#!/usr/bin/env bash
# ============================================================
# 甲骨文 Always Free A1.Flex 容量搶建腳本
# 用途：VM.Standard.A1.Flex 常因「Out of capacity」建立失敗，
#       本腳本每隔一段時間自動重試，成功建立即停止。
#
# 執行環境：Oracle Cloud Shell（Console 右上角圖示開啟）
#           已內建 oci CLI 且自動登入，不需另外設定 API 金鑰。
#
# 使用方式：
#   1. 依下方「必填參數」區塊填入你的環境資訊
#   2. chmod +x retry-launch-instance.sh
#   3. ./retry-launch-instance.sh
#   4. 可以直接關掉 Cloud Shell 分頁去做別的事，
#      Cloud Shell 閒置逾時後腳本會停止；若要長時間背景執行，
#      建議用 nohup（見下方說明）。
# ============================================================
set -uo pipefail

# ────────────────────────────────────────────────────────────
# 必填參數：請依註解說明，用 oci CLI 查出對應值後填入
# ────────────────────────────────────────────────────────────

# 1) Compartment OCID（根目錄 compartment，通常等於 tenancy OCID）
#    查詢指令：oci iam compartment list --compartment-id-in-subtree true --all
#    若只用 root compartment，可直接執行： oci iam availability-domain list
#    的輸出中會顯示你目前登入的 tenancy，root compartment OCID 與 tenancy OCID 相同。
#    也可在 Console 右上角個人選單 →Tenancy 查看。
COMPARTMENT_ID="ocid1.tenancy.oc1..xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 2) Availability Domain
#    查詢指令：oci iam availability-domain list
AVAILABILITY_DOMAIN="WkMx:AP-TOKYO-1-AD-1"

# 3) Subnet OCID（先前在 Console 建立的 public subnet）
#    查詢指令：oci network subnet list --compartment-id <COMPARTMENT_ID> --all
SUBNET_ID="ocid1.subnet.oc1.ap-tokyo-1.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 4) Image OCID（Canonical Ubuntu 22.04，ARM 版本）
#    查詢指令：
#    oci compute image list --compartment-id <COMPARTMENT_ID> \
#        --operating-system "Canonical Ubuntu" --operating-system-version "22.04" \
#        --shape "VM.Standard.A1.Flex" --all \
#        --query "data[*].{Name:\"display-name\", OCID:id}" --output table
IMAGE_ID="ocid1.image.oc1.ap-tokyo-1.xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"

# 5) SSH 公鑰內容（注意：是「登入 VM 用」的 SSH 公鑰，不是 API 簽章金鑰）
#    做法：把先前 Console 下載的 public key 檔案（.pub），
#    用 Cloud Shell 右上角工具列的「Upload」功能上傳進來，
#    上傳後預設會放在 Cloud Shell 的家目錄，例如 $HOME/ssh-key-xxxx.pub
#    上傳完成後，把下面路徑改成實際檔名。
#    若沒有現成的 .pub，也可以直接在 Cloud Shell 執行：
#      ssh-keygen -t rsa -b 4096 -f $HOME/maigret_vm_key -N ""
#    產生新的一組，這裡就填 $HOME/maigret_vm_key.pub，
#    並保留 $HOME/maigret_vm_key（私鑰）供之後 SSH 連線使用。
SSH_PUBLIC_KEY_PATH="$HOME/ssh-key-public.pub"   # 請改成你實際上傳/產生的 .pub 檔路徑

# 6) 資源規格（容量吃緊時，可先降規格搶建，之後在 Console 免重建直接調高）
OCPUS="4"
MEMORY_IN_GBS="24"

# 7) Instance 顯示名稱
DISPLAY_NAME="maigret-vps"

# 8) 每次重試間隔秒數（建議 60～120 秒，太頻繁可能觸發 API rate limit）
RETRY_INTERVAL_SECONDS=90

# ────────────────────────────────────────────────────────────
# 以下不需修改
# ────────────────────────────────────────────────────────────

# 防止重複啟動（Cloud Shell 斷線重連時常會誤重播 Enter，導致腳本被啟動兩次以上，
# 進而在容量釋出瞬間並行送出多個建立請求，有機會建出多台重複 VM）
LOCK_FILE="/tmp/retry-launch-instance.lock"
if [[ -f "$LOCK_FILE" ]]; then
    existing_pid=$(cat "$LOCK_FILE")
    if kill -0 "$existing_pid" 2>/dev/null; then
        echo "錯誤：偵測到已有一個本腳本正在執行中（PID ${existing_pid}）。"
        echo "為避免重複建立 VM，本次啟動已自動取消。"
        echo "如需強制重跑，請先執行：kill ${existing_pid} && rm -f ${LOCK_FILE}"
        exit 1
    else
        echo "偵測到過期的鎖檔（程序 ${existing_pid} 已不存在），自動清除後繼續。"
        rm -f "$LOCK_FILE"
    fi
fi
echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

if [[ "$COMPARTMENT_ID" == *xxxx* || "$SUBNET_ID" == *xxxx* || "$IMAGE_ID" == *xxxx* ]]; then
    echo "錯誤：請先填入上方「必填參數」區塊的實際 OCID，不能保留範例值。"
    exit 1
fi

if [[ ! -f "$SSH_PUBLIC_KEY_PATH" ]]; then
    echo "錯誤：找不到 SSH 公鑰檔案：$SSH_PUBLIC_KEY_PATH"
    echo "請確認路徑，或改用 --metadata 直接貼上公鑰字串。"
    exit 1
fi

attempt=0
echo "開始嘗試建立 VM（每 ${RETRY_INTERVAL_SECONDS} 秒重試一次，Ctrl+C 可中止）..."
echo "規格：${OCPUS} OCPU / ${MEMORY_IN_GBS} GB RAM，AD：${AVAILABILITY_DOMAIN}"
echo ""

while true; do
    attempt=$((attempt + 1))
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[${timestamp}] 第 ${attempt} 次嘗試..."

    result=$(oci compute instance launch \
        --compartment-id "$COMPARTMENT_ID" \
        --availability-domain "$AVAILABILITY_DOMAIN" \
        --shape "VM.Standard.A1.Flex" \
        --shape-config "{\"ocpus\": ${OCPUS}, \"memoryInGBs\": ${MEMORY_IN_GBS}}" \
        --image-id "$IMAGE_ID" \
        --subnet-id "$SUBNET_ID" \
        --display-name "$DISPLAY_NAME" \
        --assign-public-ip true \
        --metadata "{\"ssh_authorized_keys\": \"$(cat "$SSH_PUBLIC_KEY_PATH")\"}" \
        --wait-for-state RUNNING \
        --max-wait-seconds 120 \
        2>&1)

    if echo "$result" | grep -qi '"lifecycle-state": "RUNNING"'; then
        echo ""
        echo "════════════════════════════════════════════"
        echo "✅ 建立成功！VM 已進入 RUNNING 狀態。"
        echo "════════════════════════════════════════════"
        instance_id=$(echo "$result" | grep -o '"id": *"[^"]*"' | head -1 | sed 's/.*"id": *"\(.*\)"/\1/')
        echo "Instance OCID: ${instance_id}"
        echo ""
        echo "查詢 Public IP，請執行："
        echo "  oci compute instance list-vnics --instance-id ${instance_id} --query 'data[0].\"public-ip\"' --raw-output"
        break
    fi

    if echo "$result" | grep -qi "Out of capacity\|OutOfCapacity"; then
        echo "  → 容量不足（Out of capacity），${RETRY_INTERVAL_SECONDS} 秒後重試。"
    elif echo "$result" | grep -qi "LimitExceeded\|QuotaExceeded"; then
        echo "  → 額度已達上限（LimitExceeded）。請檢查是否已有其他 A1 執行個體佔用免費額度。"
        echo "$result"
        break
    else
        echo "  → 發生非預期錯誤，內容如下："
        echo "$result"
        echo "  → ${RETRY_INTERVAL_SECONDS} 秒後重試（如持續發生相同錯誤，請中止並檢查參數設定）。"
    fi

    sleep "$RETRY_INTERVAL_SECONDS"
done
