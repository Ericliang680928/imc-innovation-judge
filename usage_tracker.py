"""
本 session 用量追蹤器
─────────────────────────────────────
記錄當前 Streamlit session 對各 AI 服務商的呼叫次數與 token 估算,
並計算佔每日免費額度的百分比。

注意:
- 只算本 session(分頁開啟期間),關閉瀏覽器分頁就清零
- Token 數為估算值,實際以 Google/Anthropic 官方為準
- 雲端版每位使用者各自獨立計數
"""

import streamlit as st
from datetime import datetime


# 各模型的每日免費額度 (Requests Per Day)
# 來源:各家官方文件(2026 年現行)
FREE_DAILY_LIMITS = {
    # ── Gemini ────────────────────────────
    "gemini-2.5-flash-lite": 1500,
    "gemini-2.5-flash": 1500,
    "gemini-2.5-pro": 50,
    "gemini-2.0-flash": 1500,
    "gemini-2.0-flash-lite": 1500,
    # ── Groq ──────────────────────────────
    "llama-3.1-8b-instant": 1000,
    "llama-3.3-70b-versatile": 1000,
    "deepseek-r1-distill-llama-70b": 1000,
    "gemma2-9b-it": 1000,
    # ── OpenRouter :free ──────────────────
    "nvidia/nemotron-nano-9b-v2:free": 200,
    "google/gemma-4-31b-it:free": 200,
    "nvidia/nemotron-nano-12b-v2-vl:free": 200,
    "liquid/lfm-2.5-1.2b-instruct:free": 200,
    # ── Mistral ───────────────────────────
    "mistral-small-latest": 100,
    "open-mistral-nemo": 100,
    # ── Claude (no free tier, 給 $5 credit 換算) ──
    "claude-sonnet-4-5": 18,
    "claude-haiku-4-5": 100,
    "claude-opus-4-5": 5,
    "claude-opus-4-1": 5,
}


def init_usage_state():
    """初始化 session state 中的用量追蹤欄位。"""
    if "usage_log" not in st.session_state:
        st.session_state.usage_log = []  # [{ts, provider, model, in_tokens, out_tokens}]
    if "session_start" not in st.session_state:
        st.session_state.session_start = datetime.now().isoformat()


def log_api_call(provider: str, model: str,
                  in_tokens: int = 0, out_tokens: int = 0,
                  is_vision: bool = False, n_images: int = 0):
    """記錄一次 API 呼叫。"""
    init_usage_state()
    # 視覺輸入 token 估算(每張圖 ~ 1500)
    vision_tokens = n_images * 1500 if is_vision else 0
    st.session_state.usage_log.append({
        "ts": datetime.now().isoformat(),
        "provider": provider,
        "model": model,
        "in_tokens": int(in_tokens) + vision_tokens,
        "out_tokens": int(out_tokens),
        "is_vision": is_vision,
        "n_images": n_images,
    })


def estimate_call_tokens(content_chars: int, has_system_prompt: bool = True,
                          max_output_tokens: int = 12000) -> tuple:
    """從文字長度估算 input/output token(無實際 API 回應時用)。

    估算公式:
      - 中文 1 字 ≈ 1.5 tokens(因為包含繁體分詞)
      - System prompt(SKILL.md + persona) ≈ 5000 tokens
      - Output 預估為 max_output_tokens 的 60%
    """
    user_in = int(content_chars * 1.5)
    system_in = 5000 if has_system_prompt else 0
    in_tokens = user_in + system_in
    out_tokens = int(max_output_tokens * 0.6)
    return in_tokens, out_tokens


def get_session_summary() -> dict:
    """彙整本 session 的用量。"""
    init_usage_state()
    log = st.session_state.usage_log
    if not log:
        return {"total_calls": 0, "by_model": {}, "total_in": 0, "total_out": 0}

    by_model = {}
    total_in = total_out = 0
    for entry in log:
        m = entry["model"]
        if m not in by_model:
            by_model[m] = {
                "calls": 0, "in_tokens": 0, "out_tokens": 0,
                "provider": entry["provider"], "vision_calls": 0,
            }
        by_model[m]["calls"] += 1
        by_model[m]["in_tokens"] += entry["in_tokens"]
        by_model[m]["out_tokens"] += entry["out_tokens"]
        if entry.get("is_vision"):
            by_model[m]["vision_calls"] += 1
        total_in += entry["in_tokens"]
        total_out += entry["out_tokens"]

    return {
        "total_calls": len(log),
        "by_model": by_model,
        "total_in": total_in,
        "total_out": total_out,
    }


def render_sidebar_widget():
    """在 Sidebar 渲染用量追蹤小工具。"""
    init_usage_state()
    summary = get_session_summary()
    total_calls = summary["total_calls"]

    st.markdown("### 📊 本 session 用量")

    if total_calls == 0:
        st.caption("尚未呼叫任何 AI API。")
        st.caption("開始評審後會顯示用量。")
        if st.button("🔄 重置計數", use_container_width=True, key="__reset_usage_empty"):
            st.session_state.usage_log = []
            st.rerun()
        return

    # 總覽
    total_tokens = summary["total_in"] + summary["total_out"]
    col1, col2 = st.columns(2)
    with col1:
        st.metric("呼叫次數", f"{total_calls}")
    with col2:
        st.metric("總 tokens", f"{total_tokens:,}")

    # 各模型用量 + 佔每日額度比例
    st.caption("**各模型用量(估算)**")
    for model, stats in summary["by_model"].items():
        calls = stats["calls"]
        limit = FREE_DAILY_LIMITS.get(model, None)
        if limit:
            pct = (calls / limit) * 100
            color = "🟢" if pct < 25 else ("🟡" if pct < 75 else "🔴")
            # 用 progress bar 顯示
            short_model = model.split("/")[-1][:25]
            st.markdown(
                f"`{short_model}`  \n"
                f"{color} **{calls}/{limit}** 次({pct:.1f}%)"
            )
            # progress bar(限制在 0-1.0)
            st.progress(min(pct / 100, 1.0))
        else:
            st.markdown(f"`{model.split('/')[-1][:25]}`  \n⚪ **{calls}** 次(無額度資訊)")

        # vision 標記
        if stats.get("vision_calls", 0) > 0:
            st.caption(f"  ↳ 其中 {stats['vision_calls']} 次含視覺 👁️")

    # 詳細(可摺疊)
    with st.expander("🔍 詳細呼叫紀錄"):
        st.caption(f"Session 啟動:{st.session_state.session_start[:19]}")
        for i, entry in enumerate(reversed(st.session_state.usage_log[-10:]), 1):
            ts_short = entry["ts"][11:19]
            vision_mark = " 👁️" if entry.get("is_vision") else ""
            st.text(
                f"{ts_short}  {entry['model'].split('/')[-1][:20]}{vision_mark}\n"
                f"  in: {entry['in_tokens']:,} | out: {entry['out_tokens']:,}"
            )
        if len(st.session_state.usage_log) > 10:
            st.caption(f"…還有 {len(st.session_state.usage_log) - 10} 筆")

    # 重置
    if st.button("🔄 重置本 session 計數", use_container_width=True, key="__reset_usage"):
        st.session_state.usage_log = []
        st.rerun()

    # 提醒
    if total_calls > 0:
        any_warning = any(
            (stats["calls"] / FREE_DAILY_LIMITS[m]) * 100 >= 75
            for m, stats in summary["by_model"].items()
            if m in FREE_DAILY_LIMITS
        )
        if any_warning:
            st.warning("⚠️ 已用 ≥75% 每日額度,接近上限!")

    # 說明
    st.caption(
        "ℹ️ 本計數**僅供參考**,實際以官方為準。"
        "關閉分頁會清零。"
    )
