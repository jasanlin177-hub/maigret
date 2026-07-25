"""
頭像關聯聚類（Avatar Correlation Clustering）。

單一查詢常會在數百個站點中找到同名帳號，但「同名」不代表「同一人」——
可能只是巧合搶到相同用戶名稱的不同人。本模組透過比對各帳號頭像的視覺
相似度（dHash 差異雜湊 + 漢明距離），將高度相似頭像的帳號歸為同一群組，
輔助偵查人員判斷「這些帳號很可能屬於同一人」。

演算法：dHash（Difference Hash）
    將圖片縮成 9x8 灰階小圖，逐列比較相鄰像素亮度大小，產生 64-bit 雜湊值。
    圖片視覺上越相似，兩者雜湊值的漢明距離（不同位元數）越小。
    相較於 MD5 等加密雜湊，dHash 對縮圖、輕微壓縮、格式轉換等視覺無感的
    改動不敏感，適合用來判斷「兩張圖看起來是不是同一張」。

僅依賴 Pillow（PIL），不需要額外安裝 OpenCV 或 imagehash 套件。
"""

from __future__ import annotations

import asyncio
import io
import logging
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import aiohttp
from aiohttp import TCPConnector
from aiohttp.resolver import ThreadedResolver

try:
    from PIL import Image
except ImportError:  # pragma: no cover - Pillow 為選用依賴
    Image = None  # type: ignore[assignment]


# dHash 漢明距離門檻：兩張圖的 64-bit 雜湊值有幾個 bit 不同即視為「相似」。
# 值越小越嚴格（誤判率低、漏判率高）；經驗上 0～10 為高信心相似，
# 11～15 為可能相似，本模組預設採嚴格門檻，避免誤導偵查方向。
DEFAULT_HAMMING_THRESHOLD = 10

# 「同一張圖被過多站點共用」的判定門檻。
#
# 實測發現許多平台在使用者未設定頭像時會回傳通用預設圖（灰色人形剪影等），
# 或同一服務的多個地區站台共用同一張系統圖。這類頭像會讓完全不相干的帳號
# 被誤判為「同一人」，對偵查是危險的誤導。
#
# 同一個雜湊值出現在超過此數量的站點上時，視為預設圖／系統圖而排除。
#
# 注意不能設得太嚴（例如 1）：dHash 是縮到 8x8 灰階後比對，對尺寸與輕度
# 壓縮極不敏感，所以「同一個人在多個平台使用同一張照片」時，即使各平台
# 提供的圖片尺寸不同，算出的雜湊值往往**完全相同**——這正是本功能要偵測
# 的目標，不該被當成預設圖濾掉。
#
# 反之平台預設圖的特徵是「大量站點」共用（實測 OP.GG 家族達 17 站）。
# 取 6 可區分兩者：真人跨平台重複使用同一張照片通常在 2～6 站，
# 超過此數更可能是系統預設圖。真正的預設圖另有 URL 特徵過濾與
# 低資訊量過濾兩道防線把關，此門檻僅作為最後兜底。
DEFAULT_MAX_SHARED_SITES = 6

# 網址中出現這些關鍵字時，代表該圖片是平台預設頭像或平台 logo，
# 而非使用者自訂頭像，一律排除。
#
# 這比單純比對圖像更可靠：許多平台的預設圖有明確的命名慣例
# （Mastodon 的 avatars/original/missing.png、MixCloud 的
# defaults/users/1.png、TradingView 的 logo-preview.png 等），
# 直接從 URL 就能判定，不需要下載後才發現是誤判。
_DEFAULT_AVATAR_URL_MARKERS = (
    "missing",
    "default",
    "placeholder",
    "blank",
    "anonymous",
    "no-avatar",
    "noavatar",
    "no_avatar",
    "avatar-default",
    "gravatar.com/avatar/00000",
    "logo-preview",
    "/logos/",
    "identicon",
    "mystery",
    "unknown-user",
    "guest",
)

# 資訊量過低的雜湊值，代表圖片幾乎無視覺特徵（純色、全白、空白佔位圖），
# 無法作為身分關聯依據，一律排除。
# dHash 為 0 表示整張圖沒有任何相鄰亮度變化（純色）；
# 全 1（2^64-1）則為另一個極端。
_DEGENERATE_HASHES = {0, (1 << 64) - 1}

# 雜湊值中位元 1 的數量若過少或過多，代表圖片對比極低、視覺特徵不足。
#
# 門檻經實測校準：以 151 張真實頭像取樣，位元數中位數為 25、平均 24.7。
# 平台預設頭像（大片單色背景 + 小圖案，如 YouTube／Facebook／Threads／
# Twitch／Snapchat 的預設灰人像）位元數集中在 13～16，且彼此漢明距離很小
# ——但那是「共同的低資訊量」造成的假性相似，不是圖案真的相同。
# 若不濾除，這些完全不相干的帳號會被誤判為同一人。
#
# 取 18 為分界可精準切掉該低資訊量區間，同時保留約 84% 的正常頭像。
MIN_HASH_BIT_VARIANCE = 18

# 單張頭像下載大小上限（bytes），避免異常大檔案拖垮小記憶體主機
MAX_IMAGE_BYTES = 5 * 1024 * 1024  # 5MB

# 同時下載頭像的並行數上限（VPS 記憶體有限，避免一次性佔用過多連線）
MAX_CONCURRENT_FETCHES = 5

# 單次下載逾時秒數
FETCH_TIMEOUT_SECONDS = 10


@dataclass
class AvatarCluster:
    """一組被判定為視覺相似頭像的站點集合。"""

    cluster_id: int
    site_names: List[str] = field(default_factory=list)
    representative_hash: Optional[int] = None


def compute_dhash(image_bytes: bytes, hash_size: int = 8) -> Optional[int]:
    """
    計算圖片的 dHash（差異雜湊）。

    Args:
        image_bytes: 圖片原始位元組資料。
        hash_size: 雜湊邊長，預設 8（產生 8x8=64 bit 雜湊值）。

    Returns:
        64-bit 整數雜湊值；圖片無法解析時回傳 None。
    """
    if Image is None or not image_bytes:
        return None

    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            # 縮成 (hash_size+1) x hash_size 灰階小圖，
            # 多出的一欄用來跟下一欄比較亮度大小
            img = img.convert("L").resize(
                (hash_size + 1, hash_size), Image.Resampling.LANCZOS
            )
            pixels = list(img.getdata())
    except Exception:
        return None

    bits = 0
    for row in range(hash_size):
        row_start = row * (hash_size + 1)
        for col in range(hash_size):
            bits <<= 1
            left = pixels[row_start + col]
            right = pixels[row_start + col + 1]
            if left > right:
                bits |= 1
    return bits


def is_default_avatar_url(image_url: str) -> bool:
    """
    從網址判斷該圖片是否為平台預設頭像／平台 logo。

    許多平台的預設圖有明確命名慣例（missing.png、defaults/users/1.png、
    logo-preview.png 等），直接由網址判定可在下載前就排除，
    既省頻寬也避免這類圖片污染關聯分析結果。
    """
    if not image_url:
        return True
    url_lower = image_url.lower()
    return any(marker in url_lower for marker in _DEFAULT_AVATAR_URL_MARKERS)


def hamming_distance(hash_a: int, hash_b: int) -> int:
    """計算兩個雜湊值的漢明距離（不同的 bit 數）。"""
    return bin(hash_a ^ hash_b).count("1")


async def _fetch_and_hash(
    session: aiohttp.ClientSession,
    site_name: str,
    image_url: str,
    semaphore: asyncio.Semaphore,
    logger: logging.Logger,
) -> Optional[int]:
    """下載單張頭像並計算 dHash，任何失敗都回傳 None（不中斷整體流程）。"""
    if not image_url or not image_url.startswith(("http://", "https://")):
        return None

    # 由網址即可判定的平台預設圖／logo，在下載前就跳過
    if is_default_avatar_url(image_url):
        logger.debug(f"略過疑似平台預設頭像（{site_name}）：{image_url}")
        return None

    async with semaphore:
        try:
            async with session.get(
                image_url,
                timeout=aiohttp.ClientTimeout(total=FETCH_TIMEOUT_SECONDS),
                ssl=False,
            ) as resp:
                if resp.status != 200:
                    return None
                content_length = resp.content_length
                if content_length and content_length > MAX_IMAGE_BYTES:
                    return None

                # 注意：resp.content.read(n) 遇到分段傳輸（chunked transfer）時
                # 可能提早返回、讀不滿完整內容，導致 PIL 解析時出現
                # "image file is truncated"。改用 iter_chunked 迴圈累積，
                # 直到真正讀到 EOF 或超過大小上限為止。
                chunks = bytearray()
                async for chunk in resp.content.iter_chunked(65536):
                    chunks.extend(chunk)
                    if len(chunks) > MAX_IMAGE_BYTES:
                        return None
                data = bytes(chunks)
        except Exception as e:
            logger.debug(f"頭像下載失敗（{site_name}）：{e}")
            return None

    return compute_dhash(data)


async def compute_avatar_hashes(
    site_avatars: Dict[str, str],
    logger: Optional[logging.Logger] = None,
) -> Dict[str, int]:
    """
    平行下載多個站點的頭像並計算 dHash。

    Args:
        site_avatars: {站點名稱: 頭像網址} 對照表。
        logger: 選用的 logger，預設使用模組層級 logger。

    Returns:
        {站點名稱: dHash 值} 對照表，僅包含成功計算雜湊的項目。
    """
    if Image is None:
        (logger or logging.getLogger(__name__)).warning(
            "Pillow 未安裝，略過頭像關聯聚類（pip install Pillow 以啟用此功能）"
        )
        return {}

    logger = logger or logging.getLogger(__name__)
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_FETCHES)

    # Windows 上預設的 aiodns/c-ares 解析器常出現 DNS 查詢失敗，
    # 改用 ThreadedResolver（走系統 getaddrinfo）與主查詢引擎採一致修法。
    connector = TCPConnector(resolver=ThreadedResolver())
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = {
            site_name: _fetch_and_hash(session, site_name, url, semaphore, logger)
            for site_name, url in site_avatars.items()
            if url
        }
        results = await asyncio.gather(*tasks.values())

    return {
        site_name: h
        for site_name, h in zip(tasks.keys(), results)
        if h is not None
    }


def _is_degenerate_hash(h: int) -> bool:
    """判斷雜湊值是否資訊量不足（純色、極低對比圖），無法作為關聯依據。"""
    if h in _DEGENERATE_HASHES:
        return True
    bit_count = bin(h).count("1")
    return bit_count < MIN_HASH_BIT_VARIANCE or bit_count > (
        64 - MIN_HASH_BIT_VARIANCE
    )


def filter_default_avatars(
    hashes: Dict[str, int],
    max_shared_sites: int = DEFAULT_MAX_SHARED_SITES,
    logger: Optional[logging.Logger] = None,
) -> Dict[str, int]:
    """
    排除平台預設頭像與無特徵圖片，避免誤判不相干帳號為「同一人」。

    兩類會被排除：
      1. 資訊量不足的圖（純色、空白佔位圖）
      2. 同一張圖被過多站點共用（平台預設頭像、同服務多地區站台共用系統圖）

    Args:
        hashes: {站點名稱: dHash 值} 對照表。
        max_shared_sites: 同一雜湊值出現超過幾個站點即視為預設圖。
        logger: 選用的 logger，會記錄被排除的項目供稽核。

    Returns:
        過濾後的 {站點名稱: dHash 值} 對照表。
    """
    logger = logger or logging.getLogger(__name__)

    hash_counts: Dict[int, int] = {}
    for h in hashes.values():
        hash_counts[h] = hash_counts.get(h, 0) + 1

    filtered: Dict[str, int] = {}
    for site_name, h in hashes.items():
        if _is_degenerate_hash(h):
            logger.debug(f"排除無特徵頭像（{site_name}）：雜湊值資訊量不足")
            continue
        if hash_counts[h] > max_shared_sites:
            logger.debug(
                f"排除疑似平台預設頭像（{site_name}）："
                f"同一張圖出現在 {hash_counts[h]} 個站點"
            )
            continue
        filtered[site_name] = h

    return filtered


def cluster_by_hash(
    hashes: Dict[str, int],
    threshold: int = DEFAULT_HAMMING_THRESHOLD,
) -> List[AvatarCluster]:
    """
    依漢明距離將站點頭像分群（貪婪聚類：逐一比對，距離小於門檻即歸入同群）。

    注意：呼叫前建議先以 filter_default_avatars() 排除平台預設頭像，
    否則共用同一張系統預設圖的無關帳號會被誤判為同一人。
    correlate_avatars() 已內建此過濾步驟。

    Args:
        hashes: {站點名稱: dHash 值} 對照表。
        threshold: 漢明距離門檻，小於等於此值視為相似。

    Returns:
        群組清單，僅包含成員數 >= 2 的群組（單一站點不構成「關聯」）。
    """
    assigned: Dict[str, int] = {}
    clusters: List[AvatarCluster] = []

    for site_name, h in hashes.items():
        matched_cluster: Optional[AvatarCluster] = None
        for cluster in clusters:
            if cluster.representative_hash is None:
                continue
            if hamming_distance(h, cluster.representative_hash) <= threshold:
                matched_cluster = cluster
                break

        if matched_cluster is not None:
            matched_cluster.site_names.append(site_name)
            assigned[site_name] = matched_cluster.cluster_id
        else:
            new_cluster = AvatarCluster(
                cluster_id=len(clusters) + 1,
                site_names=[site_name],
                representative_hash=h,
            )
            clusters.append(new_cluster)
            assigned[site_name] = new_cluster.cluster_id

    return [c for c in clusters if len(c.site_names) >= 2]


async def correlate_avatars(
    site_avatars: Dict[str, str],
    threshold: int = DEFAULT_HAMMING_THRESHOLD,
    max_shared_sites: int = DEFAULT_MAX_SHARED_SITES,
    logger: Optional[logging.Logger] = None,
) -> List[AvatarCluster]:
    """
    對外主要入口：輸入各站點的頭像網址，回傳視覺相似的頭像群組。

    流程：下載頭像 → 計算 dHash → 排除平台預設圖 → 依相似度分群。

    Args:
        site_avatars: {站點名稱: 頭像網址} 對照表（通常來自各站
            extract_ids_data 擷取出的 "image" 欄位）。
        threshold: 漢明距離門檻，見 DEFAULT_HAMMING_THRESHOLD 說明。
        max_shared_sites: 預設頭像判定門檻，見 DEFAULT_MAX_SHARED_SITES 說明。
        logger: 選用的 logger。

    Returns:
        群組清單，每組代表一批頭像視覺高度相似、可能屬於同一人的站點。
    """
    hashes = await compute_avatar_hashes(site_avatars, logger)
    hashes = filter_default_avatars(hashes, max_shared_sites, logger)
    return cluster_by_hash(hashes, threshold)
