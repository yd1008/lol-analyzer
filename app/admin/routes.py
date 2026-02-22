import functools
import json
import logging

from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import login_required, current_user
from app.admin import admin_bp
from app.models import AdminAuditLog, MatchAnalysis, RiotAccount, User
from app.analysis.riot_api import get_watcher, get_routing_value, resolve_puuid, get_recent_matches
from app.analysis.engine import analyze_match, get_match_summary
from app.analysis.llm import get_llm_analysis_detailed
from app.i18n import get_locale, lt, t
from app.extensions import db

logger = logging.getLogger(__name__)


def _has_admin_access() -> bool:
    admin_email = (current_app.config.get('ADMIN_EMAIL', '') or '').strip().lower()
    email = (current_user.email or '').strip().lower()
    return bool(current_user.is_admin or (admin_email and email == admin_email))


def _audit_admin_action(action: str, details: dict | None = None) -> None:
    """Persist a best-effort audit event for admin traffic."""
    try:
        entry = AdminAuditLog(
            actor_user_id=getattr(current_user, 'id', None),
            action=action,
            route=request.path,
            method=request.method,
            ip_address=request.headers.get('X-Forwarded-For', request.remote_addr),
            user_agent=(request.user_agent.string or '')[:512],
            metadata_json=details or {},
        )
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Failed to write admin audit log for action=%s", action)


def admin_required(f):
    @functools.wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not _has_admin_access():
            _audit_admin_action('admin_access_denied', {'endpoint': request.endpoint})
            flash(t('flash.access_denied'), 'error')
            return redirect(url_for('dashboard.index'))
        _audit_admin_action('admin_access_allowed', {'endpoint': request.endpoint})
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@admin_required
def index():
    users = User.query.all()
    total_analyses = MatchAnalysis.query.count()
    _audit_admin_action('admin_index_view')
    return render_template('admin/index.html', users=users, total_analyses=total_analyses)


@admin_bp.route('/test-llm', methods=['GET', 'POST'])
@admin_required
def test_llm():
    result = None
    analysis_data = None

    if request.method == 'POST':
        action = request.form.get('action', 'lookup')

        if action == 'lookup':
            _audit_admin_action('admin_test_llm_lookup')
            summoner = request.form.get('summoner_name', '').strip()
            tagline = request.form.get('tagline', '').strip()
            region = request.form.get('region', 'na1').strip()

            if not summoner or not tagline:
                flash(lt('Summoner name and tagline are required.', '召唤师名称和标签为必填项。'), 'error')
                return redirect(url_for('admin.test_llm'))

            puuid, error = resolve_puuid(summoner, tagline, region)
            if error:
                flash(error, 'error')
                return redirect(url_for('admin.test_llm'))

            matches = get_recent_matches(region, puuid, count=10)
            if not matches:
                flash(lt('No recent matches found for this summoner.', '未找到该召唤师最近对局。'), 'warning')
                return redirect(url_for('admin.test_llm'))

            watcher = get_watcher()
            routing = get_routing_value(region)
            match_list = []
            for mid in matches:
                summary = get_match_summary(watcher, routing, puuid, mid)
                if summary:
                    match_list.append(summary)

            if not match_list:
                flash(lt('Failed to fetch match details.', '获取对局详情失败。'), 'error')
                return redirect(url_for('admin.test_llm'))

            return render_template('admin/test_llm.html',
                match_list=match_list,
                puuid=puuid,
                summoner_name=summoner,
                tagline=tagline,
                region=region,
                analysis_data=None,
                result=None,
            )

        elif action == 'select':
            _audit_admin_action('admin_test_llm_select')
            match_id = request.form.get('match_id', '').strip()
            puuid = request.form.get('puuid', '').strip()
            region = request.form.get('region', 'na1').strip()
            summoner = request.form.get('summoner_name', '').strip()
            tagline = request.form.get('tagline', '').strip()

            if not match_id or not puuid:
                flash(lt('Missing match or player information.', '缺少对局或玩家信息。'), 'error')
                return redirect(url_for('admin.test_llm'))

            watcher = get_watcher()
            routing = get_routing_value(region)
            analysis_data = analyze_match(watcher, routing, puuid, match_id)

            if not analysis_data:
                flash(lt('Failed to analyze the selected match.', '分析所选对局失败。'), 'error')
                return redirect(url_for('admin.test_llm'))
            analysis_data['platform_region'] = region
            analysis_data['player_puuid'] = puuid

            return render_template('admin/test_llm.html',
                analysis_data=analysis_data,
                summoner_name=summoner,
                tagline=tagline,
                region=region,
                match_list=None,
                result=None,
            )

        elif action == 'run_llm':
            _audit_admin_action('admin_test_llm_run')
            analysis_json = request.form.get('analysis_json', '')
            max_bytes = int(current_app.config.get('ADMIN_ANALYSIS_JSON_MAX_BYTES', 256 * 1024) or 256 * 1024)
            if len(analysis_json.encode('utf-8')) > max_bytes:
                flash(
                    lt(
                        'Analysis JSON is too large for admin test input.',
                        '分析 JSON 过大，超出管理测试输入上限。',
                    ),
                    'error',
                )
                return redirect(url_for('admin.test_llm'))
            try:
                analysis_data = json.loads(analysis_json)
            except (json.JSONDecodeError, TypeError):
                flash(lt('Invalid analysis data.', '分析数据无效。'), 'error')
                return redirect(url_for('admin.test_llm'))

            result, llm_error = get_llm_analysis_detailed(analysis_data, language=get_locale())
            if llm_error:
                flash(
                    lt('LLM error: {error}', 'LLM 错误：{error}').format(error=llm_error),
                    'error',
                )

            return render_template('admin/test_llm.html',
                analysis_data=analysis_data,
                summoner_name=analysis_data.get('champion', ''),
                tagline='',
                region='',
                match_list=None,
                result=result,
            )

    return render_template('admin/test_llm.html', analysis_data=None, match_list=None, result=None)


@admin_bp.route('/test-discord', methods=['POST'])
@admin_required
def test_discord():
    _audit_admin_action('admin_test_discord')
    channel_id = request.form.get('channel_id', '').strip()
    message = request.form.get('message', lt('Test message from LoL Analyzer admin panel.', '来自 LoL Analyzer 管理面板的测试消息。')).strip()

    if not channel_id:
        flash(t('validation.channel_required'), 'error')
        return redirect(url_for('admin.index'))

    from app.analysis.discord_notifier import send_message
    success = send_message(channel_id, message)

    if success:
        flash(lt('Message sent to channel {channel_id}.', '消息已发送到频道 {channel_id}。').format(channel_id=channel_id), 'success')
    else:
        flash(
            lt('Failed to send Discord message. Check DISCORD_BOT_TOKEN and channel ID.', '发送 Discord 消息失败，请检查 DISCORD_BOT_TOKEN 与频道 ID。'),
            'error',
        )

    return redirect(url_for('admin.index'))
