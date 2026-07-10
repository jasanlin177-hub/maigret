#!/usr/bin/env bash
# ============================================================
# Maigret 甲骨文 VPS 初始化腳本
# 用途：全新 Ubuntu VM 建好後，執行本腳本完成系統環境準備
# 使用方式：
#   1. SSH 連進 VM： ssh -i <你的私鑰> ubuntu@<VM_公網IP>
#   2. 上傳本腳本，或直接貼上內容執行
#   3. chmod +x setup-vm.sh && ./setup-vm.sh
# ============================================================
set -euo pipefail

echo "=== [1/5] 更新系統套件 ==="
sudo apt-get update -y
sudo apt-get upgrade -y

echo "=== [2/5] 安裝 Docker 與 Docker Compose ==="
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com | sudo sh
    sudo usermod -aG docker "$USER"
    echo ">> Docker 安裝完成。請注意：需要重新登入 SSH 才能免 sudo 使用 docker 指令。"
else
    echo ">> Docker 已安裝，略過。"
fi

if ! docker compose version &> /dev/null; then
    sudo apt-get install -y docker-compose-plugin
fi

echo "=== [3/5] 建立 Swap（避免建置映像檔時記憶體不足） ==="
if [ ! -f /swapfile ]; then
    sudo fallocate -l 4G /swapfile
    sudo chmod 600 /swapfile
    sudo mkswap /swapfile
    sudo swapon /swapfile
    echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
    echo ">> 已建立 4GB swap。"
else
    echo ">> Swap 已存在，略過。"
fi

echo "=== [4/5] 開放防火牆連接埠（OS 層 iptables） ==="
# 甲骨文 Ubuntu 映像檔預設會用 iptables 擋掉 80/443，
# 即使在 Console 的 Security List 已開放，這裡也要再開一次，否則連不進去。
sudo iptables -I INPUT -p tcp --dport 80  -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT -p tcp --dport 22  -j ACCEPT
sudo netfilter-persistent save 2>/dev/null || sudo iptables-save | sudo tee /etc/iptables/rules.v4 > /dev/null || true

echo "=== [5/5] 完成！ ==="
cat <<'EOF'

────────────────────────────────────────────────────
下一步：
1. 【必做】到甲骨文 Console → VM 執行個體 → 子網路 → Security List
   新增 Ingress Rule 開放 TCP 80 與 443（來源 0.0.0.0/0）
   （這一步在 Console 網頁做，本腳本無法代勞）

2. 重新登入 SSH 一次（讓 docker 群組生效）：
   exit
   ssh -i <你的私鑰> ubuntu@<VM_公網IP>

3. 執行 deploy.sh 進行實際部署
────────────────────────────────────────────────────
EOF
