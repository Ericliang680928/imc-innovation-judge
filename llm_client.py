"""
統一 LLM Client
─────────────────────────────────────
支援:
  - Anthropic Claude API
  - Google Gemini API(免費額度大、推薦)
  - Groq / OpenRouter / Mistral(OpenAI-compatible)

內建:
  - 503/429/500 自動重試(指數退避)
  - Gemini Pro 過載時自動降級到 Flash
  - 視覺增強模式(支援 Vision API,送圖片給 AI 看)
"""

import base64
import time
import random


# 各家提供的模型清單(顯示在 Sidebar)
# ⭐ Gemini 排第一位 — 最穩、免費額度大、支援讀圖、IMC 評審首選
PROVIDERS = {
    "🤖 Google Gemini (免費・推薦)": {
        "key": "gemini",
        "models": [
            "gemini-2.5-flash-lite",   # 預設!額度最寬、TPM 最大、長文徵文穩
            "gemini-2.5-flash",        # 品質更好、額度也夠
            "gemini-2.5-pro",          # 旗艦、最強、但 quota 緊
            "gemini-2.0-flash",
            "gemini-2.0-flash-lite",
        ],
        "default_model": "gemini-2.5-flash-lite",
        "api_key_url": "https://aistudio.google.com/app/apikey",
        "api_key_prefix": "AIza...",
        "free_tier": "每天免費 1500 次・支援讀圖・IMC 評審首選",
        "env_var": "GOOGLE_API_KEY",
        "base_url": None,  # 用官方 SDK
        "pricing": {
            "gemini-2.5-pro": (1.25, 5.0),
            "gemini-2.5-flash": (0.0, 0.0),
            "gemini-2.5-flash-lite": (0.0, 0.0),
            "gemini-2.0-flash": (0.0, 0.0),
            "gemini-2.0-flash-lite": (0.0, 0.0),
        },
    },
    "💎 Anthropic Claude (品質最頂)": {
        "key": "anthropic",
        "models": [
            "claude-sonnet-4-5",
            "claude-opus-4-5",
            "claude-opus-4-1",
            "claude-haiku-4-5",
            "claude-3-7-sonnet-latest",
        ],
        "default_model": "claude-sonnet-4-5",
        "api_key_url": "https://console.anthropic.com/settings/keys",
        "api_key_prefix": "sk-ant-...",
        "free_tier": "新帳號送 $5 試用(夠評 18 件)・支援讀圖・品質頂尖",
        "env_var": "ANTHROPIC_API_KEY",
        "base_url": None,
        "pricing": {
            "claude-sonnet-4-5": (3.0, 15.0),
            "claude-opus-4-5": (15.0, 75.0),
            "claude-opus-4-1": (15.0, 75.0),
            "claude-haiku-4-5": (0.80, 4.0),
            "claude-3-7-sonnet-latest": (3.0, 15.0),
        },
    },
    "🌍 OpenRouter (免費模型聚合)": {
        "key": "openrouter",
        "models": [
            # ─── 無充值門檻組(優先使用)─────────────
            "nvidia/nemotron-nano-9b-v2:free",                # 預設,無門檻最穩
            "google/gemma-4-31b-it:free",                     # Gemma 4 31B,通常無門檻
            "nvidia/nemotron-nano-12b-v2-vl:free",            # NVIDIA Nano 12B(支援讀圖)
            "liquid/lfm-2.5-1.2b-instruct:free",              # 超輕量
            "openrouter/free",                                # OpenRouter 自家免費
            # ─── 需充值 $10 帳號才能用(只做門檻不扣錢)─
            "meta-llama/llama-3.3-70b-instruct:free",
            "deepseek/deepseek-v4-flash:free",
            "qwen/qwen3-next-80b-a3b-instruct:free",
            "openai/gpt-oss-120b:free",
            "openai/gpt-oss-20b:free",
            "z-ai/glm-4.5-air:free",
            "minimax/minimax-m2.5:free",
            "qwen/qwen3-coder:free",
        ],
        "default_model": "nvidia/nemotron-nano-9b-v2:free",
        "api_key_url": "https://openrouter.ai/keys",
        "api_key_prefix": "sk-or-v1-...",
        "free_tier": "⚠️ 部分:free 模型需充值 $10(僅做門檻不扣)",
        "env_var": "OPENROUTER_API_KEY",
        "base_url": "https://openrouter.ai/api/v1",
        "pricing": {},
    },
    "🇫🇷 Mistral AI (免費)": {
        "key": "mistral",
        "models": [
            "mistral-small-latest",          # 預設,免費 tier 可用
            "open-mistral-nemo",
            "mistral-large-latest",          # 旗艦(免費 tier 有限)
            "codestral-latest",
        ],
        "default_model": "mistral-small-latest",
        "api_key_url": "https://console.mistral.ai/api-keys",
        "api_key_prefix": "...(無固定前綴)",
        "free_tier": "La Plateforme 免費層・每月限額",
        "env_var": "MISTRAL_API_KEY",
        "base_url": "https://api.mistral.ai/v1",
        "pricing": {},
    },
    "🚀 Groq (速度最快・短文評審)": {
        "key": "groq",
        "models": [
            "llama-3.1-8b-instant",          # 預設,TPM 寬鬆
            "llama-3.3-70b-versatile",       # 品質好,但 TPM 緊
            "deepseek-r1-distill-llama-70b", # 推理強
            "gemma2-9b-it",
        ],
        "default_model": "llama-3.1-8b-instant",
        "api_key_url": "https://console.groq.com/keys",
        "api_key_prefix": "gsk_...",
        "free_tier": "速度最快(每秒千 token)・⚠️ 長文徵文易爆 TPM",
        "env_var": "GROQ_API_KEY",
        "base_url": "https://api.groq.com/openai/v1",
        "pricing": {},  # 免費層
    },
}


def get_providers() -> list:
    return list(PROVIDERS.keys())


def get_provider_info(provider_name: str) -> dict:
    return PROVIDERS[provider_name]


def estimate_cost(provider_name: str, model: str,
                   n_files: int, n_judges: int) -> tuple:
    """估算成本(USD)與耗時(秒)。回傳 (cost_str, time_seconds)。"""
    in_per_call = 2500  # 粗略
    out_per_call = 5000
    total_in = n_files * n_judges * in_per_call
    total_out = n_files * n_judges * out_per_call

    p = PROVIDERS[provider_name]["pricing"].get(model, (0, 0))
    cost = (total_in / 1_000_000) * p[0] + (total_out / 1_000_000) * p[1]

    if cost < 0.005:
        cost_str = "免費(在 Gemini 免費額度內)"
    else:
        cost_str = f"~ US${cost:.2f}"

    time_seconds = n_files * n_judges * 30  # 每次約 30 秒(Gemini Flash 更快)
    if PROVIDERS[provider_name]["key"] == "gemini" and "flash" in model.lower():
        time_seconds = n_files * n_judges * 20

    return cost_str, time_seconds


# 自動降級模型表:某模型過載時,自動切到右邊備援
# 注意:Google 近期將 gemini-2.0 系列的免費額度大幅縮減(很多帳號 = 0),
# 因此 fallback 鏈避開 2.0,只在 2.5 系列內降級。
FALLBACK_MAP = {
    # Gemini
    "gemini-2.5-pro": "gemini-2.5-flash",
    "gemini-2.5-flash": "gemini-2.5-flash-lite",
    "gemini-2.5-flash-lite": None,
    "gemini-2.0-flash": "gemini-2.5-flash",
    "gemini-2.0-flash-lite": "gemini-2.5-flash-lite",
    # Claude
    "claude-opus-4-5": "claude-sonnet-4-5",
    "claude-opus-4-1": "claude-sonnet-4-5",
    "claude-sonnet-4-5": "claude-haiku-4-5",
    "claude-haiku-4-5": None,
    "claude-3-7-sonnet-latest": "claude-haiku-4-5",
    # Groq
    "llama-3.3-70b-versatile": "llama-3.1-8b-instant",
    "deepseek-r1-distill-llama-70b": "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant": None,
    "gemma2-9b-it": "llama-3.1-8b-instant",
    "mixtral-8x7b-32768": "llama-3.1-8b-instant",
    # OpenRouter:可能需充值的模型 → 降到無充值門檻組(Gemma 4 → Nemotron Nano)
    "meta-llama/llama-3.3-70b-instruct:free": "google/gemma-4-31b-it:free",
    "deepseek/deepseek-v4-flash:free": "google/gemma-4-31b-it:free",
    "qwen/qwen3-next-80b-a3b-instruct:free": "google/gemma-4-31b-it:free",
    "openai/gpt-oss-120b:free": "openai/gpt-oss-20b:free",
    "openai/gpt-oss-20b:free": "nvidia/nemotron-nano-9b-v2:free",
    "z-ai/glm-4.5-air:free": "google/gemma-4-31b-it:free",
    "minimax/minimax-m2.5:free": "google/gemma-4-31b-it:free",
    "qwen/qwen3-coder:free": "google/gemma-4-31b-it:free",
    # 無充值門檻組互相 fallback
    "google/gemma-4-31b-it:free": "nvidia/nemotron-nano-9b-v2:free",
    "nvidia/nemotron-nano-9b-v2:free": "nvidia/nemotron-nano-12b-v2-vl:free",
    "nvidia/nemotron-nano-12b-v2-vl:free": "liquid/lfm-2.5-1.2b-instruct:free",
    "liquid/lfm-2.5-1.2b-instruct:free": None,
    # Mistral
    "mistral-large-latest": "mistral-small-latest",
    "mistral-small-latest": "open-mistral-nemo",
    "open-mistral-nemo": None,
    "codestral-latest": "mistral-small-latest",
}


def diagnose_quota_error(err: Exception) -> str:
    """從錯誤訊息中診斷 quota 問題,給出具體建議。"""
    msg = str(err)
    if "limit: 0" in msg or "limit:0" in msg:
        return (
            "\n\n🚨 **診斷結果:你的帳號在此模型上的免費額度為 0**(非『用完』,是『沒給』)\n"
            "可能原因:\n"
            "  1. 此模型在你的地區/Project 尚未開放免費層\n"
            "  2. Google Cloud Project 設定問題\n"
            "  3. 須在 Cloud Console 啟用 Generative Language API\n\n"
            "💡 **解決方案**(由易到難):\n"
            "  ① **改用 gemini-2.5-flash 或 gemini-2.5-flash-lite**(這兩個免費額度最穩)\n"
            "  ② **重新申請 Key**:到 https://aistudio.google.com/app/apikey 刪掉舊 Key 建新 Key\n"
            "  ③ **切換 AI 服務商**:Sidebar 改用 Anthropic Claude(新帳號送 $5)\n"
        )
    if "429" in msg or "rate limit" in msg.lower() or "quota" in msg.lower():
        return (
            "\n\n⏱️ **診斷結果:觸發 API 速率限制**(分鐘級或每日級)\n"
            "💡 **解決方案**:\n"
            "  ① 等 1-2 分鐘再試(分鐘級限制會自動恢復)\n"
            "  ② 改用 gemini-2.5-flash-lite(額度最寬鬆)\n"
            "  ③ 把評審人數從 5 降到 3 位\n"
        )
    if "503" in msg or "unavailable" in msg.lower():
        return (
            "\n\n🌋 **診斷結果:模型過載**(流量高峰)\n"
            "💡 **解決方案**:稍等 30 秒重試,或切換到輕量模型\n"
        )
    if ("tpm" in msg.lower() or "tokens per minute" in msg.lower()
            or "tokens_per_min" in msg.lower() or "request too large" in msg.lower()):
        return (
            "\n\n🔥 **診斷結果:Groq 免費層 TPM 不足以處理長投件**\n"
            "Groq 免費層**所有模型**都是 TPM 6000,而 IMC 徵文評審單次請求約 15000-25000 tokens,"
            "**單次請求就超過 2-4 倍**(不是並行問題,是 prompt 本身就太大)。\n\n"
            "💡 **解決方案**(由易到難):\n"
            "  ① 🌍 **立刻切到 OpenRouter**:Sidebar 改選『🌍 OpenRouter』即可(你已有 Key,免費模型 TPM 寬鬆 10 倍)\n"
            "  ② 🤖 **切到 Google Gemini**:Sidebar 改選『🤖 Google Gemini』(你也有 Key,1500 次/天)\n"
            "  ③ 💎 **切到 Anthropic Claude**:品質頂尖,新帳號送 $5\n"
            "  ④ 💳 Groq 升級到 Dev Tier(付費,TPM 升至 30000)\n"
        )
    if "decommission" in msg.lower() or "not found" in msg.lower() or "no longer" in msg.lower():
        return (
            "\n\n📛 **診斷結果:此模型已下架**\n"
            "💡 **解決方案**:換成 llama-3.3-70b-versatile 或 llama-3.1-8b-instant\n"
        )
    if "context" in msg.lower() and ("length" in msg.lower() or "limit" in msg.lower()):
        return (
            "\n\n📏 **診斷結果:輸入內容過長,超出模型 context 上限**\n"
            "💡 **解決方案**:換更大 context 的模型,或縮短投件內容(超過 30 頁建議分批)\n"
        )
    if "402" in msg or "insufficient_quota" in msg.lower() or "out of credits" in msg.lower():
        return (
            "\n\n💸 **診斷結果:OpenRouter 此模型需要充值門檻**\n"
            "OpenRouter 2025 年新政策:部分 `:free` 模型需帳號餘額 ≥ $10 才能使用(雖然不扣錢,"
            "但要證明非全免費用戶)。**Llama 3.3 70B、DeepSeek V4 等熱門 :free 模型已有此限制**。\n\n"
            "💡 **解決方案**(由易到難):\n"
            "  ① 🤖 **強烈推薦:切回 Gemini gemini-2.5-flash-lite**(你有 Key,免費額度最穩,**這是最務實的選擇**)\n"
            "  ② 🌍 OpenRouter 改用無門檻小模型:`nvidia/nemotron-nano-9b-v2:free`、`google/gemma-4-31b-it:free`\n"
            "  ③ 💎 切換到 Anthropic Claude(新帳號送 $5,品質頂尖,可評 18 件)\n"
            "  ④ 💳 OpenRouter 充值 $10(只是門檻,不會被扣)\n"
        )
    return ""


def get_recommended_workers(provider: str) -> int:
    """各服務商建議的並行數(避免 rate limit)。"""
    p_key = PROVIDERS[provider]["key"]
    return {
        "groq": 1,         # TPM 限制嚴格,強制順序
        "openrouter": 2,   # :free 模型有 per-minute 限制
        "mistral": 2,
        "gemini": 3,
        "anthropic": 5,
    }.get(p_key, 3)


def is_retryable_error(err: Exception) -> bool:
    """判斷錯誤是否值得重試或降級(過載、限流、暫時性、付費門檻)。"""
    msg = str(err).lower()
    keywords = [
        "503", "429", "500", "502", "504",
        "402", "insufficient_quota", "out of credits",  # OpenRouter 付費門檻 → 降級到無門檻模型
        "unavailable", "overloaded", "rate limit", "rate_limit",
        "high demand", "try again", "resource exhausted",
        "timeout", "deadline exceeded", "connection",
    ]
    return any(k in msg for k in keywords)


# Vision-capable 模型清單(支援讀圖)
# 注意:Gemini 全系列、Claude 4.x 全系列穩定支援。
# OpenRouter 免費模型對多模態的支援很不穩定,只列明確標 -vl/vision 的。
VISION_CAPABLE_MODELS = {
    # Gemini 全系列原生支援多模態
    "gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.5-flash-lite",
    "gemini-2.0-flash", "gemini-2.0-flash-lite",
    # Claude 4.x 系列全部支援
    "claude-sonnet-4-5", "claude-opus-4-5", "claude-opus-4-1",
    "claude-haiku-4-5", "claude-3-7-sonnet-latest",
    # OpenRouter:只列明確標 -vl 的視覺模型(其他開源模型支援度不穩,不建議)
    "nvidia/nemotron-nano-12b-v2-vl:free",
}


def is_vision_capable(model: str) -> bool:
    """判斷模型是否支援視覺輸入。"""
    if model in VISION_CAPABLE_MODELS:
        return True
    # gemini 全系列、claude 全系列預設都支援
    if model.startswith("gemini-") or model.startswith("claude-"):
        return True
    if "-vl" in model.lower() or "vision" in model.lower():
        return True
    return False


def call_llm(
    provider: str, model: str, api_key: str,
    system_prompt: str, user_prompt: str,
    max_tokens: int = 12000, temperature: float = 0.4,
    max_retries: int = 4, enable_fallback: bool = True,
    on_retry=None,  # callback(attempt, delay, error, current_model)
    images: list = None,  # 新:[(label, png_bytes), ...] 視覺增強用
) -> str:
    """
    統一 LLM 呼叫介面,內建自動重試與模型降級。

    重試策略:
      - 503/429/500 等暫時錯誤 → 指數退避重試 (2s, 4s, 8s, 16s)
      - 重試 2 次仍失敗 → 嘗試降級到備援模型
    """
    provider_info = PROVIDERS[provider]
    provider_key = provider_info["key"]
    current_model = model
    tried_fallback = False

    last_err = None
    for attempt in range(max_retries):
        try:
            # 若有圖片但當前模型不支援,先警告(仍會嘗試,但可能失敗)
            if images and not is_vision_capable(current_model):
                if attempt == 0:
                    print(f"⚠️  模型 {current_model} 可能不支援視覺,將嘗試送出")

            if provider_key == "anthropic":
                return _call_anthropic(api_key, current_model, max_tokens,
                                        temperature, system_prompt, user_prompt,
                                        images=images)
            elif provider_key == "gemini":
                return _call_gemini(api_key, current_model, max_tokens,
                                     temperature, system_prompt, user_prompt,
                                     images=images)
            elif provider_key in ("groq", "openrouter", "mistral"):
                base_url = provider_info["base_url"]
                return _call_openai_compat(
                    api_key, current_model, max_tokens, temperature,
                    system_prompt, user_prompt, base_url, provider_key,
                    images=images,
                )
            else:
                raise ValueError(f"Unknown provider: {provider}")

        except Exception as e:
            last_err = e
            if not is_retryable_error(e):
                raise  # 非暫時性錯誤直接拋出

            # 第 3 次重試前,嘗試降級到備援模型
            if enable_fallback and attempt == 2 and not tried_fallback:
                fallback = FALLBACK_MAP.get(current_model)
                if fallback:
                    if on_retry:
                        on_retry(attempt + 1, 0, e, f"降級 → {fallback}")
                    current_model = fallback
                    tried_fallback = True
                    continue

            # 最後一次失敗,直接拋出(附原始錯誤 + 診斷)
            if attempt == max_retries - 1:
                diagnosis = diagnose_quota_error(e)
                raise RuntimeError(
                    f"已重試 {max_retries} 次仍失敗(最後模型:{current_model})\n\n"
                    f"📛 原始錯誤訊息:\n{str(e)[:1500]}"
                    f"{diagnosis}"
                )

            # 指數退避 + 隨機 jitter
            delay = (2 ** (attempt + 1)) + random.uniform(0, 1.5)
            if on_retry:
                on_retry(attempt + 1, delay, e, current_model)
            time.sleep(delay)

    raise last_err


def _call_anthropic(api_key, model, max_tokens, temperature,
                     system_prompt, user_prompt, images=None):
    from anthropic import Anthropic
    client = Anthropic(api_key=api_key)

    if images:
        content = [{"type": "text", "text": user_prompt}]
        for label, img_bytes in images:
            b64 = base64.b64encode(img_bytes).decode("ascii")
            content.append({
                "type": "image",
                "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}
            })
            content.append({"type": "text", "text": f"[以上為:{label}]"})
        messages = [{"role": "user", "content": content}]
    else:
        messages = [{"role": "user", "content": user_prompt}]

    response = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        system=system_prompt,
        messages=messages,
    )
    return "".join(b.text for b in response.content if hasattr(b, "text"))


def _call_openai_compat(api_key, model, max_tokens, temperature,
                          system_prompt, user_prompt, base_url, provider_key,
                          images=None):
    """用 OpenAI-compatible API 呼叫(Groq / OpenRouter / Mistral 等)。"""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError(
            "尚未安裝 openai 套件,請執行:\n  pip install openai"
        )

    # OpenRouter 需要額外 headers
    extra_headers = {}
    if provider_key == "openrouter":
        extra_headers = {
            "HTTP-Referer": "https://imc-judge-app.local",
            "X-Title": "IMC Innovation Judge",
        }

    client = OpenAI(api_key=api_key, base_url=base_url)

    # 組裝 messages — 若有圖片,user content 改為 multipart
    if images:
        user_content = [{"type": "text", "text": user_prompt}]
        for label, img_bytes in images:
            b64 = base64.b64encode(img_bytes).decode("ascii")
            user_content.append({
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{b64}"}
            })
            user_content.append({"type": "text", "text": f"[以上為:{label}]"})
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]
    else:
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

    response = client.chat.completions.create(
        model=model,
        max_tokens=max_tokens,
        temperature=temperature,
        messages=messages,
        extra_headers=extra_headers if extra_headers else None,
    )

    if not response.choices:
        raise RuntimeError(f"{provider_key} 回應為空")

    text = response.choices[0].message.content
    if not text:
        raise RuntimeError(f"{provider_key} 回應內容為空")
    return text


def _call_gemini(api_key, model, max_tokens, temperature,
                  system_prompt, user_prompt, images=None):
    try:
        from google import genai
        from google.genai import types
    except ImportError:
        raise RuntimeError(
            "尚未安裝 google-genai 套件,請執行:\n  pip install google-genai"
        )

    client = genai.Client(api_key=api_key)

    # 組裝 contents — 若有圖片,以 list 形式傳遞
    if images:
        contents = [user_prompt]
        for label, img_bytes in images:
            contents.append(types.Part.from_bytes(data=img_bytes, mime_type="image/jpeg"))
            contents.append(f"[以上為:{label}]")
    else:
        contents = user_prompt

    response = client.models.generate_content(
        model=model,
        contents=contents,
        config=types.GenerateContentConfig(
            system_instruction=system_prompt,
            temperature=temperature,
            max_output_tokens=max_tokens,
        ),
    )

    if not response.text:
        if response.candidates:
            parts = response.candidates[0].content.parts
            return "".join(p.text for p in parts if hasattr(p, "text"))
        raise RuntimeError("Gemini 回應為空,可能觸發安全過濾或額度上限")

    return response.text
