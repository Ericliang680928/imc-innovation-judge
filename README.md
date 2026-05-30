# 🏆 IMC 第 21 屆創新獎 AI 評審模擬器

一個基於 Streamlit + 多家 AI API 的 IMC 創新獎評審輔助工具。

> 🌐 **線上版**:[點此使用](#) (部署後填入 URL)
> 💻 **本機版**:見下方安裝說明

---

## ✨ 功能

- 🏆 **5 大類組評審**:研發製造類、服務行銷類、新創企劃類、社務創新類、創新徵文類
- 👥 **評審團模式**:1/3/5 位 AI 評審獨立打分,自動去極值平均(IMC 官方計分法)
- 🎭 **5 種評審 Persona**:嚴格派 / 平衡派 / 鼓勵派 / 商業派 / 創意派
- 👁️ **視覺增強模式**:讓 AI 看圖(流程圖、商業模式畫布、數據圖表)
- 🤖 **AI 內容偵測**:檢測投件多少比例可能是 AI 生成
- 📚 **批次評審**:一次評多份,自動排名 + Excel 彙整
- 📥 **多格式下載**:Word / PDF / Markdown / ZIP

---

## 🌐 線上使用(推薦)

只要瀏覽器:

1. 開啟 [https://your-app-url.streamlit.app](#) (部署後更新)
2. 在左側 Sidebar 選擇 AI 服務商並填入 API Key
3. 上傳投件 → 選類組 → 開始評審

**API Key 取得**(任選一個):
- 🤖 **Google Gemini**(推薦,免費 1500 次/天):https://aistudio.google.com/app/apikey
- 🚀 **Groq**(免費,適合短文):https://console.groq.com/keys
- 🌍 **OpenRouter**(免費模型聚合):https://openrouter.ai/keys
- 💎 **Anthropic Claude**(付費,品質頂尖):https://console.anthropic.com

---

## 💻 本機安裝

### 系統需求
- Python 3.10+
- Windows / macOS / Linux

### 快速啟動(Windows)
```bash
# 1. 雙擊「啟動IMC評審模擬器.bat」 (一鍵搞定)
# 2. 瀏覽器自動開啟 http://localhost:8501
```

### 一般安裝
```bash
pip install -r requirements.txt
streamlit run app.py
```

### 設定 API Key(本機版可選)
```bash
cp .env.example .env
# 編輯 .env 填入你的 Key
```

---

## 🔒 隱私聲明

- ✅ 投件內容**不會被儲存到伺服器**
- ✅ API Key **存放於瀏覽器 session**,關閉視窗即清除
- ✅ 評審結果可下載至本機
- ⚠️ 投件內容會送給你選擇的 AI 服務商(Google / Anthropic 等)處理
- ⚠️ 請勿上傳含個資、機密的投件

---

## 📦 技術棧

- **Frontend**:Streamlit
- **AI Provider**:Anthropic Claude / Google Gemini / Groq / OpenRouter / Mistral
- **檔案處理**:pdfplumber / PyMuPDF / python-docx / python-pptx
- **報告產生**:reportlab(PDF)/ python-docx(Word)/ openpyxl(Excel)

---

## 📜 授權與聲明

- 本系統依照「中華民國國際工商經營研究社聯合會」第 21 屆創新獎簡章設計
- 評審結果**僅供參考**,正式名次以實際評審會議為準
- 程式碼採 MIT 授權,可自由修改、分享

---

## 🤖 Generated with [Claude Code](https://claude.com/claude-code)
