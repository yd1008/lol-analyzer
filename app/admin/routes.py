import functools
from flask import render_template, request, flash, redirect, url_for, current_app
from flask_login import login_required, current_user
from app.admin import admin_bp
from app.models import User, RiotAccount, MatchAnalysis
from app.analysis.riot_api import get_watcher, get_routing_value, resolve_puuid, get_recent_matches
from app.analysis.engine import analyze_match
from app.analysis.llm import get_llm_analysis
from app.extensions import db


def admin_required(f):
    @functools.wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        admin_email = current_app.config.get('ADMIN_EMAIL', '')
        if not admin_email or current_user.email != admin_email:
            flash('Access denied.', 'error')
            return redirect(url_for('dashboard.index'))
        return f(*args, **kwargs)
    return decorated


@admin_bp.route('/')
@admin_required
def index():
    users = User.query.all()
    total_analyses = MatchAnalysis.query.count()
    return render_template('admin/index.html', users=users, total_analyses=total_analyses)


@admin_bp.route('/test-llm', methods=['GET', 'POST'])
@admin_required
def test_llm():
    result = None
    analysis_data = None

    if request.method == 'POST':
        action = request.form.get('action', 'lookup')

        if action == 'lookup':
            summoner = request.form.get('summoner_name', '').strip()
            tagline = request.form.get('tagline', '').strip()
            region = request.form.get('region', 'na1').strip()

            if not summoner or not tagline:
                flash('Summoner name and tagline are required.', 'error')
                return redirect(url_for('admin.test_llm'))

            puuid, error = resolve_puuid(summoner, tagline, region)
            if error:
                flash(error, 'error')
                return redirect(url_for('admin.test_llm'))

            matches = get_recent_matches(region, puuid, count=5)
            if not matches:
                flash('No recent matches found for this summoner.', 'warning')
                return redirect(url_for('admin.test_llm'))

            watcher = get_watcher()
            routing = get_routing_value(region)
            analysis_data = analyze_match(watcher, routing, puuid, matches[0])

            if not analysis_data:
                flash('Failed to analyze the most recent match.', 'error')
                return redirect(url_for('admin.test_llm'))

            return render_template('admin/test_llm.html',
                analysis_data=analysis_data,
                summoner_name=summoner,
                tagline=tagline,
                region=region,
                result=None,
            )

        elif action == 'run_llm':
            import json
            analysis_json = request.form.get('analysis_json', '')
            try:
                analysis_data = json.loads(analysis_json)
            except (json.JSONDecodeError, TypeError):
                flash('Invalid analysis data.', 'error')
                return redirect(url_for('admin.test_llm'))

            result = get_llm_analysis(analysis_data)
            if not result:
                flash('LLM returned no response. Check your LLM_API_KEY and LLM_API_URL in .env.', 'error')

            return render_template('admin/test_llm.html',
                analysis_data=analysis_data,
                summoner_name=analysis_data.get('champion', ''),
                tagline='',
                region='',
                result=result,
            )

    return render_template('admin/test_llm.html', analysis_data=None, result=None)


@admin_bp.route('/test-discord', methods=['POST'])
@admin_required
def test_discord():
    channel_id = request.form.get('channel_id', '').strip()
    message = request.form.get('message', 'Test message from LoL Analyzer admin panel.').strip()

    if not channel_id:
        flash('Channel ID is required.', 'error')
        return redirect(url_for('admin.index'))

    from app.analysis.discord_notifier import send_message
    success = send_message(channel_id, message)

    if success:
        flash(f'Message sent to channel {channel_id}.', 'success')
    else:
        flash('Failed to send Discord message. Check DISCORD_BOT_TOKEN and channel ID.', 'error')

    return redirect(url_for('admin.index'))
