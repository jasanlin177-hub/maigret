#!/usr/bin/env bash
# ============================================================
# Maigret 甲骨文 VPS 部署 / 更新腳本
# 首次部署與之後每次更新（git push 後）都執行這支
# 使用方式：
#   ~/maigret/deploy/oracle/deploy.sh
# ============================================================
set -euo pipefail

REPO_URL="https://github.com/jasanlin177-hub/maigret.git"
REPO_DIR="$HOME/maigret"
COMPOSE_DIR="$REPO_DIR/deploy/oracle"

echo "=== [1/3] 取得最新程式碼 ==="
if [ -d "$REPO_DIR/.git" ]; then
    cd "$REPO_DIR"
    git pull
else
    git clone "$REPO_URL" "$REPO_DIR"
fi

echo "=== [2/3] 建置並啟動容器 ==="
cd "$COMPOSE_DIR"
mkdir -p data/reports data/db caddy_data caddy_config
docker compose build
docker compose up -d

echo "=== [3/3] 完成，檢查容器狀態 ==="
docker compose ps

cat <<'EOF'

────────────────────────────────────────────────────
部署完成！確認方式：
  瀏覽器開啟 http://<VM_公網IP>（或你設定的網域）

常用指令（皆需先 cd ~/maigret/deploy/oracle）：
  查看即時日誌：  docker logs -f maigret-web
  重新啟動：      docker compose restart
  更新到最新版：  重新執行本腳本 ./deploy.sh
────────────────────────────────────────────────────
EOF
