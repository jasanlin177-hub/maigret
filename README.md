# Maigret 🕵️ — Taiwan Enhanced Fork

> **English** | [繁體中文](#繁體中文)

Maigret collects a dossier on a person by username only, checking for accounts on a huge number of sites and gathering all available information from web pages. No API keys required.

This fork ([jasanlin177-hub/maigret](https://github.com/jasanlin177-hub/maigret)) builds on the upstream [soxoj/maigret](https://github.com/soxoj/maigret) with deep enhancements for Taiwan users: a fully Traditional Chinese web interface, 89 Taiwan-local sites, formatted Excel reports, SHA-256 PoW bypass, and Windows compatibility fixes.

---

## 🇹🇼 Differences from Upstream

| Feature | Upstream | Taiwan Fork |
|---|---|---|
| Taiwan sites | Partially disabled | 89 Taiwan sites (`taiwan` tag) |
| Web UI language | English | Full Traditional Chinese UI |
| Excel report | ✗ | ✅ Formatted .xlsx (column width, alignment, info sheet) |
| HTML / CSV column headers | English | Bilingual (EN + ZH) |
| Quick filter | ✗ | ✅ One-click "Taiwan only" scan |
| PDF output | Built-in PDF generator | ✅ Browser print HTML (no CJK garbling) |
| SHA-256 PoW bypass | ✗ | ✅ Auto-solve (supports Eyny / Discuz forums) |
| Query type | Username only | Username / Email / Nickname (3-in-1) |
| Timeout default | 30 s | 60 s |
| Windows compatibility | Partial issues | ✅ Path separator & DNS resolver fixes |
| TLS certificate handling | Strict validation | ✅ Skip invalid certs (Taiwan enterprise / ISP environments) |

---

## 📦 Installation

### Prerequisites

- Python 3.10+
- `curl_cffi` (recommended — enables TLS fingerprint spoofing & SHA-256 PoW solving)

### Quick Install

```bash
# 1. Clone this fork
git clone https://github.com/jasanlin177-hub/maigret.git
cd maigret

# 2. Install base packages
pip install .

# 3. Recommended extras
pip install curl_cffi   # TLS fingerprint + PoW solving
pip install openpyxl    # Excel (.xlsx) report output
```

### Docker (Local Web UI)

```bash
# Build and start the web UI (default final stage is "web")
docker build -t maigret-web .
docker run -p 5000:5000 maigret-web

# CLI mode
docker build --target cli -t maigret-cli .
docker run maigret-cli <username> --html
```

---

## 🚀 Quick Start

### CLI

```bash
# Search a single username (default: top 500 sites by traffic)
maigret <username>

# Taiwan sites only (89 sites)
maigret <username> --tags taiwan

# Multiple usernames
maigret name1 name2 name3

# HTML report (bilingual columns)
maigret <username> --html

# CSV report (Chinese headers)
maigret <username> --csv

# Use a proxy
maigret <username> --proxy socks5://127.0.0.1:1080

# Route through Tor (includes .onion sites)
maigret <username> --tor-proxy socks5://127.0.0.1:9050
```

### Web UI

```bash
maigret --web 5000
# Open http://127.0.0.1:5000 in your browser
```

---

## 🌐 Traditional Chinese Web Interface

### Quick-Filter Bar

| Button | Function |
|---|---|
| 🇹🇼 Taiwan Only | Applies `--tags taiwan` automatically — scans 89 Taiwan-local sites |
| Top 500 | Set to top 500 sites by traffic (default) |
| All Sites | Enable full-database scan (~3,200+ sites) |
| ✕ Clear Filters | Reset all filters |

### Query Types

- 👤 Username
- ✉️ Email
- 🏷️ Nickname

### Results Page

- Account count bar (Found / Report Done / Search Target)
- Status explanation block (expanded by default — clarifies Available / Unknown meanings)
- Per-target report sections are collapsible — click header to toggle
- Account relationship graph (Pyvis interactive)

### Report Downloads

| Format | Description |
|---|---|
| CSV | Bilingual headers — opens directly in Excel / Numbers |
| Excel (.xlsx) | Formatted: column widths, frozen headers, auto-filter, info sheet |
| JSON | Full raw data (NDJSON format) |
| HTML | Bilingual columns — print or save as PDF via Ctrl+P |

---

## 📊 Excel Report Format

| Col | Field | Format |
|---|---|---|
| A | Username | — |
| B | Site Name | — |
| C | Site Chinese Name | Smaller font to fit column |
| D | Site Homepage | — |
| E | Profile URL | — |
| F | Account Status (EN) | Centered |
| G | Account Status Description (ZH) | Centered, width 35 |
| H | HTTP Status Code | Centered |
| I | HTTP Description | Centered |

An additional **Status Legend** sheet lists the meaning of each status code to prevent misinterpreting *Available* (account not found) vs *Unknown* (inconclusive).

---

## 🇹🇼 Taiwan Site Support (89 sites)

Filter with `--tags taiwan` or the "Taiwan Only" button in the Web UI.

### Social / Forums

| Site | Description | Protection |
|---|---|---|
| Dcard | Taiwan's largest anonymous community | TLS fingerprint |
| Bahamut (巴哈姆特) | Taiwan's largest gaming community | TLS fingerprint |
| Mobile01 | Taiwan's largest tech discussion board | TLS fingerprint |
| Eyny (伊莉討論區) | Taiwan general forum | SHA-256 PoW auto-solve |
| Backpackers (背包客棧) | Taiwan's largest independent travel forum | — |

### Shopping / Events

| Site | Description |
|---|---|
| Ruten (露天市集) | Taiwan's largest online auction platform |
| KKTIX | Event ticketing (subdomain format) |
| Accupass (活動通) | Event organizer pages |
| Zeczec (嘖嘖) | Taiwan crowdfunding platform |

### Media / Creative

| Site | Description |
|---|---|
| TechBang (T客邦) | Tech media author pages |
| Womany (女人迷) | Gender issues media |
| TWReporter (報導者) | Non-profit investigative journalism |
| iThome | Taiwan IT media |
| TNL (關鍵評論網) | Multilingual news & commentary |

### Knowledge / Writing

| Site | Description |
|---|---|
| HackMD | Markdown collaborative notes |
| Vocus (方格子) | Paid subscription writing platform |
| iCook (愛料理) | Recipe community |

---

## 🔧 Technical Enhancements

### SHA-256 PoW Auto-Solve (PowSha256Checker)

Some Taiwan forums built on Discuz (e.g. Eyny) use SHA-256 Proof-of-Work protection. The mechanism embeds JavaScript in the page to force browsers to brute-force a nonce — pure HTTP clients are blocked because they cannot set the required cookie.

This fork adds PowSha256Checker with the following flow:

1. Detect the solvePoW marker in the page
2. Extract challenge, ts, diff parameters
3. Brute-force the nonce in Python (diff=4 typically takes < 0.1 s)
4. Inject three cookies then re-fetch the page
5. Up to 5 retry rounds

Add "protection": ["pow_sha256"] to a site entry in data.json to enable it (requires curl_cffi).

### Windows Compatibility Fixes

- **Report download paths** — uses os.path.normpath + send_file to fix Windows backslash path 404 errors
- **DNS resolver** — Web mode forces system DNS (dns_resolver='threaded') to avoid aiodns resolution failures on Windows
- **PDF dependency** — heavy PDF library removed; browser-print HTML replaces it (CJK renders correctly)

### Relaxed TLS Verification

Some Taiwan sites hold invalid certificates, or users operate in TLS-intercepting corporate / ISP environments. This fork adds verify: False to CurlCffiChecker to prevent certificate errors from producing false negatives.

---

## ☁️ Cloud Deployment (Render.com)

This fork ships with render.yaml for one-click deployment to Render.com free tier:

1. Fork this repository to your GitHub account
2. Go to render.com and create a new Web Service, selecting your GitHub repo
3. Render automatically reads render.yaml and builds the web Docker stage
4. After deployment, access the Web UI via the URL Render provides

> **Note:** Render's free plan has a 512 MB memory limit. To avoid OOM errors during full-database scans, use "Top 500" or "Taiwan Only" mode instead of scanning all sites.

---

## 🤝 Contributing Taiwan Sites

1. Add or modify site entries in maigret/resources/data.json
2. usernameClaimed must be a real, existing account
3. usernameUnclaimed should be a value guaranteed not to exist (e.g. noonewouldeverusethis7)
4. Test via CLI: the real account should show found; the non-existent one should show not found
5. Add "protection": ["tls_fingerprint"] for TLS-fingerprinted sites, or "protection": ["pow_sha256"] for PoW-protected sites
6. Open a Pull Request with test screenshots

---

## ⚠️ Disclaimer

For educational and lawful purposes only. Users are solely responsible for complying with all applicable laws (including Personal Data Protection Act and equivalents) in their jurisdiction. The authors bear no responsibility for any misuse.

---

## 📄 License

MIT © soxoj (upstream)
Taiwan Fork modifications © jasanlin177-hub

Released under the MIT License.

---
---

# 繁體中文

> [English](#maigret-️--taiwan-enhanced-fork) | **繁體中文**

Maigret 僅憑用戶名稱即可蒐集個人資料，透過檢查大量網站的帳號並從網頁擷取所有可用資訊。無需 API 金鑰。

本分支（[jasanlin177-hub/maigret](https://github.com/jasanlin177-hub/maigret)）以上游 [soxoj/maigret](https://github.com/soxoj/maigret) 為基礎，針對臺灣使用情境進行深度強化：全繁體中文網頁介面、89 個臺灣本土站點、格式化 Excel 報告、SHA-256 PoW 繞過，以及 Windows 相容性修正。

---

## 🇹🇼 與上游版本差異

| 功能面向 | 上游原版 | 臺灣加強版 |
|---|---|---|
| 臺灣站點 | 部分停用 | 89 個臺灣站點（taiwan 標籤） |
| 網頁介面語言 | 英文 | 全繁體中文介面 |
| Excel 報告 | ✗ | ✅ 格式化 .xlsx（欄寬、置中、說明工作表） |
| HTML / CSV 報告欄位 | 英文 | 中英對照雙語 |
| 快速篩選 | ✗ | ✅ 一鍵「只查臺灣站」 |
| PDF 輸出 | 內建 PDF 產生器 | ✅ 瀏覽器列印 HTML（中文不亂碼） |
| SHA-256 PoW 繞過 | ✗ | ✅ 自動解題（支援伊莉等 Discuz 論壇） |
| 查詢類型 | 僅用戶名稱 | 用戶名稱 / Email / 暱稱 三選一 |
| 逾時預設值 | 30 秒 | 60 秒 |
| Windows 相容性 | 部分問題 | ✅ 路徑分隔符號與 DNS 解析器修正 |
| TLS 憑證處理 | 嚴格驗證 | ✅ 跳過無效憑證（適應臺灣企業 / ISP 環境） |

---

## 📦 安裝

### 前置需求

- Python 3.10+
- curl_cffi（建議安裝，啟用 TLS 指紋偽裝與 SHA-256 PoW 解題）

### 快速安裝

```bash
# 1. 複製本分支
git clone https://github.com/jasanlin177-hub/maigret.git
cd maigret

# 2. 安裝基本套件
pip install .

# 3. 建議額外安裝
pip install curl_cffi  # TLS 指紋偽裝 + PoW 解題
pip install openpyxl   # Excel (.xlsx) 報告輸出
```

### Docker（本地網頁 UI）

```bash
# 建置並啟動網頁 UI（預設最後 stage 為 web）
docker build -t maigret-web .
docker run -p 5000:5000 maigret-web

# CLI 模式
docker build --target cli -t maigret-cli .
docker run maigret-cli <用戶名稱> --html
```

---

## 🚀 快速開始

### CLI

```bash
# 查詢單一用戶名稱（預設查流量前 500 名網站）
maigret <用戶名稱>

# 只查臺灣站點（89 個）
maigret <用戶名稱> --tags taiwan

# 同時查詢多個用戶名稱
maigret 名稱一 名稱二 名稱三

# 輸出 HTML 報告（中英對照）
maigret <用戶名稱> --html

# 輸出 CSV 報告（中文標頭）
maigret <用戶名稱> --csv

# 使用代理伺服器
maigret <用戶名稱> --proxy socks5://127.0.0.1:1080

# 透過 Tor 查詢（含 .onion 站點）
maigret <用戶名稱> --tor-proxy socks5://127.0.0.1:9050
```

### 網頁 UI

```bash
maigret --web 5000
# 瀏覽器開啟 http://127.0.0.1:5000
```

---

## 🌐 全繁體中文網頁介面

### 快速篩選列

| 按鈕 | 功能 |
|---|---|
| 🇹🇼 只查臺灣站 | 自動套用 --tags taiwan，掃描 89 個臺灣本土站點 |
| 查前 500 站 | 設定為流量前 500 名（預設值） |
| 查全部站點 | 啟用全庫掃描（約 3,200+ 站） |
| ✕ 清除篩選 | 重置所有篩選條件 |

### 查詢類型

- 👤 使用者名稱（Username）
- ✉️ Email
- 🏷️ 暱稱（Nickname）

### 結果頁

- 帳號數量統計列（找到 / 完成報告 / 搜尋目標）
- 狀態說明區塊（預設展開，說明 Available / Unknown 等狀態意義，避免誤解）
- 各目標報告可折疊展開，點擊標題列切換
- 帳號關聯圖（Pyvis 互動式圖形）

### 報告下載

| 格式 | 說明 |
|---|---|
| CSV | 中英對照標頭，可直接以 Excel / Numbers 開啟 |
| Excel (.xlsx) | 格式化報告：欄寬調整、凍結標頭、自動篩選、說明工作表 |
| JSON | 完整原始資料（NDJSON 格式） |
| HTML | 中英對照欄位，可用瀏覽器列印 / 另存 PDF（Ctrl+P） |

---

## 📊 Excel 報告格式說明

| 欄 | 欄位名稱 | 格式 |
|---|---|---|
| A | 使用者名稱 | — |
| B | 站點名稱 | — |
| C | 站點中文名稱 | 縮小字型以適合欄寬 |
| D | 站點首頁 | — |
| E | 個人頁網址 | — |
| F | 帳號狀態（英文） | 置中 |
| G | 帳號狀態說明（中文） | 置中，欄寬 35 |
| H | HTTP 狀態碼 | 置中 |
| I | HTTP 說明 | 置中 |

附加「狀態說明」工作表，列出各狀態代碼的意義，避免誤解 Available（查無帳號）與 Unknown（無法判斷）等狀態。

---

## 🇹🇼 臺灣站點支援（89 個）

以 --tags taiwan 或網頁 UI「只查臺灣站」按鈕篩選。

### 社群 / 論壇

| 站點 | 說明 | 防護機制 |
|---|---|---|
| Dcard | 臺灣最大匿名社群平台 | TLS 指紋偽裝 |
| 巴哈姆特（Bahamut） | 臺灣最大遊戲社群 | TLS 指紋偽裝 |
| Mobile01 | 臺灣最大科技討論區 | TLS 指紋偽裝 |
| 伊莉討論區（Eyny） | 臺灣綜合論壇 | SHA-256 PoW 自動解題 |
| 背包客棧（Backpackers） | 臺灣最大自助旅行論壇 | — |

### 購物 / 活動

| 站點 | 說明 |
|---|---|
| 露天市集（Ruten） | 臺灣最大網路拍賣平台 |
| KKTIX | 活動售票平台（子域名格式） |
| Accupass 活動通 | 活動主辦單位頁面 |
| 嘖嘖（Zeczec） | 臺灣群眾募資平台 |

### 媒體 / 創作

| 站點 | 說明 |
|---|---|
| T客邦（TechBang） | 科技媒體作者頁 |
| 女人迷（Womany） | 性別議題媒體 |
| 報導者（TWReporter） | 非營利調查報導 |
| iThome 電腦報 | 臺灣 IT 媒體 |
| 關鍵評論網（TNL） | 多語言新聞評論平台 |

### 知識 / 寫作

| 站點 | 說明 |
|---|---|
| HackMD | Markdown 協作筆記平台 |
| 方格子（Vocus） | 付費訂閱寫作平台 |
| 愛料理（iCook） | 食譜社群 |

---

## 🔧 技術強化說明

### SHA-256 PoW 自動解題（PowSha256Checker）

部分基於 Discuz 架構的臺灣論壇（如伊莉討論區）使用 SHA-256 工作量證明防護。此機制在頁面內嵌 JavaScript 讓瀏覽器暴力破解 nonce，純 HTTP 客戶端因無法設置對應 Cookie 而被擋下。

本分支新增 PowSha256Checker，流程如下：

1. 偵測頁面中的 solvePoW 標記
2. 提取 challenge、ts、diff 參數
3. 在 Python 端暴力計算 nonce（diff=4 通常不到 0.1 秒）
4. 注入三個 Cookie 後重取頁面
5. 支援最多 5 輪重試

站點 data.json 中加入 "protection": ["pow_sha256"] 即可啟用（需安裝 curl_cffi）。

### Windows 相容性修正

- 報告下載路徑：使用 os.path.normpath 與 send_file，修正 Windows 反斜線路徑導致的 404 問題
- DNS 解析器：Web 模式強制採用系統 DNS（dns_resolver='threaded'），避免 Windows 上 aiodns 解析失敗
- PDF 套件：移除重量級 PDF 套件依賴，改以瀏覽器列印 HTML 產生 PDF（中文正常顯示）

### TLS 憑證寬鬆驗證

部分臺灣站點持有無效憑證，或使用者處於 TLS 攔截的企業 / ISP 環境。本分支在 CurlCffiChecker 中加入 verify: False，避免憑證問題造成誤報。

---

## ☁️ 雲端部署（Render.com）

本分支附有 render.yaml，可直接部署至 Render.com 免費方案：

1. 將本分支 Fork 到你的 GitHub 帳號
2. 至 render.com 新增 Web Service，選擇你的 GitHub repo
3. Render 會自動讀取 render.yaml，使用 Docker 建置 web stage
4. 部署完成後即可透過 Render 提供的網址使用網頁 UI

> 注意： Render 免費方案記憶體上限 512 MB，建議查詢時限制站點數量（使用「查前 500 站」或「只查臺灣站」），避免全庫掃描導致 OOM。

---

## 🤝 貢獻臺灣站點

1. 在 maigret/resources/data.json 中新增或修改站點設定
2. usernameClaimed 必須使用真實存在的帳號
3. usernameUnclaimed 設為確定不存在的值（如 noonewouldeverusethis7）
4. CLI 實際測試：真實帳號應顯示 found，不存在帳號應顯示 not found
5. 有 TLS 指紋要求加入 "protection": ["tls_fingerprint"]；有 PoW 防護加入 "protection": ["pow_sha256"]
6. 發送 Pull Request，附上測試截圖

---

## ⚠️ 免責聲明

本工具僅供教育與合法授權目的使用。使用者須自行遵守所在地區的適用法律（包括個人資料保護法等）。作者對任何濫用行為不承擔任何法律責任。

---

## 📄 授權條款

MIT © soxoj（上游）
臺灣加強版修改部分 © jasanlin177-hub

本分支依 MIT 授權條款釋出。
