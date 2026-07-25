"""
通用 OpenGraph / meta 標籤擷取器。

socid_extractor 僅對少數站點寫死解析規則（如 Facebook 專屬的 og:title/og:image
規則），其餘上千個站點若沒有對應規則，即使頁面本身含有標準的 OpenGraph meta
標籤，也擷取不到頭像、全名等資訊。

本模組不依賴任何站點專屬規則，對任意 HTML 頁面通用解析下列標準標籤：
    - og:image / twitter:image / twitter:image:src / apple-touch-icon
    - og:title / twitter:title（作為 fullname 的備援來源）
    - og:description / twitter:description

輸出欄位刻意採用與 socid_extractor 相同的命名（image / fullname /
description），使下游程式碼（報告產生、頭像聚類等）不需要區分資料來源。

僅在 socid_extractor 沒有擷取到對應欄位時，才由本模組補上，兩者互為備援
而非互相覆蓋。
"""

from typing import Dict

try:
    import lxml.html
except ImportError:  # pragma: no cover - lxml 已是 pyproject.toml 既有依賴
    lxml = None  # type: ignore[assignment]


def _first_meta_content(tree, selectors) -> str:
    """依序嘗試多個 XPath 選擇器，回傳第一個非空的 content/href 屬性值。"""
    for xpath in selectors:
        try:
            matches = tree.xpath(xpath)
        except Exception:
            continue
        for value in matches:
            value = (value or "").strip()
            if value:
                return value
    return ""


def extract_opengraph_data(html_text: str) -> Dict[str, str]:
    """
    從任意 HTML 頁面通用擷取 OpenGraph / meta 標籤資訊。

    Args:
        html_text: 頁面原始 HTML 字串。

    Returns:
        僅包含實際擷取到內容的欄位（image / fullname / description），
        擷取不到的欄位不會出現在回傳的 dict 中，避免以空字串覆蓋既有資料。
    """
    if lxml is None or not html_text:
        return {}

    try:
        tree = lxml.html.fromstring(html_text)
    except Exception:
        return {}

    result: Dict[str, str] = {}

    image = _first_meta_content(
        tree,
        [
            "//meta[@property='og:image']/@content",
            "//meta[@property='og:image:url']/@content",
            "//meta[@name='twitter:image']/@content",
            "//meta[@name='twitter:image:src']/@content",
            "//link[@rel='apple-touch-icon']/@href",
            "//link[@rel='apple-touch-icon-precomposed']/@href",
        ],
    )
    if image:
        result["image"] = image

    fullname = _first_meta_content(
        tree,
        [
            "//meta[@property='og:title']/@content",
            "//meta[@name='twitter:title']/@content",
        ],
    )
    if fullname:
        result["fullname"] = fullname

    description = _first_meta_content(
        tree,
        [
            "//meta[@property='og:description']/@content",
            "//meta[@name='twitter:description']/@content",
            "//meta[@name='description']/@content",
        ],
    )
    if description:
        result["description"] = description

    return result


def merge_opengraph_fallback(
    extracted_ids_data: Dict[str, str], html_text: str
) -> Dict[str, str]:
    """
    以 OpenGraph 通用擷取結果補齊既有的 extracted_ids_data，
    僅填補既有資料中缺少的欄位，不覆蓋 socid_extractor 已擷取到的內容。

    Args:
        extracted_ids_data: socid_extractor 擷取的原始結果（可能為空 dict）。
        html_text: 頁面原始 HTML 字串。

    Returns:
        補齊後的 dict（就地修改並回傳同一個物件，方便呼叫端直接串接使用）。
    """
    og_data = extract_opengraph_data(html_text)
    for key, value in og_data.items():
        if not extracted_ids_data.get(key):
            extracted_ids_data[key] = value
    return extracted_ids_data
