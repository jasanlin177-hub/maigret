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
import asyncio
from datetime import datetime
from threading import Thread
from typing import Any, Dict
import maigret
import maigret.settings
from maigret.checking import build_cloudflare_bypass_config
from maigret.sites import MaigretDatabase
from maigret.report import generate_report_context

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


def setup_logger(log_level, name):
    logger = logging.getLogger(name)
    logger.setLevel(log_level)
    return logger


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
            timeout=int(options.get('timeout', 30)),
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


def process_search_task(usernames, options, timestamp):
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

            context = generate_report_context(general_results)

            maigret.report.save_csv_report(csv_path, username, results)
            try:
                maigret.report.save_xlsx_report(xlsx_path, username, results)
            except Exception as e:
                xlsx_path = None  # openpyxl 未安裝，略過
                logging.warning(f"XLSX 報告產生失敗：{e}")
            maigret.report.save_json_report(
                json_path, username, results, report_type='ndjson'
            )
            # PDF 改用瀏覽器列印 HTML 報告（中文正常），不再產生內建 PDF
            maigret.report.save_html_report(html_path, context)

            claimed_profiles = []
            for site_name, site_data in results.items():
                if (
                    site_data.get('status')
                    and site_data['status'].status
                    == maigret.result.MaigretCheckStatus.CLAIMED
                ):
                    claimed_profiles.append(
                        {
                            'site_name': site_name,
                            'url': site_data.get('url_user', ''),
                            'tags': (
                                site_data.get('status').tags
                                if site_data.get('status')
                                else []
                            ),
                        }
                    )

            individual_reports.append(
                {
                    'username': username,
                    'csv_file': f"search_{timestamp}/report_{safe_username}.csv",
                    'xlsx_file': f"search_{timestamp}/report_{safe_username}.xlsx" if xlsx_path else None,
                    'json_file': f"search_{timestamp}/report_{safe_username}.json",
                    'html_file': f"search_{timestamp}/report_{safe_username}.html",
                    'claimed_profiles': claimed_profiles,
                }
            )

        # save results and mark job as complete using timestamp as key
        job_results[timestamp] = {
            'status': 'completed',
            'session_folder': f"search_{timestamp}",
            'graph_file': f"search_{timestamp}/combined_graph.html",
            'usernames': usernames,
            'individual_reports': individual_reports,
        }

    except Exception as e:
        logging.error(f"Error in search task for timestamp {timestamp}: {str(e)}")
        job_results[timestamp] = {'status': 'failed', 'error': str(e)}
    finally:
        background_jobs[timestamp]['completed'] = True


@app.route('/')
def index():
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

    # Create timestamp for this search session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    # Get selected tags - ensure it's a list
    selected_tags = request.form.getlist('tags')
    excluded_tags = request.form.getlist('excluded_tags')
    logging.info(f"Selected tags: {selected_tags}, Excluded tags: {excluded_tags}")

    options = {
        'top_sites': request.form.get('top_sites') or '500',
        'timeout': request.form.get('timeout') or '30',
        'use_cookies': 'use_cookies' in request.form,
        'all_sites': 'all_sites' in request.form,
        'disable_recursive_search': 'disable_recursive_search' in request.form,
        'disable_extracting': 'disable_extracting' in request.form,
        'with_domains': 'with_domains' in request.form,
        'proxy': request.form.get('proxy', None) or None,
        'tor_proxy': request.form.get('tor_proxy', None) or None,
        'i2p_proxy': request.form.get('i2p_proxy', None) or None,
        'permute': 'permute' in request.form,
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
    background_jobs[timestamp] = {
        'completed': False,
        'thread': Thread(
            target=process_search_task, args=(usernames, options, timestamp)
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
