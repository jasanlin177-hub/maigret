from flask import (
    Flask,
    render_template,
    request,
    send_from_directory,
    send_file,
    Response,
    flash,
    redirect,
    url_for,
)
from werkzeug.exceptions import NotFound
import logging
import os
import sqlite3
import asyncio
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from threading import Thread, Lock
from typing import Any, Dict
import maigret
import maigret.settings
from maigret.checking import build_cloudflare_bypass_config
from maigret.sites import MaigretDatabase
from maigret.report import generate_report_context
from maigret.correlation import correlate_avatars

app = Flask(__name__)
# Use environment variable for secret key, generate random one if not set
app.secret_key = os.getenv('FLASK_SECRET_KEY', os.urandom(24).hex())

# add background job tracking
background_jobs: Dict[str, Any] = {}
job_results = {}

# 全域資料庫單例：3245 站的 data.json 只載入一次，避免每次請求重複載入吃光記憶體
_DB_CACHE: Dict[str, Any] = {}


def get_db() -> MaigretDatabase:
    db_file = app.config["MAIGRET_DB_FILE"]
    if _DB_CACHE.get("path") != db_file or _DB_CACHE.get("db") is None:
        _DB_CACHE["db"] = MaigretDatabase().load_from_path(db_file)
        _DB_CACHE["path"] = db_file
    return _DB_CACHE["db"]

# Configuration
app.config["MAIGRET_DB_FILE"] = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'resources', 'data.json')
app.config["COOKIES_FILE"] = "cookies.txt"
app.config["UPLOAD_FOLDER"] = 'uploads'
app.config["REPORTS_FOLDER"] = os.environ.get(
    "REPORTS_FOLDER",
    os.path.abspath(
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'reports')
    )
)
app.config["COUNTERS_DB_FILE"] = os.environ.get(
    "COUNTERS_DB_FILE",
    os.path.abspath(
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), 'data', 'counters.db')
    )
)


def setup_logger(log_level, name):
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    return logger


# ── 使用次數計數器（開頁次數 / 查詢次數），以 SQLite 持久化，容器重啟不歸零 ──
_counters_lock = Lock()


def _get_counters_db():
    db_path = app.config["COUNTERS_DB_FILE"]
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS counters (key TEXT PRIMARY KEY, value INTEGER NOT NULL DEFAULT 0)"
    )
    return conn


def increment_counter(key: str) -> int:
    with _counters_lock:
        conn = _get_counters_db()
        try:
            conn.execute(
                "INSERT INTO counters (key, value) VALUES (?, 1) "
                "ON CONFLICT(key) DO UPDATE SET value = value + 1",
                (key,),
            )
            conn.commit()
            row = conn.execute(
                "SELECT value FROM counters WHERE key = ?", (key,)
            ).fetchone()
            return row[0] if row else 0
        finally:
            conn.close()


def get_counters() -> Dict[str, int]:
    with _counters_lock:
        conn = _get_counters_db()
        try:
            rows = conn.execute("SELECT key, value FROM counters").fetchall()
            return {key: value for key, value in rows}
        finally:
            conn.close()


@app.context_processor
def inject_counters():
    counters = get_counters()
    return {
        'page_view_count': counters.get('page_views', 0),
        'search_count': counters.get('search_count', 0),
    }


# 統一以臺灣時區顯示時間，避免伺服器所在地時區不同造成誤解。
# 部分環境（如未安裝 tzdata 套件的 Windows）沒有 IANA 時區資料庫，
# 此時退回固定 UTC+8 偏移；臺灣不實施日光節約時間，兩者結果一致。
try:
    TAIPEI_TZ = ZoneInfo("Asia/Taipei")
except Exception:  # pragma: no cover - 僅在缺少 tzdata 的環境觸發
    TAIPEI_TZ = timezone(timedelta(hours=8))


def format_duration(seconds: float) -> str:
    """將秒數轉為中文可讀的耗時字串，例如「3 分 42 秒」。"""
    total_seconds = int(seconds)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)
    if hours:
        return f"{hours} 小時 {minutes} 分 {secs} 秒"
    if minutes:
        return f"{minutes} 分 {secs} 秒"
    return f"{secs} 秒"


async def maigret_search(username, options):
    logger = setup_logger(logging.WARNING, 'maigret')
    try:
        settings = maigret.settings.Settings()
        settings.load()
        cf_bypass_config = build_cloudflare_bypass_config(settings)
        if cf_bypass_config:
            modules_summary = ", ".join(
                f"{m.get('name', m.get('method'))}({m.get('url')})"
                for m in cf_bypass_config["modules"]
            )
            logger.info(
                f"Cloudflare webgate active: triggers={cf_bypass_config['trigger_protection']}, "
                f"modules=[{modules_summary}]"
            )

        db = get_db()

        top_sites = int(options.get('top_sites') or 500)
        if options.get('all_sites'):
            top_sites = 999999999  # effectively all

        tags = options.get('tags', [])
        excluded_tags = options.get('excluded_tags', [])
        site_list = options.get('site_list', [])
        logger.info(f"Filtering sites by tags: {tags}, excluded: {excluded_tags}")

        id_type = options.get('id_type', 'username')

        sites = db.ranked_sites_dict(
            top=top_sites,
            tags=tags,
            excluded_tags=excluded_tags,
            names=site_list,
            disabled=False,
            id_type=id_type,
        )

        logger.info(f"Found {len(sites)} sites matching the tag criteria")

        results = await maigret.search(
            username=username,
            site_dict=sites,
            timeout=int(options.get('timeout', 60)),
            logger=logger,
            id_type=id_type,
            cookies=app.config["COOKIES_FILE"] if options.get('use_cookies') else None,
            is_parsing_enabled=(not options.get('disable_extracting', False)),
            recursive_search_enabled=(
                not options.get('disable_recursive_search', False)
            ),
            check_domains=options.get('with_domains', False),
            proxy=options.get('proxy', None),
            tor_proxy=options.get('tor_proxy', None),
            i2p_proxy=options.get('i2p_proxy', None),
            cloudflare_bypass=cf_bypass_config,
            dns_resolver='threaded',  # Windows 上 aiodns 常失敗，強制用系統 DNS
        )
        return results
    except Exception as e:
        logger.error(f"Error during search: {str(e)}")
        raise


async def search_multiple_usernames(usernames, options):
    results = []
    for username in usernames:
        try:
            search_results = await maigret_search(username.strip(), options)
            results.append((username.strip(), 'username', search_results))
        except Exception as e:
            logging.error(f"Error searching username {username}: {str(e)}")
    return results


def sanitize_username_for_path(username: str) -> str:
    """Remove path separators and dangerous components from username for safe file path usage."""
    # Replace path separators and null bytes
    sanitized = username.replace('/', '_').replace('\\', '_').replace('\0', '_')
    # Remove . and .. components
    sanitized = sanitized.strip('.')
    # If empty after sanitization, use a fallback
    return sanitized or '_'


def process_search_task(usernames, options, timestamp, started_at):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        general_results = loop.run_until_complete(
            search_multiple_usernames(usernames, options)
        )

        os.makedirs(app.config["REPORTS_FOLDER"], exist_ok=True)
        session_folder = os.path.join(
            app.config["REPORTS_FOLDER"], f"search_{timestamp}"
        )
        os.makedirs(session_folder, exist_ok=True)

        graph_path = os.path.join(session_folder, "combined_graph.html")
        maigret.report.save_graph_report(
            graph_path,
            general_results,
            get_db(),
        )

        individual_reports = []
        for username, id_type, results in general_results:
            safe_username = sanitize_username_for_path(username)
            report_base = os.path.join(session_folder, f"report_{safe_username}")

            csv_path = f"{report_base}.csv"
            xlsx_path = f"{report_base}.xlsx"
            json_path = f"{report_base}.json"
            html_path = f"{report_base}.html"

            context = generate_report_context([(username, id_type, results)])

            maigret.report.save_csv_report(csv_path, username, results)
            try:
                maigret.report.save_xlsx_report(xlsx_path, username, results)
            except Exception as e:
                xlsx_path = None  # openpyxl 未安裝，略過
                logging.warning(f"XLSX 報告產生失敗：{e}")
            maigret.report.save_json_report(
                json_path, username, results, report_type='ndjson'
            )
            # 注意：save_html_report 移到頭像關聯分析執行「之後」（見下方），
            # 避免下載的 HTML 報告在關聯分析資料產生前就已存檔完畢，
            # 導致網頁結果頁看得到關聯分析、下載的 HTML 報告卻沒有。

            claimed_profiles = []
            site_avatars = {}
            for site_name, site_data in results.items():
                if (
                    site_data.get('status')
                    and site_data['status'].status
                    == maigret.result.MaigretCheckStatus.CLAIMED
                ):
                    status_obj = site_data.get('status')
                    ids_data = (status_obj.ids_data or {}) if status_obj else {}
                    avatar_url = ids_data.get('image', '')
                    if avatar_url:
                        site_avatars[site_name] = avatar_url
                    claimed_profiles.append(
                        {
                            'site_name': site_name,
                            'url': site_data.get('url_user', ''),
                            'tags': (
                                status_obj.tags if status_obj else []
                            ),
                        }
                    )

            # 頭像關聯分析（選用）：比對各站頭像視覺相似度，
            # 找出可能屬於同一人的帳號群組。失敗不影響主要查詢結果。
            #
            # correlation_requested 記錄「使用者是否勾選了這個選項」，
            # 讓結果頁能明確區分「沒有啟用」「啟用了但沒抓到頭像可比對」
            # 「啟用且執行完成」三種狀態，避免使用者誤以為功能故障、
            # 或誤以為系統已比對過而其實根本沒跑。
            correlation_requested = bool(options.get('correlate_avatars'))
            avatar_clusters = []
            avatar_stats = None
            correlation_error = None
            if correlation_requested and site_avatars:
                try:
                    clusters, stats = loop.run_until_complete(
                        correlate_avatars(site_avatars, logger=logging.getLogger('maigret'))
                    )
                    avatar_clusters = [
                        {
                            'cluster_id': c.cluster_id,
                            'site_names': c.site_names,
                        }
                        for c in clusters
                    ]
                    # 完整保留統計數據，讓介面能誠實區分
                    # 「已比對後無相似」與「頭像無法取得」
                    avatar_stats = {
                        'total_urls': stats.total_urls,
                        'compared': stats.compared,
                        'unavailable': stats.unavailable,
                        'download_failed': stats.download_failed,
                        'unreadable': stats.unreadable,
                        'excluded': stats.excluded,
                        # 逐站失敗原因，讓偵查人員知道哪些站點沒比對到、為什麼，
                        # 必要時可自行人工補查該站頭像
                        'failures': sorted(stats.failures.items()),
                    }
                except Exception as e:
                    correlation_error = str(e)
                    logging.warning(f"頭像關聯分析失敗（不影響查詢結果）：{e}")

            # 把關聯分析結果一併塞進 context，讓下載的 HTML 報告與
            # 網頁結果頁呈現一致的內容，不再各自為政
            context['correlation_requested'] = correlation_requested
            context['avatar_url_count'] = len(site_avatars)
            context['avatar_clusters'] = avatar_clusters
            context['avatar_stats'] = avatar_stats
            context['correlation_error'] = correlation_error
            # PDF 改用瀏覽器列印 HTML 報告（中文正常），不再產生內建 PDF
            maigret.report.save_html_report(html_path, context)

            individual_reports.append(
                {
                    'username': username,
                    'csv_file': f"search_{timestamp}/report_{safe_username}.csv",
                    'xlsx_file': f"search_{timestamp}/report_{safe_username}.xlsx" if xlsx_path else None,
                    'json_file': f"search_{timestamp}/report_{safe_username}.json",
                    'html_file': f"search_{timestamp}/report_{safe_username}.html",
                    'claimed_profiles': claimed_profiles,
                    'correlation_requested': correlation_requested,
                    'avatar_url_count': len(site_avatars),
                    'avatar_clusters': avatar_clusters,
                    'avatar_stats': avatar_stats,
                    'correlation_error': correlation_error,
                }
            )

        # save results and mark job as complete using timestamp as key
        completed_at = datetime.now(TAIPEI_TZ)
        job_results[timestamp] = {
            'status': 'completed',
            'session_folder': f"search_{timestamp}",
            'graph_file': f"search_{timestamp}/combined_graph.html",
            'usernames': usernames,
            'individual_reports': individual_reports,
            'completed_at_str': completed_at.strftime("%Y-%m-%d %H:%M:%S") + " (UTC+8 臺灣時間)",
            'duration_str': format_duration((completed_at - started_at).total_seconds()),
        }

    except Exception as e:
        logging.error(f"Error in search task for timestamp {timestamp}: {str(e)}")
        job_results[timestamp] = {'status': 'failed', 'error': str(e)}
    finally:
        background_jobs[timestamp]['completed'] = True


@app.route('/')
def index():
    increment_counter('page_views')
    # 自動完成清單也快取，避免每次首頁訪問都重算 3245 站的排序
    site_options = _DB_CACHE.get("site_options")
    if site_options is None:
        db = get_db()
        names = set()
        for site in db.sites:
            names.add(site.name)
            if site.url_main:
                names.add(site.url_main)
        site_options = sorted(names)
        _DB_CACHE["site_options"] = site_options

    return render_template('index.html', site_options=site_options)


# Modified search route
@app.route('/search', methods=['POST'])
def search():
    usernames_input = request.form.get('usernames', '').strip()
    if not usernames_input:
        flash('請至少輸入一個查詢目標', 'danger')
        return redirect(url_for('index'))

    usernames = [
        u.strip() for u in usernames_input.replace(',', ' ').split() if u.strip()
    ]

    increment_counter('search_count')

    # Create timestamp for this search session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Get selected tags - ensure it's a list
    selected_tags = request.form.getlist('tags')
    excluded_tags = request.form.getlist('excluded_tags')
    logging.info(f"Selected tags: {selected_tags}, Excluded tags: {excluded_tags}")

    options = {
        'top_sites': request.form.get('top_sites') or '500',
        'timeout': request.form.get('timeout') or '60',
        'use_cookies': 'use_cookies' in request.form,
        'all_sites': 'all_sites' in request.form,
        'disable_recursive_search': 'disable_recursive_search' in request.form,
        'disable_extracting': 'disable_extracting' in request.form,
        'with_domains': 'with_domains' in request.form,
        'proxy': request.form.get('proxy', None) or None,
        'tor_proxy': request.form.get('tor_proxy', None) or None,
        'i2p_proxy': request.form.get('i2p_proxy', None) or None,
        'correlate_avatars': 'correlate_avatars' in request.form,
        'tags': selected_tags,  # Pass selected tags as a list
        'excluded_tags': excluded_tags,  # Pass excluded tags as a list
        'site_list': [
            s.strip() for s in request.form.get('site', '').split(',') if s.strip()
        ],
        'id_type': request.form.get('search_type', 'username'),
    }

    logging.info(
        f"Starting search for usernames: {usernames} with tags: {selected_tags}, excluded: {excluded_tags}"
    )

    # Start background job
    started_at = datetime.now(TAIPEI_TZ)
    background_jobs[timestamp] = {
        'completed': False,
        'thread': Thread(
            target=process_search_task,
            args=(usernames, options, timestamp, started_at),
        ),
    }
    background_jobs[timestamp]['thread'].start()  # type: ignore[union-attr]

    return redirect(url_for('status', timestamp=timestamp))


@app.route('/status/<timestamp>')
def status(timestamp):
    logging.info(f"Status check for timestamp: {timestamp}")

    # Validate timestamp
    if timestamp not in background_jobs:
        flash('查詢階段無效，請重新查詢。', 'danger')
        logging.error(f"Invalid search session: {timestamp}")
        return redirect(url_for('index'))

    # Check if job is completed
    if background_jobs[timestamp]['completed']:
        result = job_results.get(timestamp)
        if not result:
            flash('No results found for this search session.', 'warning')
            logging.error(f"No results found for completed session: {timestamp}")
            return redirect(url_for('index'))

        if result['status'] == 'completed':
            return redirect(url_for('results', session_id=result['session_folder']))
        else:
            error_msg = result.get('error', '發生未知錯誤。')
            # 將常見英文錯誤訊息轉為中文說明
            if "pdf" in error_msg.lower() and "extra" in error_msg.lower():
                error_msg = "PDF 報告套件未安裝，請執行：pip install 'maigret[pdf]'（其他格式報告仍可使用）"
            elif "No module named" in error_msg:
                error_msg = f"缺少必要套件：{error_msg}"
            flash(f'查詢失敗：{error_msg}', 'danger')
            logging.error(f"Search failed for session {timestamp}: {error_msg}")
            return redirect(url_for('index'))

    # If job is still running, show a status page
    return render_template('status.html', timestamp=timestamp)


@app.route('/results/<session_id>')
def results(session_id):
    # Find completed results that match this session_folder
    result_data = next(
        (
            r
            for r in job_results.values()
            if r.get('status') == 'completed' and r['session_folder'] == session_id
        ),
        None,
    )

    if not result_data:
        flash('找不到此次查詢的結果，請重新查詢。', 'danger')
        logging.error(f"Results for session {session_id} not found in job_results.")
        return redirect(url_for('index'))

    return render_template(
        'results.html',
        usernames=result_data['usernames'],
        graph_file=result_data['graph_file'],
        individual_reports=result_data['individual_reports'],
        timestamp=session_id.replace('search_', ''),
        completed_at_str=result_data.get('completed_at_str', ''),
        duration_str=result_data.get('duration_str', ''),
    )


@app.route('/reports/<path:filename>')
def download_report(filename):
    reports_root = app.config["REPORTS_FOLDER"]
    os.makedirs(reports_root, exist_ok=True)
    # Use os.path.join for Windows-compatible path building
    full_path = os.path.normpath(os.path.join(reports_root, filename))
    # Security: ensure resolved path stays within reports_root
    if not full_path.startswith(os.path.normpath(reports_root)):
        return "Access denied", 403
    if not os.path.isfile(full_path):
        logging.error(f"File not found: {full_path}")
        return "File not found", 404
    try:
        return send_file(full_path)
    except Exception as e:
        logging.error(f"Error serving file {filename}: {str(e)}")
        return "File not found", 404


if __name__ == '__main__':
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    )
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() in ['true', '1', 't']

    # Host configuration: secure by default
    # Use 127.0.0.1 for local development, 0.0.0.0 only if explicitly set
    host = os.getenv('FLASK_HOST', '127.0.0.1')
    port = int(os.getenv('FLASK_PORT', '5000'))

    app.run(host=host, port=port, debug=debug_mode)
