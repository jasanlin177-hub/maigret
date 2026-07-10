# Maigret 甲骨文 VPS 部署指南

本資料夾包含將 Maigret 從 Render 搬遷至甲骨文 Always Free VPS 所需的全部腳本。
甲骨文帳號註冊、VM 建立為手動步驟（需本人身分驗證），完成後接續本指南。

---

## 前置：建立 VM 執行個體（甲骨文 Console 網頁操作）

1. 登入甲骨文 Console → **Compute → Instances → Create Instance**
2. **Image**：選擇 `Canonical Ubuntu 22.04`
3. **Shape**：點「Change Shape」→ 選 `Ampere` 系列 → `VM.Standard.A1.Flex`
   - 務必確認畫面標示 **"Always Free-eligible"**
   - OCPU 設為 `4`、記憶體設為 `24 GB`
4. **SSH 金鑰**：選「產生金鑰配對」，下載私鑰（`.key` 檔），妥善保存，之後 SSH 連線要用
5. 點「Create」，等待狀態變成 **Running**（約 1～2 分鐘）
6. 記下 VM 的 **Public IP Address**

> ⚠️ **常見狀況：建立失敗，錯誤訊息為「Out of capacity」**
> `VM.Standard.A1.Flex` 是熱門的免費 ARM 機型，部分地區常出現資源調度不足，
> 屬甲骨文平台本身問題，與你的設定無關。
> 若遇到此狀況，可使用 [`retry-launch/`](retry-launch/README.md) 資料夾內的自動重試腳本，
> 透過 Cloud Shell 定時嘗試建立，成功即自動停止，不需自己盯著手動重試。

## 前置：開放防火牆連接埠（甲骨文 Console 網頁操作）

1. 進入該 VM 詳細頁 → 找到所屬 **Subnet** → 點進去 → **Security List**
2. **Add Ingress Rules**，新增兩條：
   - Source CIDR: `0.0.0.0/0`　Protocol: TCP　Destination Port: `80`
   - Source CIDR: `0.0.0.0/0`　Protocol: TCP　Destination Port: `443`

> ⚠️ 這一步很多人會漏掉：甲骨文的防火牆有兩層——Console 的 Security List（雲端層）+ VM 內部的 iptables（系統層）。
> 兩層都要開，其中系統層已包含在 `setup-vm.sh` 腳本中自動處理。

---

## 步驟 1：SSH 連線進 VM

```bash
chmod 600 你的私鑰檔.key
ssh -i 你的私鑰檔.key ubuntu@<VM_公網IP>
```

## 步驟 2：下載並執行系統初始化腳本

```bash
curl -o setup-vm.sh https://raw.githubusercontent.com/jasanlin177-hub/maigret/main/deploy/oracle/setup-vm.sh
chmod +x setup-vm.sh
./setup-vm.sh
```

執行完畢後，依提示**重新登入 SSH 一次**（讓 docker 群組權限生效）：

```bash
exit
ssh -i 你的私鑰檔.key ubuntu@<VM_公網IP>
```

## 步驟 3：部署 Maigret

```bash
curl -o deploy.sh https://raw.githubusercontent.com/jasanlin177-hub/maigret/main/deploy/oracle/deploy.sh
chmod +x deploy.sh
./deploy.sh
```

> 此腳本會自動把專案 clone 到 `~/maigret`，並在 `~/maigret/deploy/oracle` 建置、啟動容器。

首次執行約需 3～5 分鐘（下載映像檔 + 建置）。完成後瀏覽器開啟：

```
http://<VM_公網IP>
```

即可看到 Maigret 網頁介面。

---

## 之後如何更新（改完程式碼、git push 之後）

VPS 更新方式與 Render 不同，**不會自動部署**，需手動執行一次：

```bash
ssh -i 你的私鑰檔.key ubuntu@<VM_公網IP>
~/maigret/deploy/oracle/deploy.sh
```

## 若要換成自己的網域（有 HTTPS，取代目前的 IP 直連）

1. 網域 DNS 設定一筆 **A 記錄**指向 VM 的 Public IP
2. 編輯 `~/maigret/deploy/oracle/Caddyfile`，改為：
   ```
   maigret.你的網域.com {
       reverse_proxy maigret:5000
   }
   ```
3. 重新啟動 Caddy：
   ```bash
   cd ~/maigret/deploy/oracle
   docker compose restart caddy
   ```
   Caddy 會自動向 Let's Encrypt 申請免費憑證，全程免手動。

---

## Render 轉址銜接規劃（VPS 穩定運作後再做）

為避免舊網址 `maigret-x963.onrender.com` 直接失效造成同仁找不到工具，
待 VPS 確認穩定後，將 Render 服務改為單純的轉址頁（3 秒自動跳轉至 VPS 新網址），
掛置 2～4 週緩衝期後再關閉 Render 服務。此部分待 VPS 上線後再另行提供轉址頁程式碼。

---

## 常用維運指令

> 以下指令皆需先 `cd ~/maigret/deploy/oracle`

| 目的 | 指令 |
|---|---|
| 查看即時日誌 | `docker logs -f maigret-web` |
| 查看容器狀態 | `docker compose ps` |
| 重新啟動服務 | `docker compose restart` |
| 停止服務 | `docker compose down` |
| 檢查記憶體用量 | `free -h` |
| 檢查磁碟空間 | `df -h` |

## 疑難排解

| 現象 | 可能原因 | 處理方式 |
|---|---|---|
| SSH 連不進去 | Security List 未開放 22 埠，或私鑰權限錯誤 | 確認 Security List 已含 22 埠；`chmod 600` 私鑰檔 |
| 瀏覽器打不開網頁 | 80/443 埠未在 Security List 開放 | 回到前置步驟檢查 Security List |
| 瀏覽器打不開網頁（Security List 已開） | VM 內 iptables 未開放 | 重新執行 `setup-vm.sh` 的第 4 步 |
| `docker: permission denied` | 尚未重新登入 SSH | 執行 `exit` 後重新 SSH 連線 |
| 建置時當機或極慢 | 記憶體不足 | 確認 `setup-vm.sh` 已建立 4GB swap（`free -h` 查看） |
