"""
IMC 第 21 屆創新獎 — AI 評審 Streamlit App (v2)
================================================
新增功能:
- 多評審委員制(N 位 AI 評審獨立打分,去掉最高最低平均)
- 5 種評審 Persona(嚴格 / 平衡 / 鼓勵 / 商業 / 創意)
- 批次評審(一次評多份檔案,輸出 ZIP)
- 4 種介面主題色
- 評分標準客製化(進階)

使用方式:
    pip install -r requirements.txt
    streamlit run app.py
"""

import os
import time
import streamlit as st
from pathlib import Path


# ─────────────────────────────────────────────
# 啟動時載入 .env(若存在)
# ─────────────────────────────────────────────
def _load_dotenv():
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and k not in os.environ:
                os.environ[k] = v
    except Exception:
        pass

_load_dotenv()

from judge_prompt import (
    SYSTEM_PROMPT, build_user_prompt,
    get_categories, get_stages, get_stage_max,
)
from judge_personas import (
    PERSONAS, get_persona_names, get_persona,
    get_default_panel, build_persona_prompt_suffix,
)
from multi_judge import (
    run_single_judge, extract_scores,
    calculate_panel_score, build_panel_summary_markdown,
    extract_quick_summary,
)
from batch_processor import build_batch_zip
from file_readers import read_file
from report_generator import markdown_to_docx, markdown_to_pdf
from vision_extractor import (
    extract_images, compress_image, estimate_vision_tokens,
)
from llm_client import get_providers, get_provider_info, estimate_cost, get_recommended_workers
from ai_detection import (
    detect_ai_content, format_detection_markdown,
    get_probability_label, get_probability_color,
)


# ─────────────────────────────────────────────
# 頁面基本設定
# ─────────────────────────────────────────────
st.set_page_config(
    page_title="IMC 創新獎 AI 評審",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ─────────────────────────────────────────────
# 主題色(4 種預設)
# ─────────────────────────────────────────────
THEMES = {
    "沉穩學院藍": {"primary": "#1a4d7a", "secondary": "#2a6ca8", "accent": "#e8f1fa"},
    "暖橘活力": {"primary": "#d35400", "secondary": "#e67e22", "accent": "#fdebd0"},
    "沉穩深邃": {"primary": "#2c3e50", "secondary": "#34495e", "accent": "#ecf0f1"},
    "高對比經典": {"primary": "#000000", "secondary": "#444444", "accent": "#f5f5f5"},
}


def apply_theme(theme_name: str):
    t = THEMES[theme_name]
    st.markdown(f"""
    <style>
    :root {{
        --imc-primary: {t['primary']};
        --imc-secondary: {t['secondary']};
        --imc-accent: {t['accent']};
    }}
    .main-title {{
        font-size: 32px; font-weight: 700;
        color: {t['primary']};
        margin-bottom: 4px;
    }}
    .sub-title {{
        font-size: 14px; color: #666; margin-bottom: 16px;
    }}
    .tag-pill {{
        display: inline-block; padding: 4px 14px; border-radius: 14px;
        background: {t['accent']}; color: {t['primary']};
        font-size: 13px; margin-right: 6px; font-weight: 500;
    }}
    .report-card {{
        background: #ffffff; border-left: 4px solid {t['primary']};
        border-radius: 6px; padding: 16px 22px; margin: 10px 0;
        box-shadow: 0 1px 3px rgba(0,0,0,0.06);
    }}
    .judge-pill {{
        display: inline-block; padding: 6px 14px; border-radius: 18px;
        background: {t['primary']}; color: white;
        font-size: 13px; margin: 3px; font-weight: 500;
    }}
    .score-box {{
        background: linear-gradient(135deg, {t['primary']} 0%, {t['secondary']} 100%);
        color: white; padding: 18px 26px; border-radius: 10px;
        text-align: center; margin: 10px 0;
    }}
    .score-num {{ font-size: 36px; font-weight: 700; }}
    .score-label {{ font-size: 13px; opacity: 0.9; }}
    div.stButton > button:first-child {{
        background-color: {t['primary']};
        color: white; border: none;
    }}
    div.stButton > button:first-child:hover {{
        background-color: {t['secondary']};
        color: white;
    }}
    </style>
    """, unsafe_allow_html=True)


# ─────────────────────────────────────────────
# Sidebar
# ─────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 系統設定")

    # AI 服務商選擇
    provider = st.selectbox(
        "🤖 AI 服務商",
        options=get_providers(),
        index=0,  # 預設 Groq (免費 + 最快)
        help="預設 Groq 免費且最快,也可試 OpenRouter 取得免費 DeepSeek/Llama 等模型!",
    )
    provider_info = get_provider_info(provider)

    # 動態 API Key 提示與環境變數對應
    env_var = provider_info.get("env_var", "GOOGLE_API_KEY")
    label_map = {
        "groq": "Groq API Key",
        "openrouter": "OpenRouter API Key",
        "mistral": "Mistral AI API Key",
        "gemini": "Google Gemini API Key",
        "anthropic": "Anthropic API Key",
    }
    api_key_label = label_map.get(provider_info["key"], "API Key")
    api_key = st.text_input(
        api_key_label,
        type="password",
        value=os.environ.get(env_var, ""),
        help=f"格式 {provider_info['api_key_prefix']}|取得:{provider_info['api_key_url']}",
        placeholder=provider_info["api_key_prefix"],
    )

    # 免費額度提示
    st.caption(f"💰 **{provider_info['free_tier']}**")
    st.caption(f"🔑 申請 Key:[點此前往]({provider_info['api_key_url']})")

    # 動態模型清單(若視覺增強開啟,過濾出支援 vision 的)
    from llm_client import is_vision_capable
    all_models = provider_info["models"]
    if "enable_vision" in dir() or True:  # placeholder,enable_vision 後面才宣告
        pass
    # 用 session state 暫存,讓視覺切換生效
    _vision_on = st.session_state.get("__vision_toggle", False)
    if _vision_on:
        filtered = [m for m in all_models if is_vision_capable(m)]
        if filtered:
            available_models = filtered
            st.caption("👁️ 視覺模式開啟 — 已過濾出支援讀圖的模型")
        else:
            available_models = all_models
            st.warning("⚠️ 此服務商的免費模型都不支援讀圖,請改用其他服務商")
    else:
        available_models = all_models
    model = st.selectbox(
        "評審模型",
        options=available_models,
        index=0,
        help="預設模型已平衡品質與速度。若開啟視覺增強,清單會只顯示支援讀圖的模型。",
    )

    max_tokens = st.slider("回應長度上限(tokens)", 4000, 16000, 12000, 1000)

    st.divider()

    # 視覺增強模式
    st.markdown("### 👁️ 視覺增強模式")
    enable_vision = st.toggle(
        "讓 AI 讀圖(讀懂流程圖、商業模式畫布、數據圖表)",
        value=False,
        key="__vision_toggle",
        help="開啟後,系統會把 PDF 每頁/PPT 每張轉成圖片送給 Vision AI 一起判讀。"
             "Token 消耗 ~5 倍,只支援多模態模型(Gemini/Claude 全系列、部分 OpenRouter)。"
             "切換後請重新選擇模型。",
    )
    max_vision_pages = st.slider(
        "視覺增強最大頁數",
        min_value=5, max_value=30, value=15, step=1,
        disabled=not enable_vision,
        help="超過此頁數的內容只保留文字,避免 token 爆量",
    )

    st.divider()

    theme_name = st.selectbox("🎨 介面主題", list(THEMES.keys()), index=0)

    st.divider()
    st.caption(
        "💡 **多評審模式提示**\n\n"
        "- N=1:快速試評\n"
        "- N=3:標準評審(去除最高最低平均)\n"
        "- N=5:完整評審團(IMC 官方建議)\n\n"
        "Gemini Flash 每天 1500 次 → 3 位評審可評 **500 件/天** 🎉"
    )

apply_theme(theme_name)


# ─────────────────────────────────────────────
# 標題列
# ─────────────────────────────────────────────
st.markdown('<div class="main-title">🏆 IMC 第 21 屆創新獎 — AI 評審系統</div>',
            unsafe_allow_html=True)
st.markdown(
    '<div class="sub-title">'
    '上傳投件檔案 → 選擇類組 → AI 評審團獨立打分 → 取得完整評審報告(含 ≥10 個提問),'
    '可下載 Word / PDF / Excel 彙整。'
    '</div>',
    unsafe_allow_html=True,
)


# ─────────────────────────────────────────────
# 1️⃣ 評審模式選擇(單件 vs 批次)
# ─────────────────────────────────────────────
st.markdown("### 1️⃣ 評審模式")
mode = st.radio(
    "選擇模式",
    options=["📄 單件評審", "📚 批次評審(多份檔案)"],
    horizontal=True,
    label_visibility="collapsed",
)
is_batch = "批次" in mode


# ─────────────────────────────────────────────
# 2️⃣ 類組與階段
# ─────────────────────────────────────────────
st.markdown("### 2️⃣ 選擇參賽類組與評審階段")

col_c1, col_c2, col_c3 = st.columns([2, 2, 1])
with col_c1:
    category = st.selectbox("參賽類組", options=get_categories(), index=4,
                            help="預設選「創新徵文類」")
with col_c2:
    stage = st.selectbox("評審階段", options=get_stages(category))
with col_c3:
    stage_max = get_stage_max(category, stage)
    st.metric("本階段滿分", f"{stage_max} 分")

category_tips = {
    "創新徵文類": (
        "📝 **徵文類精神**:不是寫「創新產品」,而是寫「**創新服務模式**」的奇想。"
        "核心命題「相同產品,不同服務模式」。**奇想性與啟發性 > 可行性**。"
    ),
    "社務創新類": "🤝 注意是「**創益**」(社會公益效益)而非純商業創利!",
    "新創企劃類": "🚀 創新程度(0–20)為最高權重,核心概念原創性是關鍵。",
    "研發製造類": "🔬 三階段評審(書審 → 發表 → 實地參訪),前三名才進入第三階段。",
    "服務行銷(含財金)類": "💼 三階段評審,服務差異化是評審重點。",
}
st.info(category_tips.get(category, ""))


# ─────────────────────────────────────────────
# 3️⃣ 評審團設定
# ─────────────────────────────────────────────
st.markdown("### 3️⃣ 評審團設定")

col_p1, col_p2 = st.columns([1, 3])
with col_p1:
    n_judges = st.select_slider(
        "評審委員人數",
        options=[1, 3, 5],
        value=3,
        help="N=1 為快速試評;N=3 為標準(去極值平均);N=5 為完整評審團。"
    )

with col_p2:
    default_panel = get_default_panel(category, n_judges)
    # 用動態 key 讓 n_judges/category 改變時,multiselect 自動重置為新的 default
    widget_key = f"personas_{category}_{n_judges}"

    # ─── 用 on_click callback 修改 state(避開「widget 建立後不可改」的限制)───
    def _apply_recommended(_key=widget_key, _val=default_panel):
        st.session_state[_key] = list(_val)

    def _select_all(_key=widget_key):
        # 取前 n 位,符合 max_selections 限制
        st.session_state[_key] = get_persona_names()[:n_judges]

    def _clear_selection(_key=widget_key):
        st.session_state[_key] = []

    # 快速操作按鈕(放在 multiselect 之前,callback 才能合法修改 state)
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    with btn_col1:
        st.button(
            "✨ 套用推薦",
            help=f"快速套用「{category}」推薦的 {n_judges} 位",
            use_container_width=True,
            on_click=_apply_recommended,
        )
    with btn_col2:
        st.button(
            f"🌟 一次選滿 {n_judges} 位",
            help=f"一鍵選滿 {n_judges} 位 persona",
            use_container_width=True,
            on_click=_select_all,
        )
    with btn_col3:
        st.button(
            "🗑️ 清空",
            help="清空選擇,重新挑",
            use_container_width=True,
            on_click=_clear_selection,
        )

    selected_personas = st.multiselect(
        f"選擇 {n_judges} 位評審委員 (依類組已自動推薦最佳組合,你可自由增減)",
        options=get_persona_names(),
        default=default_panel,
        max_selections=n_judges,
        key=widget_key,
        help="✅ 這是「多選」欄位,點一次只會選一位 — 想選多位,請繼續點開選單再選,"
             "或使用上方「一次選滿」按鈕。改變評審人數或類組時,推薦組合會自動重置。",
    )

# Persona 預覽
if selected_personas:
    pills = ""
    for p in selected_personas:
        info = get_persona(p)
        pills += f'<span class="judge-pill">{info["icon"]} {info["title"]}</span>'
    st.markdown(pills, unsafe_allow_html=True)

if len(selected_personas) != n_judges:
    st.warning(f"⚠️ 請選擇正好 {n_judges} 位評審委員(目前 {len(selected_personas)} 位)")


# ─────────────────────────────────────────────
# 4️⃣ 檔案上傳
# ─────────────────────────────────────────────
st.markdown("### 4️⃣ 上傳投件檔案")

# 提前初始化所有可能在後續被引用的變數(避免批次模式時 NameError)
single_text = ""
single_name = ""
single_images = []  # 視覺增強用 [(label, jpg_bytes), ...]
case_title = ""
batch_files = []

if not is_batch:
    tab_file, tab_paste = st.tabs(["📎 上傳檔案", "📋 直接貼上文字"])

    with tab_file:
        up = st.file_uploader(
            "支援 PDF / Word / PowerPoint / TXT / Markdown",
            type=["pdf", "docx", "pptx", "txt", "md"],
            accept_multiple_files=False,
        )
        if up is not None:
            with st.spinner(f"📖 解析 {up.name}..."):
                try:
                    file_bytes_cache = up.read()
                    single_text = read_file(up.name, file_bytes_cache)
                    single_name = up.name
                    st.success(f"✅ 已讀取 {up.name}({len(single_text)} 字)")

                    # 視覺增強:額外提取圖片
                    if enable_vision:
                        with st.spinner("🖼️ 提取圖片中..."):
                            try:
                                raw_images, total_count, source = extract_images(
                                    up.name, file_bytes_cache,
                                    max_items=max_vision_pages,
                                )
                                if raw_images:
                                    # 壓縮 + 包裝
                                    single_images = []
                                    for idx, (page_num, img_bytes) in enumerate(raw_images, 1):
                                        compressed = compress_image(img_bytes)
                                        label = {
                                            "pdf-pages": f"PDF 第 {page_num} 頁",
                                            "docx-embedded": f"Word 文件嵌入圖 #{idx}",
                                            "pptx-slides": f"PPT 第 {page_num} 張投影片",
                                            "pptx-embedded": f"PPT 嵌入圖 #{idx}",
                                        }.get(source, f"圖片 #{idx}")
                                        single_images.append((label, compressed))
                                    est_tokens = estimate_vision_tokens(len(single_images))
                                    st.info(
                                        f"🖼️ 視覺增強已啟用:**擷取 {len(single_images)} 張圖**"
                                        f"(總共 {total_count} 頁/張,預估 +{est_tokens:,} tokens)"
                                    )
                                    with st.expander(f"👁️ 預覽圖片({len(single_images)} 張)"):
                                        cols = st.columns(min(3, len(single_images)))
                                        for i, (label, img_bytes) in enumerate(single_images[:9]):
                                            with cols[i % 3]:
                                                st.image(img_bytes, caption=label, use_container_width=True)
                                else:
                                    st.warning("⚠️ 沒擷取到任何圖片(可能是純文字檔)")
                            except Exception as e:
                                st.error(f"❌ 圖片提取失敗:{e}")

                    with st.expander("👀 預覽文字內容(前 1500 字)"):
                        preview = single_text[:1500]
                        if len(single_text) > 1500:
                            preview += "\n\n...(已截斷)"
                        st.text(preview)
                except Exception as e:
                    st.error(f"❌ 讀取失敗:{e}")

    with tab_paste:
        pasted = st.text_area("貼上投件內容", height=280,
                              placeholder="把整篇徵文或投件內容貼到這裡……")
        if pasted.strip():
            single_text = pasted.strip()
            single_name = "(直接貼上)"

    case_title = st.text_input("案件名稱/題目(選填)",
                               placeholder="例:長照 4.0 A+ — 便利超商銀髮共生平台")

else:
    # 批次模式
    ups = st.file_uploader(
        "📚 一次上傳多份檔案(批次評審)",
        type=["pdf", "docx", "pptx", "txt", "md"],
        accept_multiple_files=True,
    )
    batch_files = []
    if ups:
        for u in ups:
            with st.spinner(f"📖 解析 {u.name}..."):
                try:
                    text = read_file(u.name, u.read())
                    batch_files.append({
                        "file_name": u.name,
                        "content": text,
                        "char_count": len(text),
                    })
                except Exception as e:
                    st.error(f"❌ {u.name} 讀取失敗:{e}")
        if batch_files:
            st.success(f"✅ 已讀取 {len(batch_files)} 份檔案,總計 "
                       f"{sum(f['char_count'] for f in batch_files):,} 字")
            with st.expander("📋 批次清單"):
                for i, f in enumerate(batch_files, 1):
                    st.markdown(f"- **{i}. {f['file_name']}**({f['char_count']:,} 字)")


# ─────────────────────────────────────────────
# 5️⃣ 執行評審
# ─────────────────────────────────────────────
st.markdown("### 5️⃣ 開始評審")

if "report_md" not in st.session_state:
    st.session_state.report_md = ""
if "per_judge_data" not in st.session_state:
    st.session_state.per_judge_data = []
if "panel_score" not in st.session_state:
    st.session_state.panel_score = {}
if "report_meta" not in st.session_state:
    st.session_state.report_meta = {}
if "batch_results" not in st.session_state:
    st.session_state.batch_results = []
if "ai_detection" not in st.session_state:
    st.session_state.ai_detection = None
if "ai_detection_meta" not in st.session_state:
    st.session_state.ai_detection_meta = {}


# 顯示預估成本
if selected_personas:
    n_files_now = len(batch_files) if is_batch else (1 if single_text else 0)
    if n_files_now > 0:
        cost_str, est_time = estimate_cost(provider, model, n_files_now, n_judges)
        # 並行可省時間
        parallel_time = max(est_time // n_judges, n_files_now * 30)
        st.caption(
            f"💵 **預估**:{n_files_now} 件 × {n_judges} 位評審 = "
            f"{n_files_now * n_judges} 次 API 呼叫,約 **{cost_str}**,"
            f"耗時約 **{parallel_time // 60} 分 {parallel_time % 60} 秒**(並行加速後)"
        )


def _inline_md(text):
    """處理 inline markdown(粗體、code)。"""
    import re
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code style='background:#f4f4f4;padding:1px 4px;border-radius:3px;'>\1</code>", text)
    return text


def _render_md(text):
    """簡易 markdown → HTML,用於 unsafe_allow_html 區塊內。"""
    import re
    lines = text.split("\n")
    html_parts = []
    in_list = False
    for line in lines:
        s = line.rstrip()
        if not s.strip():
            if in_list:
                html_parts.append("</ol>")
                in_list = False
            html_parts.append("<br/>")
            continue
        h = re.match(r"^(#{2,4})\s+(.+)$", s)
        if h:
            if in_list:
                html_parts.append("</ol>")
                in_list = False
            level = min(len(h.group(1)) + 1, 6)
            html_parts.append(
                f"<h{level} style='margin:10px 0 6px 0;color:#1a4d7a;'>"
                f"{_inline_md(h.group(2))}</h{level}>"
            )
            continue
        m = re.match(r"^(\d+)\.\s+(.+)$", s)
        if m:
            if not in_list:
                html_parts.append("<ol style='margin:6px 0 6px 22px;'>")
                in_list = True
            html_parts.append(
                f"<li style='margin:4px 0;'>{_inline_md(m.group(2))}</li>"
            )
            continue
        if s.lstrip().startswith(">"):
            if in_list:
                html_parts.append("</ol>")
                in_list = False
            html_parts.append(
                f"<blockquote style='border-left:3px solid #f39c12;"
                f"margin:6px 0;padding:4px 12px;color:#666;'>"
                f"{_inline_md(s.lstrip('> '))}</blockquote>"
            )
            continue
        if in_list:
            html_parts.append("</ol>")
            in_list = False
        html_parts.append(f"<p style='margin:6px 0;'>{_inline_md(s)}</p>")
    if in_list:
        html_parts.append("</ol>")
    return "\n".join(html_parts)


def call_panel(provider, model, api_key, max_tokens, personas,
               category, stage, content, case_title, images=None):
    """呼叫評審團,N 位獨立打分。回傳 per_judge_data, panel_score。"""
    from concurrent.futures import ThreadPoolExecutor, as_completed

    per_judge_data = []
    # 依 provider 決定並行度(Groq 強制順序,避免 TPM 爆量)
    recommended_workers = get_recommended_workers(provider)
    max_workers = min(len(personas), recommended_workers)

    mode_label = "順序執行" if max_workers == 1 else f"並行 {max_workers} 路"
    progress = st.progress(0, text=f"🤖 評審團 ({len(personas)} 位) 啟動中... ({mode_label})")
    status_box = st.empty()

    # 並行呼叫所有評審
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                run_single_judge,
                provider, model, api_key, max_tokens,
                p, category, stage, content, case_title,
                images,
            ): p for p in personas
        }
        done_count = 0
        for fut in as_completed(futures):
            persona = futures[fut]
            try:
                _, report = fut.result()
                scores = extract_scores(report)
                per_judge_data.append({
                    "persona": persona,
                    "report": report,
                    "total": scores["total"],
                    "max_total": scores["max_total"],
                    "items": scores["items"],
                })
                done_count += 1
                progress.progress(
                    done_count / len(personas),
                    text=f"✅ {persona} 完成({done_count}/{len(personas)})"
                )
                p_info = get_persona(persona)
                status_box.markdown(
                    f"**{p_info['icon']} {persona}** 給分:**{scores['total']}** / {scores['max_total']}"
                )
            except Exception as e:
                st.error(f"❌ {persona} 評審失敗:{e}")

    progress.empty()
    status_box.empty()

    if not per_judge_data:
        return None, None

    # 依 personas 原順序排列
    persona_order = {p: i for i, p in enumerate(personas)}
    per_judge_data.sort(key=lambda x: persona_order.get(x["persona"], 99))

    panel_score = calculate_panel_score(per_judge_data)
    return per_judge_data, panel_score


# 視覺模式相容性檢查(若開啟但模型不支援,警告)
vision_warning = ""
if enable_vision and not is_vision_capable(model):
    vision_warning = (
        f"⚠️ **視覺增強已開啟,但你選的模型 `{model}` 不支援讀圖!**\n\n"
        f"請改選支援讀圖的模型(例如):\n"
        f"- 🤖 Gemini → `gemini-2.5-flash-lite` / `gemini-2.5-flash` / `gemini-2.5-pro`\n"
        f"- 💎 Claude → 全系列都支援\n"
        f"- 🌍 OpenRouter → `google/gemma-4-31b-it:free` / `openai/gpt-oss-120b:free`\n\n"
        f"或關閉「視覺增強模式」(Sidebar)只用文字評審。"
    )
    st.error(vision_warning)

# 按鈕區
can_run_single = bool(single_text) if not is_batch else False
can_run_batch = bool(is_batch and batch_files)
vision_ready = (not enable_vision) or is_vision_capable(model)
ready = api_key and len(selected_personas) == n_judges and (can_run_single or can_run_batch) and vision_ready

col_run, col_ai = st.columns([2, 1])
with col_run:
    run_btn = st.button(
        "🚀 開始評審" if not is_batch else f"🚀 開始批次評審({len(batch_files) if is_batch else 0} 件)",
        type="primary",
        disabled=not ready,
        use_container_width=True,
    )
with col_ai:
    can_run_detection = bool(api_key) and (
        (not is_batch and single_text) or (is_batch and batch_files)
    )
    ai_btn = st.button(
        "🤖 AI 內容檢測(選填)",
        type="secondary",
        disabled=not can_run_detection,
        use_container_width=True,
        help="偵測投件內容有多大比例可能是 AI 生成的(不影響評審流程)",
    )

if not api_key:
    st.warning("⚠️ 請先在左側 Sidebar 輸入 Anthropic API Key。")
elif len(selected_personas) != n_judges:
    pass  # 已在上方提示
elif not (can_run_single or can_run_batch):
    st.warning("⚠️ 請先上傳檔案或貼上內容。")


# ─────────────────────────────────────────────
# 執行邏輯:單件
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# 執行邏輯:AI 內容檢測
# ─────────────────────────────────────────────
if ai_btn:
    detection_target = ""
    detection_title = ""
    if not is_batch and single_text:
        detection_target = single_text
        detection_title = case_title or single_name
    elif is_batch and batch_files:
        detection_target = batch_files[0]["content"]
        detection_title = batch_files[0]["file_name"]
        if len(batch_files) > 1:
            st.info(f"📌 批次模式:目前只偵測第 1 件({batch_files[0]['file_name']})")

    if detection_target:
        with st.spinner("🤖 AI 內容檢測中(約 20-40 秒)..."):
            try:
                result = detect_ai_content(
                    provider=provider, model=model, api_key=api_key,
                    content=detection_target, case_title=detection_title,
                    max_tokens=8000,
                )
                st.session_state.ai_detection = result
                st.session_state.ai_detection_meta = {
                    "case_title": detection_title,
                    "file_name": single_name if not is_batch else batch_files[0]["file_name"],
                }
                if result.get("_parse_error"):
                    st.warning("⚠️ AI 結果解析失敗,請看下方原始輸出")
                else:
                    st.success(f"✅ 檢測完成!整體 AI 機率:**{result.get('overall_ai_probability', '?')}%**")
            except Exception as e:
                st.error(f"❌ AI 檢測失敗:{e}")


if run_btn and not is_batch and single_text:
    st.session_state.report_md = ""
    st.session_state.per_judge_data = []
    st.session_state.panel_score = {}

    per_judge_data, panel_score = call_panel(
        provider, model, api_key, max_tokens,
        selected_personas, category, stage, single_text, case_title,
        images=single_images if enable_vision else None,
    )

    if per_judge_data:
        if n_judges >= 2:
            # 多評審:產生綜合彙整 + 各位評審完整意見
            summary_md = build_panel_summary_markdown(
                case_title, category, stage, per_judge_data, panel_score,
            )
            st.session_state.report_md = summary_md
        else:
            # 單評審:直接顯示該位的完整報告
            st.session_state.report_md = per_judge_data[0]["report"]

        st.session_state.per_judge_data = per_judge_data
        st.session_state.panel_score = panel_score
        st.session_state.report_meta = {
            "category": category,
            "stage": stage,
            "case_title": case_title or "(未填寫)",
            "file_name": single_name,
            "n_judges": n_judges,
        }
        st.success("🎉 評審完成!下方檢視報告。")


# ─────────────────────────────────────────────
# 執行邏輯:批次
# ─────────────────────────────────────────────
if run_btn and is_batch and batch_files:
    st.session_state.batch_results = []
    batch_progress = st.progress(0, text=f"📚 批次評審 0 / {len(batch_files)}")

    for i, f in enumerate(batch_files, 1):
        st.markdown(f"---")
        st.markdown(f"### 📄 處理第 {i} / {len(batch_files)} 件:`{f['file_name']}`")

        per_judge_data, panel_score = call_panel(
            provider, model, api_key, max_tokens,
            selected_personas, category, stage,
            f["content"], f["file_name"],
        )

        if per_judge_data:
            if n_judges >= 2:
                report_md = build_panel_summary_markdown(
                    f["file_name"], category, stage, per_judge_data, panel_score,
                )
            else:
                report_md = per_judge_data[0]["report"]

            st.session_state.batch_results.append({
                "file_name": f["file_name"],
                "case_title": f["file_name"],
                "category": category,
                "stage": stage,
                "report_markdown": report_md,
                "panel_score": panel_score,
                "per_judge_data": per_judge_data,
            })
            total = panel_score.get("trimmed_average") or panel_score.get("raw_average")
            st.success(f"✅ 完成:**{total} 分** / {panel_score.get('max_total')}")

        batch_progress.progress(i / len(batch_files),
                                text=f"📚 批次評審 {i} / {len(batch_files)}")

    batch_progress.empty()
    st.success(f"🎉 批次評審完成({len(st.session_state.batch_results)} / {len(batch_files)} 件成功)!")


# ─────────────────────────────────────────────
# 顯示結果:單件
# ─────────────────────────────────────────────
# ─────────────────────────────────────────────
# 顯示 AI 內容檢測結果
# ─────────────────────────────────────────────
if st.session_state.ai_detection and not st.session_state.ai_detection.get("_parse_error"):
    st.divider()
    st.markdown("### 🤖 AI 內容檢測結果")

    result = st.session_state.ai_detection
    prob = result.get("overall_ai_probability", 0) or 0
    label = get_probability_label(prob)
    color = get_probability_color(prob)
    confidence = result.get("confidence", "")
    confidence_label = {
        "high": "🔴 高(可信度高)",
        "medium": "🟡 中(可信度中等)",
        "low": "🟢 低(可信度偏低,僅供參考)",
    }.get(confidence, "—")

    # 主結果卡片
    st.markdown(
        f"""<div style='background:linear-gradient(135deg,{color}dd,{color});
        color:white;padding:24px 28px;border-radius:12px;text-align:center;margin:12px 0;'>
            <div style='font-size:13px;opacity:.9;margin-bottom:6px;'>整體 AI 機率</div>
            <div style='font-size:48px;font-weight:700;line-height:1;'>{prob}%</div>
            <div style='font-size:18px;font-weight:600;margin-top:10px;'>{label}</div>
            <div style='font-size:13px;opacity:.9;margin-top:8px;'>檢測信心度:{confidence_label}</div>
        </div>""",
        unsafe_allow_html=True,
    )

    # 一句話判斷
    verdict_short = result.get("verdict_short", "")
    if verdict_short:
        st.markdown(
            f"<div style='background:#fff;border-left:4px solid {color};"
            f"padding:14px 18px;margin:10px 0;font-size:15px;'>"
            f"📝 <strong>總體判斷</strong>:{verdict_short}</div>",
            unsafe_allow_html=True,
        )

    # 六大面向長條圖
    st.markdown("#### 📊 六大面向評分")
    dims = result.get("dimensions", {})
    dim_labels = {
        "vocabulary": "詞彙多樣性",
        "sentence_structure": "句式結構",
        "structuring": "結構化程度",
        "content_depth": "內容深度",
        "tone_naturalness": "語氣自然度",
        "evidence_quality": "例證品質",
    }
    for key, label_zh in dim_labels.items():
        d = dims.get(key, {})
        score = d.get("score", 0) or 0
        reason = d.get("reason", "")
        bar_color = get_probability_color(score)
        st.markdown(
            f"""<div style='margin:8px 0;'>
                <div style='display:flex;justify-content:space-between;font-size:14px;margin-bottom:3px;'>
                    <strong>{label_zh}</strong>
                    <span style='color:{bar_color};font-weight:600;'>{score}/100</span>
                </div>
                <div style='background:#eee;border-radius:8px;height:14px;overflow:hidden;'>
                    <div style='background:{bar_color};width:{score}%;height:100%;transition:width .5s;'></div>
                </div>
                <div style='font-size:12px;color:#666;margin-top:3px;'>{reason}</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # 人類痕跡 vs AI 痕跡 對照
    col_h, col_a = st.columns(2)
    with col_h:
        st.markdown("#### 👤 人類寫作證據")
        for h in result.get("human_indicators", []):
            st.markdown(f"- {h}")
    with col_a:
        st.markdown("#### 🤖 AI 生成證據")
        for a in result.get("ai_indicators", []):
            st.markdown(f"- {a}")

    # 可疑段落
    suspicious = result.get("suspicious_passages", [])
    if suspicious:
        st.markdown("#### ⚠️ 可疑段落")
        for i, s in enumerate(suspicious, 1):
            with st.container():
                st.markdown(
                    f"""<div style='background:#fef5e7;border-left:4px solid #e67e22;
                    padding:12px 16px;border-radius:6px;margin:8px 0;'>
                        <div style='color:#888;font-size:12px;margin-bottom:4px;'>段落 {i}</div>
                        <div style='font-style:italic;color:#444;margin-bottom:8px;'>
                            「{s.get('text', '')}」</div>
                        <div style='font-size:13px;color:#c0392b;'>
                            🔍 <strong>可疑原因</strong>:{s.get('reason', '')}</div>
                    </div>""",
                    unsafe_allow_html=True,
                )

    # 詳細判斷
    verdict_long = result.get("verdict_long", "")
    if verdict_long:
        with st.expander("📖 點開查看完整判斷理由"):
            st.markdown(verdict_long)

    # 改善建議
    suggestions = result.get("improvement_suggestions", [])
    if suggestions:
        st.markdown("#### 💡 改善建議(讓文本更像人寫)")
        for i, s in enumerate(suggestions, 1):
            st.markdown(f"{i}. {s}")

    # 下載
    st.markdown("---")
    ai_meta = st.session_state.ai_detection_meta
    md_report = format_detection_markdown(result, ai_meta.get("case_title", ""))
    ts = int(time.time())
    col_dm, col_dd = st.columns(2)
    with col_dm:
        st.download_button(
            "📄 下載 AI 檢測報告(Markdown)",
            data=md_report.encode("utf-8"),
            file_name=f"AI檢測_{ai_meta.get('case_title', 'report')}_{ts}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col_dd:
        try:
            from report_generator import markdown_to_docx
            docx_bytes = markdown_to_docx(md_report, {
                "category": "AI 內容檢測",
                "stage": "—",
                "case_title": ai_meta.get("case_title", ""),
                "file_name": ai_meta.get("file_name", ""),
            })
            st.download_button(
                "📝 下載 AI 檢測報告(Word)",
                data=docx_bytes,
                file_name=f"AI檢測_{ai_meta.get('case_title', 'report')}_{ts}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        except Exception as e:
            st.caption(f"Word 產生失敗:{e}")
elif st.session_state.ai_detection and st.session_state.ai_detection.get("_parse_error"):
    st.divider()
    st.warning("⚠️ AI 內容檢測 — 結果解析失敗")
    with st.expander("📋 查看原始 AI 回應"):
        st.code(st.session_state.ai_detection.get("_raw_text", "")[:5000])


if not is_batch and st.session_state.report_md:
    st.divider()
    st.markdown("### 📋 評審報告")

    meta = st.session_state.report_meta
    st.markdown(
        f"<span class='tag-pill'>類組:{meta.get('category', '')}</span>"
        f"<span class='tag-pill'>階段:{meta.get('stage', '')}</span>"
        f"<span class='tag-pill'>檔案:{meta.get('file_name', '')}</span>"
        f"<span class='tag-pill'>評審數:{meta.get('n_judges', 1)} 位</span>",
        unsafe_allow_html=True,
    )

    # 最終得分顯示
    panel = st.session_state.panel_score
    if panel and panel.get("trimmed_average") is not None:
        max_total = panel.get("max_total") or "?"
        rate = panel["trimmed_average"] / max_total * 100 if max_total != "?" else 0
        st.markdown(
            f"""<div class='score-box'>
            <div class='score-label'>{"去極值平均" if meta.get('n_judges', 1) >= 3 else "平均"}最終得分</div>
            <div class='score-num'>{panel['trimmed_average']} / {max_total}</div>
            <div class='score-label'>達成率 {rate:.1f}%</div>
            </div>""",
            unsafe_allow_html=True,
        )

    # 🚀 快速摘要卡片(萃取自單一評審 / 中間評審)
    summary_text = ""
    per_judge = st.session_state.per_judge_data
    if per_judge:
        if len(per_judge) == 1:
            # 單評審:直接萃取
            summary_text = extract_quick_summary(per_judge[0]["report"])
        else:
            # 多評審:挑分數最接近 trimmed_average 的
            target = panel.get("trimmed_average", 0)
            if panel.get("trimmed_judges"):
                trimmed_set = set(panel["trimmed_judges"])
                trimmed = [d for d in per_judge if d["persona"] in trimmed_set]
                if trimmed:
                    rep = min(trimmed, key=lambda d: abs((d.get("total") or 0) - target))
                    summary_text = extract_quick_summary(rep["report"])

    if summary_text:
        st.markdown("### 🚀 快速摘要")
        st.markdown(
            f"<div style='background:#fff8e8;border-left:5px solid #f39c12;"
            f"padding:18px 22px;border-radius:8px;margin:14px 0;'>"
            f"{_render_md(summary_text)}"
            f"</div>",
            unsafe_allow_html=True
        )
        with st.expander("📖 查看完整評審報告(含 ≥5 亮點 / ≥5 建議 / ≥10 提問 / 總評等詳細內容)"):
            st.markdown(st.session_state.report_md)
    else:
        st.markdown(st.session_state.report_md)

    st.divider()
    st.markdown("### 📥 下載報告")

    col_d1, col_d2, col_d3 = st.columns(3)
    ts = int(time.time())

    with col_d1:
        st.download_button(
            "📄 Markdown",
            data=st.session_state.report_md.encode("utf-8"),
            file_name=f"IMC評審_{meta.get('category', '')}_{ts}.md",
            mime="text/markdown",
            use_container_width=True,
        )
    with col_d2:
        try:
            docx_bytes = markdown_to_docx(st.session_state.report_md, meta)
            st.download_button(
                "📝 Word",
                data=docx_bytes,
                file_name=f"IMC評審_{meta.get('category', '')}_{ts}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"Word 失敗:{e}")
    with col_d3:
        try:
            pdf_bytes = markdown_to_pdf(st.session_state.report_md, meta)
            st.download_button(
                "📕 PDF",
                data=pdf_bytes,
                file_name=f"IMC評審_{meta.get('category', '')}_{ts}.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        except Exception as e:
            st.error(f"PDF 失敗:{e}")


# ─────────────────────────────────────────────
# 顯示結果:批次
# ─────────────────────────────────────────────
if is_batch and st.session_state.batch_results:
    st.divider()
    st.markdown("### 📊 批次評審結果")

    # 排名摘要
    ranked = sorted(
        st.session_state.batch_results,
        key=lambda x: -((x.get("panel_score") or {}).get("trimmed_average") or 0)
    )
    st.markdown("#### 🏅 排名")
    for rank, r in enumerate(ranked, 1):
        panel = r.get("panel_score") or {}
        total = panel.get("trimmed_average")
        medal = {1: "🥇", 2: "🥈", 3: "🥉"}.get(rank, f"#{rank}")
        col_r1, col_r2, col_r3 = st.columns([1, 5, 1])
        with col_r1:
            st.markdown(f"### {medal}")
        with col_r2:
            st.markdown(f"**{r['file_name']}**")
            st.caption(f"{r['category']} | {r['stage']}")
        with col_r3:
            st.metric("分數", f"{total}/{panel.get('max_total')}")

    st.divider()
    st.markdown("#### 📂 各件詳細報告")
    for r in st.session_state.batch_results:
        panel = r.get("panel_score") or {}
        total = panel.get("trimmed_average")
        with st.expander(f"📄 {r['file_name']} — {total} 分"):
            # 萃取代表評審的快速摘要
            per_judge = r.get("per_judge_data") or []
            summary_text = ""
            if per_judge:
                if len(per_judge) == 1:
                    summary_text = extract_quick_summary(per_judge[0]["report"])
                else:
                    target = panel.get("trimmed_average", 0)
                    if panel.get("trimmed_judges"):
                        trimmed_set = set(panel["trimmed_judges"])
                        trimmed = [d for d in per_judge if d["persona"] in trimmed_set]
                        if trimmed:
                            rep = min(trimmed, key=lambda d: abs((d.get("total") or 0) - target))
                            summary_text = extract_quick_summary(rep["report"])
            if summary_text:
                st.markdown(
                    f"<div style='background:#fff8e8;border-left:5px solid #f39c12;"
                    f"padding:14px 18px;border-radius:8px;margin:8px 0 14px 0;'>"
                    f"<h4 style='margin:0 0 6px 0;color:#d35400;'>🚀 快速摘要</h4>"
                    f"{_render_md(summary_text)}"
                    f"</div>",
                    unsafe_allow_html=True
                )
                st.markdown("---")
                st.markdown("**📖 完整評審報告:**")
            st.markdown(r["report_markdown"])

    st.divider()
    st.markdown("### 📥 批次下載")
    try:
        zip_bytes = build_batch_zip(st.session_state.batch_results)
        st.download_button(
            "📦 下載批次評審 ZIP(內含每件 Word/PDF + 彙整 Excel)",
            data=zip_bytes,
            file_name=f"IMC批次評審_{int(time.time())}.zip",
            mime="application/zip",
            use_container_width=True,
        )
    except Exception as e:
        st.error(f"ZIP 產生失敗:{e}")


# Footer
st.divider()
st.caption(
    "IMC 第 21 屆創新獎 AI 評審系統 v2 · "
    f"目前主題:{theme_name} · "
    "評審結果僅供參考,正式名次以實際評審會議為準。"
)
