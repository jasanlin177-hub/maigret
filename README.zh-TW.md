# Maigret 🕵️‍♂️ — 臺灣加強版

> 本分支（`jasanlin177-hub/maigret`）以上游 [soxoj/maigret](https://github.com/soxoj/maigret) 為基礎，專為**臺灣使用情境**深度強化，包含臺灣主流網站支援、全繁體中文介面、SHA-256 PoW 繞過機制，以及 Windows 相容性修正。

**[上游原版（English）](https://github.com/soxoj/maigret) · [简体中文](README.zh-CN.md)**

---

## 🇹🇼 與上游版本的差異總覽

| 功能面向 | 上游原版 | 臺灣加強版 |
|---|---|---|
| 臺灣站點支援 | 部分停用 | **24+ 臺灣站點啟用並驗證** |
| SHA-256 PoW 繞過 | ✗ | ✅ 自動解題（支援伊莉等 Discuz 論壇） |
| 網頁介面語言 | 英文 | **全繁體中文介面** |
| HTML / CSV 報告 | 英文欄位 | **中英對照雙語欄位** |
| 快速篩選 | ✗ | ✅ 一鍵「只查臺灣站」 |
| 查詢類型 | 僅用戶名稱 | **用戶名稱 / Email / 暱稱** 三選一 |
| Windows 相容性 | 部分已知問題 | ✅ 修正檔案下載路徑與 DNS 解析器 |
| TLS 憑證處理 | 嚴格驗證 | ✅ 跳過無效憑證（適應臺灣企業/ISP 環境） |

---

## 📦 安裝

### 前置需求

- Python 3.10 或以上版本
- （建議）安裝 `curl_cffi` 以支援 TLS 指紋偽裝與 SHA-256 PoW 解題

### 快速安裝

```bash
# 1. 複製本分支
git clone https://github.com/jasanlin177-hub/maigret.git
cd maigret

# 2. 安裝（含建議選用套件）
pip install .
pip install curl_cffi            # 啟用 TLS 指紋偽裝 + PoW 解題
pip install 'maigret[pdf]'       # 可選：啟用 PDF 報告輸出
```

### Docker（網頁 UI）

```bash
# CLI 模式
docker run -v /mydir:/app/reports soxoj/maigret:latest <用戶名稱> --html

# 網頁 UI 模式（在 http://localhost:5000 開啟介面）
docker run -p 5000:5000 soxoj/maigret:web
```

---

## 🚀 快速開始

```bash
# 搜尋單一用戶名稱（預設查前 500 名流量網站）
maigret <用戶名稱>

# 只查臺灣站點（加上 --tags tw）
maigret <用戶名稱> --tags tw

# 同時搜尋多個用戶名稱
maigret 名稱一 名稱二 名稱三

# 輸出 HTML 報告（含中英對照欄位）
maigret <用戶名稱> --html

# 輸出 CSV 報告（含中文標頭）
maigret <用戶名稱> --csv
```

---

## 🇹🇼 臺灣站點支援

本分支對以下 **24+ 個臺灣本土平台**進行了 URL 模式修正、實際帳號驗證，並全數重新啟用：

### 社群 / 論壇

| 站點 | 說明 | 保護機制 |
|---|---|---|
| **Dcard** | 臺灣最大匿名社群平台 | TLS 指紋偽裝 |
| **巴哈姆特（Bahamut）** | 臺灣最大遊戲社群小屋 | TLS 指紋偽裝 |
| **Mobile01** | 臺灣最大科技討論區（以會員 ID 查詢） | TLS 指紋偽裝 |
| **伊莉討論區（Eyny）** | 臺灣綜合論壇 | **SHA-256 PoW 自動解題** |
| **背包客棧（Backpackers）** | 臺灣最大自助旅行論壇 | — |

### 購物 / 活動

| 站點 | 說明 | 保護機制 |
|---|---|---|
| **露天市集（Ruten）** | 臺灣最大網路拍賣賣場 | — |
| **KKTIX** | 臺灣主要活動售票平台（子域名格式） | — |
| **Accupass 活動通** | 活動主辦單位頁面 | — |
| **嘖嘖（Zeczec）** | 臺灣群眾募資平台 | TLS 指紋偽裝 |

### 媒體 / 創作

| 站點 | 說明 | 保護機制 |
|---|---|---|
| **T客邦（TechBang）** | 臺灣科技媒體作者頁 | — |
| **女人迷（Womany）** | 性別議題媒體專欄作家頁 | — |
| **報導者（TWReporter）** | 非營利調查報導記者頁 | — |
| **故事 StoryStudio** | 歷史文化內容平台專欄作家 | — |
| **點子生活（SayDigi）** | 科技生活部落格作者頁 | — |
| **iThome 電腦報** | 臺灣 IT 媒體 | — |
| **INSIDE 硬塞** | 網路趨勢觀察媒體 | — |
| **關鍵評論網（TNL）** | 多語言新聞評論平台 | — |

### 程式 / 知識

| 站點 | 說明 | 保護機制 |
|---|---|---|
| **HackMD** | 臺灣本土 Markdown 協作筆記平台 | — |
| **方格子（Vocus）** | 臺灣付費訂閱寫作平台 | — |
| **愛料理（iCook）** | 臺灣最大食譜社群 | — |

> **查詢所有臺灣站點：**
> ```bash
> maigret <用戶名稱> --tags tw
> ```

---

## 🌐 全繁體中文網頁介面

本分支對內建網頁 UI（`maigret --web 5000`）進行了完整中文化。

```bash
maigret --web 5000
# 瀏覽器開啟 http://127.0.0.1:5000
```

### 介面功能特色

**快速篩選列：**
- 🇹🇼 **只查臺灣站** — 一鍵自動套用 `--tags tw` 篩選
- **查前 500 站** — 快速設定為預設流量前 500 名
- **查全部站點** — 啟用全庫掃描
- **✕ 清除篩選** — 重置所有篩選條件

**查詢類型切換：**
- 👤 使用者名稱
- ✉️ Email
- 🏷️ 暱稱

**其他中文化項目：**
- 表單所有標籤與說明文字（繁體中文）
- 等待頁面提示訊息
- 錯誤訊息（含常見錯誤的中文說明，例如 PDF 套件未安裝）
- 標籤篩選區國家名稱中文化（如 TW - 臺灣、JP - 日本、US - 美國等）

---

## 📊 中英對照報告

### HTML 報告

HTML 報告中所有擷取到的個人資料欄位均顯示**中文名稱**與英文原名對照，例如：

| 欄位鍵值 | 顯示名稱 |
|---|---|
| `fullname` | 全名 |
| `created_at` | 建立時間 |
| `followers` | 追蹤者數 |
| `is_family_safe` | 兒少友善 |
| `blog_id` | 部落格 ID |
| `is_scratchteam` | Scratch 官方團隊 |

### CSV 報告

CSV 標頭採**中英換行對照**格式，方便以試算表軟體（Excel、Numbers）直接開啟閱讀，同時保持機器可讀性。

---

## 🔧 技術強化說明

### SHA-256 PoW 自動解題（PowSha256Checker）

部分基於 Discuz 架構的臺灣論壇（如**伊莉討論區**）使用自架 SHA-256 工作量證明（Proof-of-Work）防護頁。此機制會在頁面內嵌 JavaScript 暴力破解一個 nonce，使純 HTTP 客戶端因無法設置對應 Cookie 而被擋下。

本分支新增 `PowSha256Checker` 解題器：

1. 偵測頁面中的 PoW 標記（`solvePoW`）
2. 提取 `challenge`、`ts`、`diff` 參數
3. 在 Python 端暴力計算 nonce（diff=4 通常不到 0.1 秒）
4. 注入三個 Cookie（`<prefix>_n`、`<prefix>_ts`、`<prefix>_ch`）後重取頁面
5. 支援最多 5 輪重試，以應對重新發出質詢的情況

站點的 `data.json` 設定中加入 `"protection": ["pow_sha256"]` 即可自動觸發此解題器（需安裝 `curl_cffi`）。

### TLS 憑證寬鬆驗證

部分臺灣站點持有無效或過期的 TLS 憑證，或使用者處於具 TLS 攔截的企業/ISP 環境中。本分支在 `CurlCffiChecker` 中加入 `verify: False`，避免因憑證問題導致誤報失敗。

### Windows 相容性修正

- **報告下載路徑**：改用 `os.path.normpath` 與 `send_file`，解決 Windows 路徑分隔符號導致的 404 問題
- **DNS 解析器**：Web 模式強制採用系統 DNS（`dns_resolver='threaded'`），避免 Windows 上 `aiodns` 常見的解析失敗
- **PDF 套件缺失**：PDF 產生失敗時不中斷整體流程，其他格式報告仍可正常下載

---

## 📋 使用範例

```bash
# 查詢所有臺灣站點
maigret <用戶名稱> --tags tw

# 查詢全部站點並輸出 HTML 報告
maigret <用戶名稱> -a --html

# 查詢臺灣站點並輸出 CSV
maigret <用戶名稱> --tags tw --csv

# 使用代理伺服器
maigret <用戶名稱> --proxy socks5://127.0.0.1:1080

# 透過 Tor 查詢（含 .onion 站點）
maigret <用戶名稱> --tor-proxy socks5://127.0.0.1:9050

# AI 調查摘要（需設定 OPENAI_API_KEY）
export OPENAI_API_KEY=sk-...
maigret <用戶名稱> --ai
```

---

## 🤝 貢獻

歡迎新增或修正臺灣站點定義：

1. 在 `maigret/resources/data.json` 中新增或修改站點設定
2. 確保 `usernameClaimed` 使用**真實存在的帳號**，而非預留位置
3. 確保 `usernameUnclaimed` 設為不存在的值（如 `noonewouldeverusethis7`）
4. 以 CLI 實際測試：真實帳號應顯示 `found`，不存在帳號應顯示 `not found`
5. 若站點有 TLS 指紋要求，加入 `"protection": ["tls_fingerprint"]`；有 PoW 防護者加入 `"protection": ["pow_sha256"]`
6. 執行 `./utils/update_site_data.py` 重新產生 `sites.md` 與資料庫元資料
7. 發送 Pull Request

更多細節請參閱上游 [CONTRIBUTING.md](https://github.com/soxoj/maigret/blob/main/CONTRIBUTING.md)。

---

## ⚠️ 免責聲明

本工具**僅供教育與合法目的使用**。使用者須自行遵守所在地區的適用法律（包括個人資料保護法、GDPR、CCPA 等）。作者與貢獻者對任何濫用行為不承擔任何法律責任。

---

## 📄 授權條款

MIT © [soxoj](https://github.com/soxoj/maigret)（上游）
臺灣加強版修改部分 © [jasanlin177-hub](https://github.com/jasanlin177-hub)

本分支依 MIT 授權條款釋出，可自由用於商業用途。
