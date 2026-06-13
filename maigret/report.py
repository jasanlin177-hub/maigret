import ast
import csv
import io
import json
import logging
import os
from datetime import datetime
from typing import Dict, Any

import xmind  # type: ignore[import-untyped]
from dateutil.tz import gettz
from dateutil.parser import parse as parse_datetime_str
from jinja2 import Template

from .checking import SUPPORTED_IDS
from .result import MaigretCheckStatus
from .sites import MaigretDatabase
from .utils import is_country_tag, CaseConverter, enrich_link_str


ADDITIONAL_TZINFO = {"CDT": gettz("America/Chicago")}
SUPPORTED_JSON_REPORT_FORMATS = [
    "simple",
    "ndjson",
]

"""
UTILS
"""


def filter_supposed_data(data):
    allowed_fields = ["fullname", "gender", "location", "age"]

    def _first(v):
        if isinstance(v, (list, tuple)):
            return v[0] if v else ""
        return v

    return {
        CaseConverter.snake_to_title(k): _first(v)
        for k, v in data.items()
        if k in allowed_fields
    }


def sort_report_by_data_points(results):
    return dict(
        sorted(
            results.items(),
            key=lambda x: len(
                (x[1].get('status') and x[1]['status'].ids_data or {}).keys()
            ),
            reverse=True,
        )
    )


"""
REPORTS SAVING
"""


def save_csv_report(filename: str, username: str, results: dict):
    # utf-8-sig 加入 BOM，Excel 開啟時自動識別 UTF-8 而不顯示亂碼
    with open(filename, "w", newline="", encoding="utf-8-sig") as f:
        generate_csv_report(username, results, f)


def save_txt_report(filename: str, username: str, results: dict):
    with open(filename, "w", encoding="utf-8") as f:
        generate_txt_report(username, results, f)


def save_html_report(filename: str, context: dict):
    template, _ = generate_report_template(is_pdf=False)
    filled_template = template.render(**context)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(filled_template)


PDF_EXTRA_HINT = (
    "PDF reports require the optional 'pdf' extra. "
    "Install it with: pip install 'maigret[pdf]'"
)


def save_pdf_report(filename: str, context: dict):
    # Imported lazily so that users without the optional 'pdf' extra
    # can still import maigret.report and use other report formats.
    try:
        from xhtml2pdf import pisa  # type: ignore[import-untyped]
    except ImportError as e:
        raise RuntimeError(PDF_EXTRA_HINT) from e

    template, css = generate_report_template(is_pdf=True)
    filled_template = template.render(**context)

    with open(filename, "w+b") as f:
        pisa.pisaDocument(io.StringIO(filled_template), dest=f, default_css=css)


def save_json_report(filename: str, username: str, results: dict, report_type: str):
    with open(filename, "w", encoding="utf-8") as f:
        generate_json_report(username, results, f, report_type=report_type)


class MaigretGraph:
    other_params: dict = {'size': 10, 'group': 3}
    site_params: dict = {'size': 15, 'group': 2}
    username_params: dict = {'size': 20, 'group': 1}

    def __init__(self, graph):
        self.G = graph

    def add_node(self, key, value, color=None):
        node_name = f'{key}: {value}'

        params = dict(self.other_params)
        if key in SUPPORTED_IDS:
            params = dict(self.username_params)
        elif value.startswith('http'):
            params = dict(self.site_params)

        params['title'] = node_name
        if color:
            params['color'] = color

        self.G.add_node(node_name, **params)
        return node_name

    def link(self, node1_name, node2_name):
        self.G.add_edge(node1_name, node2_name, weight=2)


def save_graph_report(filename: str, username_results: list, db: MaigretDatabase):
    import networkx as nx

    G: Any = nx.Graph()
    graph = MaigretGraph(G)

    base_site_nodes = {}
    site_account_nodes = {}
    processed_values: Dict[str, Any] = {}  # Track processed values to avoid duplicates

    for username, id_type, results in username_results:
        # Add username node, using normalized version directly if different
        norm_username = username.lower()
        username_node_name = graph.add_node(id_type, norm_username)

        for website_name, dictionary in results.items():
            if not dictionary or dictionary.get("is_similar"):
                continue

            status = dictionary.get("status")
            if not status or status.status != MaigretCheckStatus.CLAIMED:
                continue

            # base site node
            site_base_url = website_name
            if site_base_url not in base_site_nodes:
                base_site_nodes[site_base_url] = graph.add_node(
                    'site', site_base_url, color='#28a745'
                )  # Green color

            site_base_node_name = base_site_nodes[site_base_url]

            # account node
            account_url = dictionary.get('url_user', f'{site_base_url}/{norm_username}')
            account_node_id = f"{site_base_url}: {account_url}"
            if account_node_id not in site_account_nodes:
                site_account_nodes[account_node_id] = graph.add_node(
                    'account', account_url
                )

            account_node_name = site_account_nodes[account_node_id]

            # link username → account → site
            graph.link(username_node_name, account_node_name)
            graph.link(account_node_name, site_base_node_name)

            def process_ids(parent_node, ids):
                for k, v in ids.items():
                    if (
                        k.endswith('_count')
                        or k.startswith('is_')
                        or k.endswith('_at')
                        or k in 'image'
                    ):
                        continue

                    # Normalize value if string
                    norm_v = v.lower() if isinstance(v, str) else v
                    value_key = f"{k}:{norm_v}"

                    if value_key in processed_values:
                        ids_data_name = processed_values[value_key]
                    else:
                        v_data = v
                        if isinstance(v, str) and v.startswith('['):
                            try:
                                v_data = ast.literal_eval(v)
                            except Exception as e:
                                logging.error(e)
                                continue

                        if isinstance(v_data, list):
                            list_node_name = graph.add_node(k, site_base_url)
                            processed_values[value_key] = list_node_name
                            for vv in v_data:
                                data_node_name = graph.add_node(vv, site_base_url)
                                graph.link(list_node_name, data_node_name)

                                add_ids = {
                                    a: b for b, a in db.extract_ids_from_url(vv).items()
                                }
                                if add_ids:
                                    process_ids(data_node_name, add_ids)
                            ids_data_name = list_node_name
                        else:
                            ids_data_name = graph.add_node(k, norm_v)
                            processed_values[value_key] = ids_data_name

                            if 'username' in k or k in SUPPORTED_IDS:
                                new_username_key = f"username:{norm_v}"
                                if new_username_key not in processed_values:
                                    new_username_node_name = graph.add_node(
                                        'username', norm_v
                                    )
                                    processed_values[new_username_key] = (
                                        new_username_node_name
                                    )
                                    graph.link(ids_data_name, new_username_node_name)

                            add_ids = {
                                k: v for v, k in db.extract_ids_from_url(v).items()
                            }
                            if add_ids:
                                process_ids(ids_data_name, add_ids)

                    graph.link(parent_node, ids_data_name)

            if status.ids_data:
                process_ids(account_node_name, status.ids_data)

    # Remove overly long nodes
    nodes_to_remove = [node for node in G.nodes if len(str(node)) > 100]
    G.remove_nodes_from(nodes_to_remove)

    # Remove site nodes with only one connection
    single_degree_sites = [
        n for n, deg in G.degree() if n.startswith("site:") and deg <= 1
    ]
    G.remove_nodes_from(single_degree_sites)

    # Generate interactive visualization
    from pyvis.network import Network  # type: ignore[import-untyped]

    nt = Network(notebook=True, height="100vh", width="100%")
    nt.from_nx(G)
    nt.show(filename)


def get_plaintext_report(context: dict) -> str:
    output = (context['brief'] + " ").replace('. ', '.\n')
    interests = list(map(lambda x: x[0], context.get('interests_tuple_list', [])))
    countries = list(map(lambda x: x[0], context.get('countries_tuple_list', [])))
    if countries:
        output += f'所在國家 (Countries): {", ".join(countries)}\n'
    if interests:
        output += f'興趣標籤 (Interests): {", ".join(interests)}\n'
    return output.strip()


def _md_format_value(value) -> str:
    """Format a value for Markdown output, detecting links."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value)
    s = str(value)
    if s.startswith("http://") or s.startswith("https://"):
        return f"[{s}]({s})"
    return s


def generate_markdown_report(context: dict, run_info: dict = None) -> str:
    username = context.get("username", "unknown")
    generated_at = context.get("generated_at", "")
    brief = context.get("brief", "")
    countries = context.get("countries_tuple_list", [])
    interests = context.get("interests_tuple_list", [])
    first_seen = context.get("first_seen")
    results = context.get("results", [])

    # Collect ALL values for key fields across all accounts
    all_fields: Dict[str, list] = {}
    last_seen = None
    for _, _, data in results:
        for _, v in data.items():
            if not v.get("found") or v.get("is_similar"):
                continue
            ids_data = v.get("ids_data", {})
            # Map multiple source fields to unified output fields
            field_sources = {
                "fullname": ("fullname", "name"),
                "location": ("location", "country", "city", "country_code", "locale", "region"),
                "gender": ("gender",),
                "bio": ("bio", "about", "description"),
            }
            for out_field, source_keys in field_sources.items():
                for src in source_keys:
                    val = ids_data.get(src)
                    if val:
                        all_fields.setdefault(out_field, [])
                        val_str = str(val)
                        if val_str not in all_fields[out_field]:
                            all_fields[out_field].append(val_str)
            # Track last_seen
            for ts_field in ("last_online", "latest_activity_at", "updated_at"):
                ts = ids_data.get(ts_field)
                if ts and (last_seen is None or str(ts) > str(last_seen)):
                    last_seen = ts

    lines = []
    lines.append(f"# Report by searching on username \"{username}\"\n")

    # Generated line with run info
    gen_line = f"Generated at {generated_at} by [Maigret](https://github.com/soxoj/maigret)"
    if run_info:
        parts = []
        if run_info.get("sites_count"):
            parts.append(f"{run_info['sites_count']} sites checked")
        if run_info.get("flags"):
            parts.append(f"flags: `{run_info['flags']}`")
        if parts:
            gen_line += f" ({', '.join(parts)})"
    lines.append(f"{gen_line}\n")

    # Summary
    lines.append("## Summary\n")
    lines.append(f"{brief}\n")

    if all_fields:
        lines.append("**Information extracted from accounts:**\n")
        for field, values in all_fields.items():
            title = CaseConverter.snake_to_title(field)
            lines.append(f"- {title}: {'; '.join(values)}")
        lines.append("")

    if countries:
        geo = ", ".join(f"{code} (x{count})" for code, count in countries)
        lines.append(f"**Country tags:** {geo}\n")

    if interests:
        tags = ", ".join(f"{tag} (x{count})" for tag, count in interests)
        lines.append(f"**Website tags:** {tags}\n")

    if first_seen:
        lines.append(f"**First seen:** {first_seen}")
    if last_seen:
        lines.append(f"**Last seen:** {last_seen}")
    if first_seen or last_seen:
        lines.append("")

    # Accounts found
    lines.append("## Accounts found\n")

    for u, id_type, data in results:
        for site_name, v in data.items():
            if not v.get("found") or v.get("is_similar"):
                continue

            lines.append(f"### {site_name}\n")
            lines.append(f"- **URL:** [{v.get('url_user', '')}]({v.get('url_user', '')})")

            tags = v.get("status") and v["status"].tags or []
            if tags:
                lines.append(f"- **Tags:** {', '.join(tags)}")
                lines.append("")

            ids_data = v.get("ids_data", {})
            if ids_data:
                for field, value in ids_data.items():
                    if field == "image":
                        continue
                    title = CaseConverter.snake_to_title(field)
                    lines.append(f"- {title}: {_md_format_value(value)}")

            lines.append("")

    # Possible false positives
    lines.append("## Possible false positives\n")
    lines.append(
        f"This report was generated by searching for accounts matching the username `{username}`. "
        f"Accounts listed above may belong to different people who happen to use the same "
        f"or similar username. Results without extracted personal information could contain "
        f"some false positive findings. Always verify findings before drawing conclusions.\n"
    )

    # Ethical use
    lines.append("## Ethical use\n")
    lines.append(
        "This report is a result of a technical collection of publicly available information "
        "from online accounts and does not constitute personal data processing. If you intend "
        "to use this data for personal data processing or collection purposes, ensure your use "
        "complies with applicable laws and regulations in your jurisdiction (such as GDPR, "
        "CCPA, and similar).\n"
    )

    return "\n".join(lines)


def save_markdown_report(filename: str, context: dict, run_info: dict = None):
    content = generate_markdown_report(context, run_info)
    with open(filename, "w", encoding="utf-8") as f:
        f.write(content)


"""
REPORTS GENERATING
"""


def generate_report_template(is_pdf: bool):
    """
    HTML/PDF template generation
    """

    def get_resource_content(filename):
        # 明確指定 utf-8，避免 Windows 用 cp950 讀取含繁中字元的模板
        return open(os.path.join(maigret_path, "resources", filename), encoding="utf-8").read()

    maigret_path = os.path.dirname(os.path.realpath(__file__))

    if is_pdf:
        template_content = get_resource_content("simple_report_pdf.tpl")
        css_content = get_resource_content("simple_report_pdf.css")
    else:
        template_content = get_resource_content("simple_report.tpl")
        css_content = None

    template = Template(template_content)
    template.globals["title"] = CaseConverter.snake_to_title  # type: ignore
    template.globals["detect_link"] = enrich_link_str  # type: ignore
    return template, css_content


def generate_report_context(username_results: list):
    brief_text = []
    usernames = {}
    extended_info_count = 0
    tags: Dict[str, int] = {}
    supposed_data: Dict[str, Any] = {}

    first_seen = None

    # moved here to speed up the launch of Maigret
    import pycountry

    for username, id_type, results in username_results:
        found_accounts = 0
        new_ids = []
        usernames[username] = {"type": id_type}

        for website_name in results:
            dictionary = results[website_name]
            # TODO: fix no site data issue
            if not dictionary:
                continue

            if dictionary.get("is_similar"):
                continue

            status = dictionary.get("status")
            if not status:  # FIXME: currently in case of timeout
                continue

            if status.ids_data:
                dictionary["ids_data"] = status.ids_data
                extended_info_count += 1

                # detect first seen
                created_at = status.ids_data.get("created_at")
                if created_at:
                    if first_seen is None:
                        first_seen = created_at
                    else:
                        try:
                            known_time = parse_datetime_str(
                                first_seen, tzinfos=ADDITIONAL_TZINFO
                            )
                            new_time = parse_datetime_str(
                                created_at, tzinfos=ADDITIONAL_TZINFO
                            )
                            if new_time < known_time:
                                first_seen = created_at
                        except Exception as e:
                            logging.debug(
                                "Problems with converting datetime %s/%s: %s",
                                first_seen,
                                created_at,
                                str(e),
                                exc_info=True,
                            )

                for k, v in status.ids_data.items():
                    # suppose target data
                    field = "fullname" if k == "name" else k
                    if field not in supposed_data:
                        supposed_data[field] = []
                    supposed_data[field].append(v)
                    # suppose country
                    if k in ["country", "locale"]:
                        try:
                            if is_country_tag(k):
                                country = pycountry.countries.get(alpha_2=v)
                                tag = country.alpha_2.lower()  # type: ignore[union-attr]
                            else:
                                tag = pycountry.countries.search_fuzzy(v)[
                                    0
                                ].alpha_2.lower()  # type: ignore[attr-defined]
                            tags[tag] = tags.get(tag, 0) + 1
                        except Exception as e:
                            logging.debug(
                                "Pycountry exception: %s", str(e), exc_info=True
                            )

            new_usernames = dictionary.get("ids_usernames")
            if new_usernames:
                for u, utype in new_usernames.items():
                    if u not in usernames:
                        new_ids.append((u, utype))
                        usernames[u] = {"type": utype}

            if status.status == MaigretCheckStatus.CLAIMED:
                found_accounts += 1
                dictionary["found"] = True
            else:
                continue

            # ignore non-exact search results
            if status.tags:
                for t in status.tags:
                    tags[t] = tags.get(t, 0) + 1

        brief_text.append(
            f"以 {id_type}「{username}」搜尋，找到 {found_accounts} 個帳號。"
            f" (Search by {id_type} {username} returned {found_accounts} accounts.)"
        )

        if new_ids:
            ids_list = []
            for u, t in new_ids:
                ids_list.append(f"{u} ({t})" if t != "username" else u)
            brief_text.append(
                "發現目標的其他識別碼 (Other IDs found): " + ", ".join(ids_list) + "。"
            )

    brief_text.append(
        f"從 {extended_info_count} 個帳號擷取延伸資訊。"
        f" (Extended info extracted from {extended_info_count} accounts.)"
    )

    brief = " ".join(brief_text).strip()
    tuple_sort = lambda d: sorted(d, key=lambda x: x[1], reverse=True)

    if "global" in tags:
        # remove tag 'global' useless for country detection
        del tags["global"]

    first_username = username_results[0][0]
    countries_lists = list(filter(lambda x: is_country_tag(x[0]), tags.items()))
    interests_list = list(filter(lambda x: not is_country_tag(x[0]), tags.items()))

    filtered_supposed_data = filter_supposed_data(supposed_data)

    return {
        "username": first_username,
        "brief": brief,
        "results": username_results,
        "first_seen": first_seen,
        "interests_tuple_list": tuple_sort(interests_list),
        "countries_tuple_list": tuple_sort(countries_lists),
        "supposed_data": filtered_supposed_data,
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


_HTTP_STATUS_ZH = {
    0:   "連線失敗（逾時或無回應）",
    200: "成功回應",
    301: "永久轉址",
    302: "暫時轉址",
    400: "請求格式錯誤",
    401: "需要身份驗證",
    403: "拒絕存取",
    404: "找不到頁面",
    405: "不允許此方法",
    410: "已永久移除",
    429: "請求次數過多",
    500: "伺服器內部錯誤",
    502: "閘道錯誤",
    503: "服務暫時無法使用",
    504: "閘道逾時",
}

_EXISTS_ZH = {
    "Available":  "帳號存在",
    "Claimed":    "帳號已確認存在",
    "Unknown":    "未知（無法判斷）",
    "Not Found":  "帳號不存在",
    "Assumed":    "推測存在",
    "Error":      "查詢發生錯誤",
}

_SITE_NAME_ZH = {
    # ── 1. 全球主流社群與通訊 ──────────────────────────────────────
    "Instagram":          "Instagram（IG）",
    "Threads":            "Threads（脆 / 串串）",
    "Facebook":           "Facebook（FB / 臉書）",
    "Twitter":            "Twitter（推特，現官方更名為 X）",
    "Telegram":           "Telegram（紙飛機 / 電報）",
    "Snapchat":           "Snapchat（色卡特）",
    "Pinterest":          "Pinterest（品趣志）",
    "Tumblr":             "Tumblr（湯不熱）",
    "Plurk":              "噗浪",
    "Weibo":              "微博",
    "Discord":            "Discord（DC）",
    "TikTok":             "TikTok（抖音國際版）",
    "Bluesky":            "Bluesky（去中心化新興社群）",
    "mastodon.social":    "長毛象 mastodon.social（分散式聯邦社群）",
    "mastodon.cloud":     "長毛象 mastodon.cloud",
    "VK":                 "VKontakte（俄羅斯與東歐最大社群，VK）",
    "linktr.ee":          "Linktree（多連結工具 / 電子名片）",
    "Dcard":              "Dcard",

    # ── 2. 臺灣本土知名網站 ───────────────────────────────────────
    "Pixnet":             "痞客邦",
    "iThome":             "iThome 電腦報",
    "iCook":              "愛料理",
    "HackMD":             "HackMD（臺灣本土 Markdown 協作平台）",
    "Bahamut":            "巴哈姆特（臺灣最大遊戲社群／小屋）",
    "KKTIX":              "KKTIX（臺灣活動售票平台）",
    "Eyny":               "伊莉討論區（臺灣綜合論壇）",
    "TechBang":           "T客邦（臺灣科技媒體／作者頁）",
    "Womany":             "女人迷 Womany（性別議題媒體／專欄作家）",
    "Ruten":              "露天市集（臺灣最大網拍／賣場）",
    "Accupass":           "Accupass 活動通（活動主辦單位）",
    "TWReporter":         "報導者 The Reporter（非營利調查報導／記者頁）",
    "SayDigi":            "點子生活 SayDigi（科技生活部落格／作者）",
    "Mobile01":           "Mobile01（臺灣最大科技討論區／會員）",
    "Backpackers":        "背包客棧（臺灣最大自助旅行論壇／會員）",
    "StoryStudio":        "故事 StoryStudio（歷史文化內容平台／專欄作家）",
    "TechNews":           "科技新報 TechNews（科技媒體／記者頁）",
    "BusinessNext":       "數位時代 BusinessNext（科技商業媒體／作者頁）",
    "CommonWealth":       "天下雜誌（財經媒體／作者頁）",
    "TVBS":               "TVBS 新聞網（電視新聞媒體／記者頁）",
    "KOCPC":              "電腦王阿達 KOCPC（3C 科技部落格／作者）",
    "INSIDE":             "INSIDE 硬塞網路趨勢觀察",
    "TNL":                "關鍵評論網（The News Lens）",
    "Vocus":              "方格子",
    "Zeczec":             "嘖嘖（知名群眾募資平台）",
    "flyingV":            "flyingV（知名群眾募資平台）",
    "Yourator":           "Yourator 數位人才媒合平台",
    "StockFeel":          "股感知識庫",
    "CakeResume":         "CakeResume（知名求職履歷平台）",
    "StreetVoice":        "街聲（獨立音樂平台）",
    "PanSci":             "泛科學",
    "SoFree":             "SoFree 心得筆記（臺灣知名科技部落格）",
    "SoFun":              "硬是要學（soft4fun.net）",
    "ITHelp":             "iT 邦幫忙",
    "Matters":            "Matters（Web3 分散式寫作社群）",
    "LikeCoin":           "讚賞幣（去中心化出版讚賞生態）",

    # ── 3. 開發者、程式設計與技術社群 ────────────────────────────
    "GitHub":             "GitHub",
    "GitHubGist":         "GitHub Gist",
    "GitLab":             "GitLab",
    "StackOverflow":      "Stack Overflow",
    "NPM":                "NPM",
    "NPM-Package":        "NPM",
    "npmjs":              "NPM",
    "PyPI":               "PyPI（Python 套件庫）",
    "HackerNews":         "Hacker News",
    "HuggingFace":        "Hugging Face（抱抱臉）",
    "DEV Community":      "DEV Community（開發者社群）",
    "Dev":                "DEV Community",
    "Gitea":              "Gitea",
    "codeberg.org":       "Codeberg",
    "Codeberg":           "Codeberg",
    "Gitee":              "碼雲（中國知名程式碼託管平台）",
    "LeetCode":           "LeetCode（臺灣工程師口語稱「刷題網」）",
    "Codepen":            "CodePen",
    "Packagist":          "Packagist",
    "JSFiddle":           "JSFiddle",
    "Laracast":           "Laracasts",
    "HackerOne":          "HackerOne",
    "Hackaday":           "Hackaday",
    "HackerNoon":         "HackerNoon",
    "RubyGems":           "RubyGems",
    "RapidAPI":           "RapidAPI",
    "Codementor":         "Codementor",
    "Topcoder":           "Topcoder",
    "codeforces.com":     "Codeforces",
    "Codeforces":         "Codeforces",
    "CTFtime":            "CTFtime（資安競賽平台）",
    "Freecodecamp":       "freeCodeCamp",
    "HackTheBox":         "Hack The Box",
    "TryHackMe":          "TryHackMe",
    "Replit":             "Replit",
    "Repl.it":            "Replit",
    "W3Schools":          "W3Schools",
    "SourceForge":        "SourceForge",
    "Keybase":            "Keybase（安全加密身分驗證平台）",
    "Geeksfor Geeks":     "GeeksforGeeks（印度起家的電腦科學學習神站）",
    "GeeksforGeeks":      "GeeksforGeeks",
    "CTAN":               "CTAN（LaTeX 綜合檔案網路）",

    # ── 4. 遊戲、電競與動漫社群 ──────────────────────────────────
    "Steam":              "Steam（蒸氣平台 / 精神時光屋）",
    "Steam (Group)":      "Steam 群組",
    "Twitch":             "Twitch（圖奇 / 紫色學校）",
    "Roblox":             "機器磚塊（羅布樂思）",
    "Minecraft":          "Minecraft（當個創世神 / 麥塊）",
    "Xbox Gamertag":      "Xbox",
    "Xbox":               "Xbox",
    "PlayStation":        "PlayStation",
    "PlaystationTrophies":"PlayStation 獎盃",
    "MyAnimeList":        "MyAnimeList（全球知名動漫評分誌）",
    "AnimeNewsNetwork":   "動漫新聞網路（ANN）",
    "Chess":              "Chess.com（西洋棋線上平台）",
    "Lichess":            "Lichess（開源西洋棋平台）",
    "Newgrounds":         "Newgrounds（獨立創作與 Flash 遊戲網）",
    "Speedrun.com":       "Speedrun.com（極速通關紀錄網）",
    "Speedrun":           "Speedrun.com（極速通關紀錄網）",
    "Kongregate":         "Kongregate（網頁遊戲平台）",
    "Wowhead":            "Wowhead（魔獸世界資料庫）",
    "OP.GG [PUBG]":       "OP.GG PUBG 戰績",
    "OP.GG [Valorant]":   "OP.GG Valorant 戰績",
    "OP.GG LoL Brazil":   "OP.GG 英雄聯盟（巴西）",
    "OP.GG":              "OP.GG（英雄聯盟戰績網）",
    "Gog":                "GOG.com（數位遊戲發行平台）",
    "GOG":                "GOG.com",
    "GamesRadar":         "GamesRadar+（遊戲媒體）",
    "Polygon":            "Polygon（知名電玩遊戲媒體）",
    "DLive":              "DLive（直播平台）",

    # ── 5. 影音、音樂與多媒體平台 ────────────────────────────────
    "YouTube":            "YouTube（YT）",
    "Vimeo":              "Vimeo",
    "SoundCloud":         "SoundCloud（臺灣音樂圈俗稱「死耗子」）",
    "MixCloud":           "Mixcloud",
    "Mixcloud":           "Mixcloud",
    "Spotify":            "Spotify（強迫聽）",
    "DailyMotion":        "Dailymotion",
    "Bandcamp":           "Bandcamp",
    "Odysee":             "Odysee（去中心化影音平台）",
    "Freesound":          "Freesound（開源聲音素材庫）",
    "last.fm":            "Last.fm",
    "Last.fm":            "Last.fm",
    "Smule":              "Smule（歌唱 App）",
    "ReverbNation":       "ReverbNation",

    # ── 6. 內容創作、網誌、電子報與 CMS ─────────────────────────
    "WordPress":          "WordPress",
    "WordPressOrg":       "WordPress 社群",
    "Blogger":            "Blogger（部落格 / 網誌）",
    "Medium":             "Medium",
    "Substack":           "Substack（電子報訂閱平台）",
    "Wix":                "Wix（線上架站平台）",
    "Weebly":             "Weebly",
    "Disqus":             "Disqus（第三方評論系統）",
    "LiveJournal":        "LiveJournal",
    "write.as":           "Write.as",
    "WriteAs":            "Write.as",
    "note":               "note（日本知名創作平台）",
    "Note":               "note（日本知名創作平台）",
    "Paragraph":          "Paragraph（Web3 創作平台）",

    # ── 7. 設計、創意、圖庫與 UI/UX ─────────────────────────────
    "Freepik":            "Freepik",
    "DeviantART":         "DeviantArt（藝術家社群，俗稱 DA）",
    "DeviantArt":         "DeviantArt（DA）",
    "Behance":            "Behance",
    "Dribbble":           "Dribbble（設計師社群，俗稱籃球網）",
    "Figma":              "Figma（UI/UX 業界標準設計工具）",
    "Artstation":         "ArtStation（數位視覺藝術家聖地）",
    "ArtStation":         "ArtStation",
    "ThemeForest":        "ThemeForest（網站佈景主題市場）",
    "Codecanyon":         "CodeCanyon",
    "CreativeMarket":     "Creative Market",
    "Imgur":              "Imgur（網路圖庫分享站）",
    "Giphy":              "Giphy（GIF 動態圖庫）",
    "Flickr":             "Flickr",
    "500px":              "500px（專業攝影社群）",
    "Redbubble":          "Redbubble（獨立設計師週邊販售網）",
    "Smugmug":            "SmugMug",
    "SmugMug":            "SmugMug",
    "Imgflip":            "Imgflip（迷因梗圖生成器）",
    "99designs":          "99designs（外包設計平台）",
    "MyMiniFactory":      "MyMiniFactory（3D 列印模型社群）",
    "CGTrader":           "CGTrader（3D 模型市場）",
    "domestika.org":      "Domestika（創意設計線上課程）",
    "Domestika":          "Domestika",
    "Coroflot":           "Coroflot（設計師求職網）",
    "Lomography":         "Lomography（樂魔相機 / 底片攝影社群）",
    "SlideShare":         "SlideShare（投影片分享平台）",

    # ── 8. 學術、百科與知識問答 ──────────────────────────────────
    "Wikipedia":          "維基百科",
    "Wikidata":           "維基數據（Wikidata）",
    "ResearchGate":       "ResearchGate（學術界的臉書）",
    "Quora":              "Quora（美國知乎）",
    "Fandom":             "Fandom（動漫 / 遊戲 Wiki 社群，前身 Wikia）",
    "GoodReads":          "Goodreads（全球書評社群）",
    "LibraryThing":       "LibraryThing（線上書目管理與社群）",
    "CTAN":               "CTAN（LaTeX 套件庫）",

    # ── 9. 群眾募資、求職外包與商務網路 ─────────────────────────
    "Kickstarter":        "Kickstarter（全球最大群眾募資平台）",
    "Gofundme":           "GoFundMe（個人公益 / 緊急募資平台）",
    "BuyMeACoffee":       "Buy Me a Coffee（創作者贊助平台）",
    "kofi":               "Ko-fi（創作者贊助平台）",
    "Ko-fi":              "Ko-fi（創作者贊助平台）",
    "Patreon":            "Patreon（創作者定額訂閱贊助平台）",
    "OpenCollective":     "Open Collective（開源專案財務公開募資）",
    "Fiverr":             "Fiverr（五美元自由職業外包網）",
    "Freelancer.com":     "Freelancer（自由職業外包網）",
    "Freelancer":         "Freelancer（自由職業外包網）",
    "Upwork":             "Upwork（全球最大高階外包接案平台）",
    "LinkedIn":           "LinkedIn（領英）",
    "Xing":               "XING（歐洲主流商務社群，類似 LinkedIn）",
    "ProductHunt":        "Product Hunt（每日科技新品發佈選物網）",
    "Calendly":           "Calendly（線上日程預約排程工具）",
    "GooglePlayStore":    "Google Play 商店",
    "IFTTT":              "IFTTT（自動化任務串接服務）",
    "Gravatar":           "Gravatar（全球頭像）",

    # ── 10. 科技、新聞媒體與論壇 ─────────────────────────────────
    "Reddit":             "Reddit（臺灣大眾常稱「美國 PTT」）",
    "CNET":               "CNET（資深科技新聞評論網）",
    "TheVerge":           "The Verge（頂級科技與潮流媒體）",
    "Slashdot":           "Slashdot（資深極客 / 黑客論壇）",
    "Techrepublic":       "TechRepublic",
    "TechRepublic":       "TechRepublic",
    "TechSpot":           "TechSpot",
    "BuzzFeed":           "BuzzFeed（美國爆紅娛樂新聞網）",
    "Flipboard":          "Flipboard（隨身翻閱雜誌 App）",
    "Polygon":            "Polygon（知名電玩遊戲媒體）",

    # ── 11. 生活、美食、旅遊 ─────────────────────────────────────
    "TripAdvisor":        "貓途鷹（Tripadvisor 旅遊評論網）",
    "Foursquare":         "Foursquare（打卡始祖 / 地理位置服務）",
    "AllRecipes":         "Allrecipes（全球最大食譜分享網）",
    "OpenStreetMap":      "開放街圖（OSM）",
    "Geocaching":         "地理藏寶（全球 GPS 尋寶遊戲）",
    "Flightradar24":      "Flightradar24（全球即時航班雷達追蹤）",
    "Windy":              "Windy（全球知名氣象風速雷達網）",

    # ── 12. 效率工具與雲端協作 ───────────────────────────────────
    "Trello":             "Trello（看板式專案管理工具）",
    "Slack":              "Slack（企業團隊通訊軟體）",
    "Pastebin":           "Pastebin（文字 / 程式碼暫存黏貼服務）",
    "Instapaper":         "Instapaper（稍後閱讀工具）",
    "Bit.ly":             "Bitly（知名縮網址服務）",
    "Bitly":              "Bitly（縮網址）",

    # ── 13. 娛樂、影評與迷因 ─────────────────────────────────────
    "Letterboxd":         "Letterboxd（全球影迷電影記錄評分社群）",
    "Rottentomatoes":     "爛番茄（知名影評網站）",
    "Genius":             "Genius（歌詞與背後意涵解析網）",
    "iFunny":             "iFunny（歐美爆笑迷因圖 App）",
    "Coub":               "Coub（10 秒循環短影音平台）",
    "Myspace":            "Myspace（我的空間，社群網站先驅）",

    # ── 14. 區域性熱門社群（韓、日、俄、其他） ──────────────────
    "Naver":              "NAVER（韓國第一大搜尋引擎與入口網站）",
    "Tistory":            "Tistory（韓國市佔極高的部落格平台）",
    "Namuwiki":           "樹維基（Namu Wiki，韓國規模極大的民間百科）",
    "Dcinside":           "DC Inside（韓國最大綜合論壇，韓國的 5ch）",
    "Velog":              "Velog（韓國工程師最愛用的簡約技術網誌）",
    "Habr":               "Habr（俄羅斯最大 IT 協作部落格）",
    "VK":                 "VKontakte（俄羅斯東歐最大社群，VK）",
    "Douban":             "豆瓣（中國書影音點評與文青社群）",
    "Ameblo":             "Ameba 部落格（日本最大明星與大眾網誌平台）",
    "Booth":              "BOOTH（日本 Pixiv 旗下同人二創與手作電商）",

    # ── 15. 其他特定領域 ─────────────────────────────────────────
    "Duolingo":           "多鄰國（語言學習 App）",
    "Wattpad":            "Wattpad（全球最大青少年網路小說創作平台）",
    "Instructables":      "Instructables（知名 DIY 手工創客步驟教學網）",
    "AlternativeTo":      "AlternativeTo（軟體替代方案評比網）",
    "TVTropes":           "TV Tropes（解構影視動漫公式與老梗的流行文化百科）",
    "TradingView":        "TradingView（全球頂尖金融 K 線分析圖表網）",
    "Untappd":            "Untappd（全球啤酒愛好者品酒打卡社群）",
    "Couchsurfing":       "沙發衝浪（國際自助旅行免費住宿交換社群）",
    "AllKPop":            "Allkpop（美國最大韓流英文新聞網）",
    "iNaturalist":        "iNaturalist（物種自然觀察記錄網）",
    "Venmo":              "Venmo（美國主流行動支付 / 社交轉帳工具）",
    "Polymarket":         "Polymarket（Web3 去中心化資訊預測市場）",
    "Change.org":         "Change.org（全球最大線上請願 / 聯署平台）",
    "Change":             "Change.org（線上請願聯署）",
}


def generate_csv_report(username: str, results: dict, csvfile):
    writer = csv.writer(csvfile)
    writer.writerow(
        [
            "使用者名稱 (username)",
            "站點名稱 (name)",
            "站點中文名稱",
            "站點首頁 (url_main)",
            "個人頁網址 (url_user)",
            "帳號狀態 (exists)",
            "帳號狀態說明",
            "HTTP狀態碼 (http_status)",
            "HTTP說明",
        ]
    )
    for site in results:
        status = 'Unknown'
        if "status" in results[site]:
            status = str(results[site]["status"].status)
        http_code = results[site].get("http_status", 0)
        site_zh = _SITE_NAME_ZH.get(site, "")
        status_zh = _EXISTS_ZH.get(status, "")
        http_zh = _HTTP_STATUS_ZH.get(int(http_code) if http_code else 0, "")
        writer.writerow(
            [
                username,
                site,
                site_zh,
                results[site].get("url_main", ""),
                results[site].get("url_user", ""),
                status,
                status_zh,
                http_code,
                http_zh,
            ]
        )


def generate_txt_report(username: str, results: dict, file):
    exists_counter = 0
    for website_name in results:
        dictionary = results[website_name]
        # TODO: fix no site data issue
        if not dictionary:
            continue
        if (
            dictionary.get("status")
            and dictionary["status"].status == MaigretCheckStatus.CLAIMED
        ):
            exists_counter += 1
            file.write(dictionary["url_user"] + "\n")
    file.write(f"Total Websites Username Detected On : {exists_counter}")


def generate_json_report(username: str, results: dict, file, report_type):
    is_report_per_line = report_type.startswith("ndjson")
    all_json = {}

    for sitename in results:
        site_result = results[sitename]
        # TODO: fix no site data issue
        if not site_result or not site_result.get("status"):
            continue

        if site_result["status"].status != MaigretCheckStatus.CLAIMED:
            continue

        data = dict(site_result)
        data["status"] = data["status"].json()
        data["site"] = data["site"].json
        for field in ["future", "checker"]:
            if field in data:
                del data[field]

        if is_report_per_line:
            data["sitename"] = sitename
            file.write(json.dumps(data) + "\n")
        else:
            all_json[sitename] = data

    if not is_report_per_line:
        file.write(json.dumps(all_json))


"""
XMIND 8 Functions
"""


def save_xmind_report(filename, username, results):
    if os.path.exists(filename):
        os.remove(filename)
    workbook = xmind.load(filename)
    sheet = workbook.getPrimarySheet()
    design_xmind_sheet(sheet, username, results)
    xmind.save(workbook, path=filename)


def add_xmind_subtopic(userlink, k, v, supposed_data):
    currentsublabel = userlink.addSubTopic()
    field = "fullname" if k == "name" else k
    if field not in supposed_data:
        supposed_data[field] = []
    supposed_data[field].append(v)
    currentsublabel.setTitle("%s: %s" % (k, v))


def design_xmind_sheet(sheet, username, results):
    alltags: Dict[str, Any] = {}
    supposed_data: Dict[str, Any] = {}

    sheet.setTitle("%s Analysis" % (username))
    root_topic1 = sheet.getRootTopic()
    root_topic1.setTitle("%s" % (username))

    undefinedsection = root_topic1.addSubTopic()
    undefinedsection.setTitle("Undefined")
    alltags["undefined"] = undefinedsection

    for website_name in results:
        dictionary = results[website_name]
        if not dictionary:
            continue
        result_status = dictionary.get("status")
        # TODO: fix the reason
        if not result_status or result_status.status != MaigretCheckStatus.CLAIMED:
            continue

        stripped_tags = list(map(lambda x: x.strip(), result_status.tags))
        normalized_tags = list(
            filter(lambda x: x and not is_country_tag(x), stripped_tags)
        )

        category = None
        for tag in normalized_tags:
            if tag in alltags.keys():
                continue
            tagsection = root_topic1.addSubTopic()
            tagsection.setTitle(tag)
            alltags[tag] = tagsection
            category = tag

        section = alltags[category] if category else undefinedsection
        userlink = section.addSubTopic()
        userlink.addLabel(result_status.site_url_user)

        ids_data = result_status.ids_data or {}
        for k, v in ids_data.items():
            # suppose target data
            if isinstance(v, list):
                for currentval in v:
                    add_xmind_subtopic(userlink, k, currentval, supposed_data)
            else:
                add_xmind_subtopic(userlink, k, v, supposed_data)

    # add supposed data
    filtered_supposed_data = filter_supposed_data(supposed_data)
    if len(filtered_supposed_data) > 0:
        undefinedsection = root_topic1.addSubTopic()
        undefinedsection.setTitle("SUPPOSED DATA")
        for k, v in filtered_supposed_data.items():
            currentsublabel = undefinedsection.addSubTopic()
            currentsublabel.setTitle("%s: %s" % (k, v))
