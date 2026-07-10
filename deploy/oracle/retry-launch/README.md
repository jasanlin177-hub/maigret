# 甲骨文 VM.Standard.A1.Flex 容量搶建腳本

`VM.Standard.A1.Flex`（Always Free 24GB ARM 機型）在部分地區經常出現
**「Out of capacity」** 建立失敗，這是甲骨文平台本身資源調度問題，與你的帳號、設定無關。
本腳本會自動每隔一段時間重試建立，直到成功為止。

---

## 為什麼用 Cloud Shell，不用本機安裝 OCI CLI？

Console 右上角有一個 **`>_` 圖示（Cloud Shell）**，點下去會開啟一個瀏覽器內建的終端機：

- 已經自動登入你的帳號權限，**不需要另外產生 API 簽章金鑰**
- `oci` 指令已預先安裝好，開啟即可直接使用
- 免費，且與建立 VM 在同一個帳號環境內操作最不容易出錯

本機安裝 OCI CLI 需要額外設定 API Key、config 檔案，對這次任務來說是不必要的麻煩，故不建議。

---

## 操作步驟

### 步驟 1：開啟 Cloud Shell

Console 右上角工具列，點擊 **`>_`** 圖示，等待終端機初始化（約 30 秒\~1 分鐘）。

### 步驟 2：上傳腳本

Cloud Shell 視窗右上角有 **「Upload」**（上傳）按鈕，把 `retry-launch-instance.sh` 這個檔案上傳進去。

或者，也可以直接在 Cloud Shell 裡用 `cat > retry-launch-instance.sh` 貼上內容後按 `Ctrl+D` 存檔。

### 步驟 3：上傳（或產生）SSH 公鑰

**方式 A**：把先前下載的 public key（`.pub`）用同一個「Upload」按鈕上傳進 Cloud Shell。

**方式 B**：如果找不到 `.pub` 檔案，直接在 Cloud Shell 裡重新產生一組專用於這台 VM 的金鑰：

```bash
ssh-keygen -t rsa -b 4096 -f $HOME/maigret_vm_key -N ""
```

這會產生 `maigret_vm_key`（私鑰）與 `maigret_vm_key.pub`（公鑰）兩個檔案。
**建立成功後，記得把私鑰下載到本機**（Cloud Shell 右上角也有「Download」功能），
之後才能用它 SSH 連進 VM。

### 步驟 4：查詢必填參數的 OCID

依序在 Cloud Shell 執行以下指令，把結果填入 `retry-launch-instance.sh` 開頭的「必填參數」區塊：

```bash
# 1) 查 Compartment OCID（root compartment）
oci iam compartment list --compartment-id-in-subtree true --all --query "data[*].{Name:name, OCID:id}" --output table
# 若要用最上層 root compartment，OCID 可從右上角個人選單 → Tenancy 頁面取得

# 2) 查 Availability Domain
oci iam availability-domain list

# 3) 查 Subnet OCID（先前在 Console 建立的 public subnet，名稱如 subnet-20260710-1113）
oci network subnet list --compartment-id <上面查到的 COMPARTMENT_ID> --all --query "data[*].{Name:\"display-name\", OCID:id}" --output table

# 4) 查 Ubuntu 22.04 ARM 版 Image OCID
oci compute image list \
    --compartment-id <COMPARTMENT_ID> \
    --operating-system "Canonical Ubuntu" \
    --operating-system-version "22.04" \
    --shape "VM.Standard.A1.Flex" \
    --all \
    --query "data[*].{Name:\"display-name\", OCID:id}" --output table
```

### 步驟 5：編輯腳本，填入查到的值

用 Cloud Shell 內建的編輯器開啟腳本：

```bash
nano retry-launch-instance.sh
```

把開頭「必填參數」區塊的 6 個變數改成步驟 4 查到的實際值，`Ctrl+O` 存檔、`Ctrl+X` 離開。

### 步驟 6：執行

```bash
chmod +x retry-launch-instance.sh
./retry-launch-instance.sh
```

腳本會持續顯示嘗試紀錄，例如：

```
[2026-07-10 15:30:00] 第 1 次嘗試...
  → 容量不足（Out of capacity），90 秒後重試。
[2026-07-10 15:31:30] 第 2 次嘗試...
  → 容量不足（Out of capacity），90 秒後重試。
...
✅ 建立成功！VM 已進入 RUNNING 狀態。
```

成功後會印出 Instance OCID，並附上查詢 Public IP 的指令。

---

## 想長時間背景執行、不怕 Cloud Shell 逾時中斷？

Cloud Shell 本身有閒置逾時限制（約 20 分鐘無操作會斷線），若想讓腳本持續跑更久：

```bash
nohup ./retry-launch-instance.sh > retry.log 2>&1 &
```

之後可以關閉 Cloud Shell 分頁，之後重新打開 Cloud Shell 執行以下指令查看進度：

```bash
cat retry.log
```

> 註：Cloud Shell 本身也並非「永久背景執行環境」，若甲骨文判定 session 已結束，
> 用 `nohup` 啟動的程序仍可能被一併終止。若腳本跑了很久（超過數小時）都沒成功，
> 建議改成白天分次手動短暫執行（例如凌晨時段），比長時間掛著更省事。

---

## 常見錯誤排解

| 錯誤訊息 | 原因 | 處理方式 |
|---|---|---|
| `Out of capacity` | 該可用區域此刻沒有足夠 A1 資源 | 腳本會自動重試，屬正常現象，耐心等待 |
| `LimitExceeded` / `QuotaExceeded` | 帳號的 Always Free A1 額度（4 OCPU/24GB）已被其他執行個體佔用 | 檢查 Console 是否已有其他 A1 VM，刪除閒置的再試 |
| 找不到 `.pub` 檔案 | `SSH_PUBLIC_KEY_PATH` 路徑設定錯誤 | 確認檔案已上傳到 Cloud Shell，路徑填正確 |
| `NotAuthorizedOrNotFound` | Compartment / Subnet / Image OCID 填錯或跨 compartment | 重新用步驟 4 的指令核對 OCID 是否正確複製完整 |
