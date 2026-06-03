"""
AI 內容檢測器
─────────────────────────────────────
分析投件內容有多大比例可能由 AI 生成,從 6 個面向綜合判斷:
  1. 詞彙多樣性(AI 傾向用「綜上所述」「值得注意的是」等過渡詞)
  2. 句式結構(AI 傾向長短句不平衡)
  3. 結構化程度(AI 傾向過度條列、副標題)
  4. 內容深度(AI 傾向寬廣但缺乏具體經驗)
  5. 語氣自然度(AI 傾向過度禮貌、缺乏情感波動)
  6. 例證品質(AI 傾向用「文獻顯示」等模糊援引)
"""

import json
import re
from llm_client import call_llm


DETECTION_SYSTEM_PROMPT = """你是一位專業的 **AI 生成內容檢測專家**,具備語言學、寫作分析、機器學習背景。
你的任務是分析給定的文本,判斷其有多大比例可能由 AI(如 ChatGPT、Claude、Gemini)生成。

## 你的分析框架(6 大面向)

### 1. 詞彙多樣性(Vocabulary Diversity)
AI 痕跡:
- 過度使用過渡詞:「值得注意的是」「綜上所述」「在某種意義上」「不僅...更是...」「總而言之」
- 高頻使用「重要的」「關鍵的」「顯著的」等形容詞
- 偏好「進一步」「深入」「全面」等副詞
- 詞彙豐富但缺乏地方性、行業性術語

### 2. 句式結構(Sentence Structure)
AI 痕跡:
- 句子長度過度均勻(都是中長句)
- 大量並列結構「不僅...而且...」「既...又...」
- 條件複句頻繁「儘管...但...」「雖然...然而...」
- 缺乏短促有力的口語化句子

### 3. 結構化程度(Structuring)
AI 痕跡:
- 過度條列化(每段都用 1、2、3、4 或 ①②③)
- 機械的「首先...其次...最後...」
- 副標題與內文比例異常(每 2-3 句就一個小標)
- 結尾總是「綜上所述」「總結而言」

### 4. 內容深度(Content Depth)
AI 痕跡:
- 廣度有餘、深度不足
- 缺乏具體人物、地點、時間、數字
- 用「許多研究表明」「眾所周知」等模糊論述
- 沒有個人經驗、情感、矛盾、失敗故事

### 5. 語氣自然度(Tone Naturalness)
AI 痕跡:
- 過度禮貌、無情緒波動
- 中性到「正向中性」的單調語氣
- 缺乏疑問、自嘲、感嘆、語氣轉折
- 沒有「我」「我們」的真實主觀感受

### 6. 例證品質(Evidence Quality)
AI 痕跡:
- 引用「相關研究」「專家指出」但無具體出處
- 數據用「約」「大致」「據估計」開頭
- 案例為通用化的「某公司」「某地區」
- 缺乏具體合作對象、實際操作細節

## 重要原則
1. **不要把「結構清晰」直接判定為 AI** — 受過訓練的人也能寫出結構化文章
2. **要看「綜合特徵」** — 單一面向高分不足以下結論
3. **要區分「AI 起草後人工修飾」與「純 AI 生成」**
4. **要考慮文體** — 學術報告本就比小說結構化
5. **要列出具體證據** — 引用文中具體片段,不能空泛
6. **要客觀公正** — 不要因「文章寫得好」就懷疑 AI

## 輸出格式(嚴格遵守,輸出純 JSON,不要 markdown code fence)

{
  "overall_ai_probability": 0-100 之間的整數,代表整體 AI 機率,
  "confidence": "low" / "medium" / "high",
  "verdict_short": "1-2 句的總體判斷",
  "dimensions": {
    "vocabulary": {"score": 0-100, "reason": "..."},
    "sentence_structure": {"score": 0-100, "reason": "..."},
    "structuring": {"score": 0-100, "reason": "..."},
    "content_depth": {"score": 0-100, "reason": "..."},
    "tone_naturalness": {"score": 0-100, "reason": "..."},
    "evidence_quality": {"score": 0-100, "reason": "..."}
  },
  "suspicious_passages": [
    {"text": "(原文片段,30-100 字)", "reason": "(為何可疑)"},
    ...(列出 2-5 處)
  ],
  "human_indicators": [
    "(列出文中明顯像人寫的證據,如具體經驗、情感、矛盾、數據等)",
    ...(列出 3-5 點)
  ],
  "ai_indicators": [
    "(列出文中明顯像 AI 寫的證據,如過渡詞、條列、抽象論述等)",
    ...(列出 3-5 點)
  ],
  "verdict_long": "(完整判斷與依據,200 字以上)",
  "improvement_suggestions": [
    "(讓文本更像人寫的具體建議)",
    ...(列出 3-5 點)
  ]
}

⚠️ 嚴格規範:
- 全文使用**繁體中文**(包括 JSON 內所有 value)
- 輸出**純 JSON**,不要任何 markdown 標記、不要 ```json 包裹
- 所有分數務必是 0-100 整數
- suspicious_passages 中的 text 必須是原文真實片段
"""


def build_detection_user_prompt(content: str, case_title: str = "") -> str:
    title_line = f"【文章題目】{case_title}\n" if case_title else ""
    return f"""請分析以下文本的 AI 生成可能性。

{title_line}
【全文】
─────────────────────────────────
{content}
─────────────────────────────────

請依照系統指示,輸出純 JSON 格式的檢測結果。
"""


def detect_ai_content(
    provider: str, model: str, api_key: str, content: str,
    case_title: str = "", max_tokens: int = 8000,
) -> dict:
    """執行 AI 內容檢測,回傳 dict 結構結果。"""
    user_prompt = build_detection_user_prompt(content, case_title)

    raw_text = call_llm(
        provider=provider,
        model=model,
        api_key=api_key,
        system_prompt=DETECTION_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        max_tokens=max_tokens,
        temperature=0.2,  # 低溫度確保結果穩定
    )

    # 記錄用量
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
        )
    except Exception:
        pass

    # 嘗試解析 JSON
    result = _parse_json_robust(raw_text)
    if result:
        result["_raw_text"] = raw_text
        return result

    # 若解析失敗,回傳錯誤但保留原始文字
    return {
        "_parse_error": True,
        "_raw_text": raw_text,
        "overall_ai_probability": None,
        "verdict_short": "JSON 解析失敗,請查看原始回應",
    }


def _parse_json_robust(text: str) -> dict:
    """嘗試多種方式解析 JSON。"""
    # 1. 直接 JSON
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        pass

    # 2. 去除 markdown code fence
    cleaned = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```\s*$", "", cleaned, flags=re.MULTILINE)
    try:
        return json.loads(cleaned.strip())
    except json.JSONDecodeError:
        pass

    # 3. 找第一個 { 與最後一個 } 之間
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end > start:
        candidate = text[start:end + 1]
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            pass

    return None


def format_detection_markdown(result: dict, case_title: str = "") -> str:
    """把 detection 結果轉成 markdown 報告(用於下載)。"""
    if not result or result.get("_parse_error"):
        return f"# AI 內容檢測\n\n⚠️ 結果解析失敗。\n\n原始回應:\n```\n{result.get('_raw_text', '')[:3000]}\n```"

    prob = result.get("overall_ai_probability", "?")
    verdict = result.get("verdict_short", "")
    confidence = result.get("confidence", "")
    dims = result.get("dimensions", {})

    lines = [
        "# 🤖 AI 內容檢測報告",
        "",
        f"- **檢測標的**:{case_title or '(未填寫題目)'}",
        f"- **整體 AI 機率**:**{prob}%**",
        f"- **檢測信心度**:{_confidence_label(confidence)}",
        f"- **總體判斷**:{verdict}",
        "",
        "---",
        "",
        "## 📊 六大面向評分",
        "",
        "| 面向 | 分數(越高越像 AI) | 評分理由 |",
        "|---|---|---|",
    ]
    dim_labels = {
        "vocabulary": "詞彙多樣性",
        "sentence_structure": "句式結構",
        "structuring": "結構化程度",
        "content_depth": "內容深度",
        "tone_naturalness": "語氣自然度",
        "evidence_quality": "例證品質",
    }
    for key, label in dim_labels.items():
        d = dims.get(key, {})
        score = d.get("score", "?")
        reason = d.get("reason", "")
        lines.append(f"| {label} | **{score}** | {reason} |")
    lines.append("")

    # 人類證據
    human = result.get("human_indicators", [])
    if human:
        lines.extend(["## 👤 人類寫作證據", ""])
        for i, h in enumerate(human, 1):
            lines.append(f"{i}. {h}")
        lines.append("")

    # AI 證據
    ai_ind = result.get("ai_indicators", [])
    if ai_ind:
        lines.extend(["## 🤖 AI 生成證據", ""])
        for i, a in enumerate(ai_ind, 1):
            lines.append(f"{i}. {a}")
        lines.append("")

    # 可疑段落
    suspicious = result.get("suspicious_passages", [])
    if suspicious:
        lines.extend(["## ⚠️ 可疑段落", ""])
        for i, s in enumerate(suspicious, 1):
            lines.append(f"### 段落 {i}")
            lines.append(f"> {s.get('text', '')}")
            lines.append("")
            lines.append(f"**可疑原因**:{s.get('reason', '')}")
            lines.append("")

    # 詳細判斷
    verdict_long = result.get("verdict_long", "")
    if verdict_long:
        lines.extend(["## 📝 詳細判斷", "", verdict_long, ""])

    # 改善建議
    suggestions = result.get("improvement_suggestions", [])
    if suggestions:
        lines.extend(["## 💡 改善建議(讓文本更像人寫)", ""])
        for i, s in enumerate(suggestions, 1):
            lines.append(f"{i}. {s}")
        lines.append("")

    return "\n".join(lines)


def _confidence_label(c: str) -> str:
    return {
        "high": "🔴 高(可信度高)",
        "medium": "🟡 中(可信度中等)",
        "low": "🟢 低(可信度偏低,僅供參考)",
    }.get(c, c or "—")


def get_probability_label(prob: int) -> str:
    """依機率回傳判讀標籤。"""
    if prob is None:
        return "—"
    if prob >= 80:
        return "🚨 高度疑似 AI 生成"
    elif prob >= 60:
        return "⚠️ 中度疑似 AI 生成"
    elif prob >= 40:
        return "🤔 部分可能 AI 輔助"
    elif prob >= 20:
        return "✅ 大多為人類寫作"
    else:
        return "🌟 高度人類寫作特徵"


def get_probability_color(prob: int) -> str:
    """依機率回傳顯示色。"""
    if prob is None:
        return "#888"
    if prob >= 80:
        return "#c0392b"
    elif prob >= 60:
        return "#e67e22"
    elif prob >= 40:
        return "#f39c12"
    elif prob >= 20:
        return "#27ae60"
    else:
        return "#16a085"
