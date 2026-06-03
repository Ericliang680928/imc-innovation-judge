"""
多評審委員協調與彙整計分
─────────────────────────────────────
模擬真實 IMC 評審會議:
  1. N 位評審獨立打分(不同 persona + temperature)
  2. 抽出各位評審的給分明細(逐項分數)
  3. 計算「去掉最高最低分後平均」(N>=3 才執行)
  4. 產出綜合報告(各評審意見彙整 + 最終得分)
"""

import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from judge_prompt import SYSTEM_PROMPT, build_user_prompt
from judge_personas import build_persona_prompt_suffix, get_persona
from llm_client import call_llm


# ─────────────────────────────────────────────
# 單一評審呼叫(可被 ThreadPoolExecutor 並行)
# ─────────────────────────────────────────────
def run_single_judge(
    provider: str, model: str, api_key: str, max_tokens: int,
    persona_name: str, category: str, stage: str,
    content: str, case_title: str,
    images: list = None,  # 視覺增強用 [(label, jpg_bytes), ...]
):
    """呼叫一位 AI 評審,回傳 (persona_name, markdown_report)。"""
    persona = get_persona(persona_name)
    system_prompt = SYSTEM_PROMPT + build_persona_prompt_suffix(persona_name)

    # 若有圖片,提示 AI 同時參考圖文
    if images:
        vision_note = (
            "\n\n📸 **本次評審含視覺資料**:除文字外,投件還附有 "
            f"{len(images)} 張圖片(可能是流程圖、商業模式畫布、數據圖表、產品照、簡報投影片等)。"
            "請務必把圖片內容納入評審判斷,在亮點/建議/提問中,若有引用圖片,請註明「圖 X」。\n"
        )
        system_prompt = system_prompt + vision_note

    user_prompt = build_user_prompt(category, stage, content, case_title)

    text = call_llm(
        provider=provider,
        model=model,
        api_key=api_key,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        temperature=persona["temperature"],
        images=images,
    )

    # 記錄用量(僅本 session)
    try:
        from usage_tracker import log_api_call, estimate_call_tokens
        in_tok, out_tok = estimate_call_tokens(
            content_chars=len(content) + len(case_title or ""),
            has_system_prompt=True,
            max_output_tokens=max_tokens,
        )
        log_api_call(
            provider=provider, model=model,
            in_tokens=in_tok, out_tokens=out_tok,
            is_vision=bool(images),
            n_images=len(images) if images else 0,
        )
    except Exception:
        pass  # 用量追蹤失敗不影響主流程

    return persona_name, text


# ─────────────────────────────────────────────
# 解析評審報告中的評分表
# ─────────────────────────────────────────────
def _clamp_score(score, max_val):
    """把分數截斷到 [0, max_val]。"""
    if score is None or max_val is None:
        return score
    try:
        if score < 0:
            return 0
        if score > max_val:
            return max_val
    except TypeError:
        return score
    return score


def extract_scores(report_markdown: str) -> dict:
    """
    從 markdown 報告中擷取評分表的每項給分與合計。
    回傳:
      {
        "items": [{"name": ..., "max": ..., "score": ...}, ...],
        "total": int or float,
        "max_total": int or float,
        "clamped": bool (是否有發生上限截斷),
      }
    """
    items = []
    total = None
    max_total = None

    # 找評分表所在區段
    # 表格行格式:| 項目名 | 配分 | 給分 | 說明 |
    lines = report_markdown.split("\n")
    in_table = False
    header_seen = False

    for line in lines:
        s = line.strip()
        if not s.startswith("|") or not s.endswith("|"):
            if in_table:
                in_table = False  # 表格結束
            continue

        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 3:
            continue

        # 偵測是否為評分表表頭
        if not in_table and any("評審給分" in c or "給分" in c for c in cells):
            in_table = True
            header_seen = True
            continue

        # 分隔列 (--- 列)
        if all(re.match(r"^:?-{3,}:?$", c) for c in cells if c):
            continue

        if in_table:
            # 嘗試解析配分與給分
            item_name = _clean_md(cells[0])
            max_val = _parse_score(cells[1]) if len(cells) > 1 else None
            score_val = _parse_score(cells[2]) if len(cells) > 2 else None

            # 合計列
            if "合計" in item_name or "合計" in cells[0]:
                total = score_val
                max_total = max_val
                continue

            if max_val is not None and score_val is not None:
                items.append({
                    "name": item_name,
                    "max": max_val,
                    "score": score_val,
                })

    # 若 total 沒抓到,從 items 加總
    if total is None and items:
        total = sum(it["score"] for it in items)
        max_total = sum(it["max"] for it in items)

    # 🛡️ 上限截斷:防止 AI 給出超過配分的分數
    clamped = False
    for it in items:
        original_score = it.get("score")
        clamped_score = _clamp_score(original_score, it.get("max"))
        if original_score != clamped_score:
            clamped = True
            it["original_score"] = original_score
            it["score"] = clamped_score

    # 重新計算 total(基於截斷後的 items)
    if items:
        recalc_total = sum(it["score"] for it in items if it["score"] is not None)
        recalc_max = sum(it["max"] for it in items if it["max"] is not None)
        # 若原本抓到的 total 超過 max_total,或與項目加總不一致,以項目加總為準
        if (total is not None and max_total is not None and total > max_total) or \
           (total is not None and abs(total - recalc_total) > 0.1):
            clamped = True
            total = recalc_total
            max_total = recalc_max

    # 最後保險:total 不可超過 max_total
    if total is not None and max_total is not None and total > max_total:
        clamped = True
        total = max_total

    return {
        "items": items,
        "total": total,
        "max_total": max_total,
        "clamped": clamped,
    }


def _parse_score(text: str):
    """從字串提取數字。
    支援:
      - 範圍格式「0–30」「0-20」「0~10」→ 取最大值(配分用)
      - 單值格式「24」「24.5」「8/10」「8 分」→ 取第一個(給分用)
    """
    if not text:
        return None
    text = _clean_md(text)

    # 範圍格式:0-X / 0–X / 0~X(半形/全形連字號、波浪號)
    range_match = re.match(
        r"^\s*0\s*[-–—‐‑‒−~〜]\s*(\d+(?:\.\d+)?)\s*$",
        text.strip()
    )
    if range_match:
        n = float(range_match.group(1))
        return int(n) if n.is_integer() else n

    # 一般單值格式 — 取第一個數字
    m = re.search(r"\d+(?:\.\d+)?", text)
    if m:
        n = float(m.group())
        return int(n) if n.is_integer() else n
    return None


def _clean_md(text: str) -> str:
    """移除 markdown 標記。"""
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"⭐+", "", text)
    text = re.sub(r"`([^`]+)`", r"\1", text)
    return text.strip()


# ─────────────────────────────────────────────
# 計算「去掉最高最低分後平均」
# ─────────────────────────────────────────────
def calculate_panel_score(per_judge_scores: list) -> dict:
    """
    輸入:[{persona, total, items}, ...] (N 位評審)
    回傳:
      {
        "totals": [...],           # 各評審總分
        "max_total": int,
        "raw_average": float,      # 全部平均
        "trimmed_average": float,  # 去掉最高最低分平均(N>=3)
        "min": (persona, score),
        "max": (persona, score),
        "trimmed_judges": [...],   # 被納入計算的評審 personas
        "per_item": [...],         # 各項目的去極值平均
      }
    """
    if not per_judge_scores:
        return {}

    totals = [(d["persona"], d["total"]) for d in per_judge_scores if d["total"] is not None]
    if not totals:
        return {}

    max_total = next((d["max_total"] for d in per_judge_scores
                      if d.get("max_total") is not None), None)

    raw_avg = sum(t[1] for t in totals) / len(totals)

    # 去極值平均(N >= 3 才執行)
    if len(totals) >= 3:
        sorted_by_score = sorted(totals, key=lambda x: x[1])
        min_one = sorted_by_score[0]
        max_one = sorted_by_score[-1]
        trimmed = sorted_by_score[1:-1]
        trimmed_avg = sum(t[1] for t in trimmed) / len(trimmed)
        trimmed_judges = [t[0] for t in trimmed]
    else:
        min_one = min(totals, key=lambda x: x[1])
        max_one = max(totals, key=lambda x: x[1])
        trimmed_avg = raw_avg
        trimmed_judges = [t[0] for t in totals]

    # 🛡️ 最終保險:平均也不可超過滿分
    if max_total is not None:
        if trimmed_avg > max_total:
            trimmed_avg = max_total
        if raw_avg > max_total:
            raw_avg = max_total

    # 各項目去極值平均
    per_item = _calc_per_item_trimmed(per_judge_scores)

    return {
        "totals": totals,
        "max_total": max_total,
        "raw_average": round(raw_avg, 2),
        "trimmed_average": round(trimmed_avg, 2),
        "min": min_one,
        "max": max_one,
        "trimmed_judges": trimmed_judges,
        "per_item": per_item,
    }


def _calc_per_item_trimmed(per_judge_scores: list) -> list:
    """各評分項目的去極值平均(N>=3)或一般平均(N<3)。"""
    if not per_judge_scores:
        return []

    # 用第一位評審的項目作為基準
    base_items = per_judge_scores[0].get("items", [])
    result = []
    for i, base in enumerate(base_items):
        values = []
        for d in per_judge_scores:
            its = d.get("items", [])
            if i < len(its) and its[i]["score"] is not None:
                values.append(its[i]["score"])
        if not values:
            continue
        if len(values) >= 3:
            values_sorted = sorted(values)
            trimmed = values_sorted[1:-1]
            avg = sum(trimmed) / len(trimmed) if trimmed else sum(values_sorted) / len(values_sorted)
        else:
            avg = sum(values) / len(values)
        result.append({
            "name": base["name"],
            "max": base["max"],
            "avg": round(avg, 2),
            "all_scores": values,
        })
    return result


# ─────────────────────────────────────────────
# 產生「綜合彙整報告」Markdown
# ─────────────────────────────────────────────
def _pick_representative_judge(per_judge_data: list, panel_score: dict):
    """挑出最具代表性的評審 —— N>=3 時為中間評審(計入分數);N<3 時為第一位。"""
    if not per_judge_data:
        return None
    if len(per_judge_data) < 3 or not panel_score.get("trimmed_judges"):
        return per_judge_data[0]
    trimmed_personas = set(panel_score["trimmed_judges"])
    # 從計入計算的評審中找分數最接近 trimmed_average 的
    target = panel_score.get("trimmed_average", 0)
    trimmed_judges = [d for d in per_judge_data if d["persona"] in trimmed_personas]
    if not trimmed_judges:
        return per_judge_data[0]
    return min(trimmed_judges, key=lambda d: abs((d.get("total") or 0) - target))


def extract_quick_summary(report_markdown: str) -> str:
    """從單一評審報告中萃取「🚀 快速摘要」段落(第二章內容)。"""
    # 找「## 二、🚀 快速摘要」到下一個 ## 標題之間的內容
    pattern = r"##\s*二[、\s]*🚀?\s*快速摘要[^\n]*\n(.*?)(?=\n##\s|\Z)"
    m = re.search(pattern, report_markdown, re.DOTALL)
    if m:
        return m.group(1).strip()
    return ""


def build_panel_summary_markdown(
    case_title: str, category: str, stage: str,
    per_judge_data: list, panel_score: dict,
) -> str:
    """產生「評審團綜合彙整」的 markdown 段落(放在所有評審報告前)。"""
    n_judges = len(per_judge_data)

    lines = [
        f"# 🏆 IMC 第 21 屆創新獎 — 評審團綜合報告",
        "",
        f"- **案件名稱**:{case_title or '(未填寫)'}",
        f"- **參賽類組**:{category}",
        f"- **評審階段**:{stage}",
        f"- **評審委員數**:{n_judges} 位",
        f"- **計分方式**:" + (
            "去掉最高最低分後平均(IMC 官方計分法)" if n_judges >= 3 else "全部評審平均"
        ),
        "",
        "---",
        "",
        "## 🎯 最終得分",
        "",
    ]

    if panel_score.get("trimmed_average") is not None:
        max_total = panel_score.get("max_total") or "?"
        lines.append(
            f"### **{panel_score['trimmed_average']} / {max_total} 分**"
        )
        lines.append("")

        # 若有任一評審發生上限截斷,加上提醒
        if any(d.get("items") and any(it.get("original_score") is not None
                                       for it in d["items"]) for d in per_judge_data):
            lines.append(
                "> ⚠️ **提醒**:本次評審中有評審委員給分超出配分上限,系統已自動截斷至上限。"
                "詳見各評審完整意見中標註的「原始分數」。"
            )
            lines.append("")
        if n_judges >= 3:
            min_p, min_s = panel_score["min"]
            max_p, max_s = panel_score["max"]
            lines.append(f"- 去掉最高分:**{max_s} 分**({max_p}) 🔥")
            lines.append(f"- 去掉最低分:**{min_s} 分**({min_p}) ❄️")
            lines.append(f"- 中間 {len(panel_score['trimmed_judges'])} 位評審平均:**{panel_score['trimmed_average']} 分**")
        lines.append(f"- 全部評審原始平均:{panel_score['raw_average']} 分")
        lines.append("")

    # 📌 評審團快速摘要(用中間那位評審的精華 — 即計入分數的)
    representative = _pick_representative_judge(per_judge_data, panel_score)
    if representative:
        rep_summary = extract_quick_summary(representative["report"])
        if rep_summary:
            from judge_personas import get_persona
            p_info = get_persona(representative["persona"])
            lines.extend([
                "---",
                "",
                f"## 📌 評審團快速摘要",
                "",
                f"> 以下為**計入最終分數的中間評審({p_info['icon']} {representative['persona']})**之精華觀點。"
                "完整 N 位評審意見請見下方各別展開。",
                "",
                rep_summary,
                "",
            ])

    # 各評審總分對照
    lines.extend([
        "## 📊 各評審總分對照",
        "",
        "| 評審委員 | 給分 | 與平均差距 |",
        "|---|---|---|",
    ])
    raw_avg = panel_score.get("raw_average", 0)
    for persona, score in panel_score.get("totals", []):
        diff = score - raw_avg
        sign = "+" if diff >= 0 else ""
        icon = get_persona(persona)["icon"]
        lines.append(f"| {icon} {persona} | {score} | {sign}{round(diff, 2)} |")
    lines.append("")

    # 各項目去極值平均對照
    if panel_score.get("per_item"):
        lines.extend([
            "## 📈 各評分項目|去極值平均",
            "",
            "| 評分項目 | 配分 | 平均得分 | 達成率 | 各評審原始分數 |",
            "|---|---|---|---|---|",
        ])
        for item in panel_score["per_item"]:
            rate = round(item["avg"] / item["max"] * 100, 1) if item["max"] else 0
            scores_str = " / ".join(str(s) for s in item["all_scores"])
            lines.append(
                f"| {item['name']} | {item['max']} | **{item['avg']}** | {rate}% | {scores_str} |"
            )
        lines.append("")

    # 共識與分歧分析
    lines.extend([
        "## 🤝 評審共識與分歧分析",
        "",
    ])
    if panel_score.get("per_item"):
        # 找最大分歧的項目
        items_with_range = []
        for item in panel_score["per_item"]:
            scores = item["all_scores"]
            if len(scores) >= 2:
                gap = max(scores) - min(scores)
                items_with_range.append((item["name"], gap, scores))
        if items_with_range:
            items_with_range.sort(key=lambda x: x[1], reverse=True)
            top_gap = items_with_range[0]
            top_consensus = items_with_range[-1]
            lines.append(f"- **最大分歧項目**:**{top_gap[0]}**(分差 {top_gap[1]} 分,各評審給分 {' / '.join(str(s) for s in top_gap[2])})")
            lines.append(f"- **最高共識項目**:**{top_consensus[0]}**(分差僅 {top_consensus[1]} 分,各評審給分 {' / '.join(str(s) for s in top_consensus[2])})")
    lines.append("")

    # 各評審意見列表
    lines.extend([
        "## 👥 各評審委員獨立意見",
        "",
        "下列為 N 位評審委員的完整獨立評審意見(未經彙整),"
        "可看到不同 persona 角度的差異:",
        "",
    ])
    for d in per_judge_data:
        persona = d["persona"]
        p_info = get_persona(persona)
        lines.append(f"### {p_info['icon']} {p_info['title']}|總分 **{d['total']}** / {d['max_total']}")
        lines.append("")
        lines.append("<details><summary>📖 點此展開完整評審意見</summary>")
        lines.append("")
        lines.append(d["report"])
        lines.append("")
        lines.append("</details>")
        lines.append("")
        lines.append("---")
        lines.append("")

    return "\n".join(lines)
