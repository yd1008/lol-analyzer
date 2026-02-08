import logging

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from app.dashboard import dashboard_bp
from app.dashboard.forms import RiotAccountForm, DiscordConfigForm, PreferencesForm
from app.models import RiotAccount, DiscordConfig, MatchAnalysis, UserSettings
from app.analysis.riot_api import resolve_puuid, get_watcher, get_routing_value, get_recent_matches
from app.analysis.engine import analyze_match
from app.analysis.llm import get_llm_analysis_detailed
from app.analysis.discord_notifier import get_bot_invite_url
from app.extensions import db

logger = logging.getLogger(__name__)

# Order matches by game time (newest first), falling back to analyzed_at for old data
_match_order = (
    func.coalesce(MatchAnalysis.game_start_timestamp, 0).desc(),
    MatchAnalysis.analyzed_at.desc(),
)


def sync_recent_matches(user_id, region, puuid):
    """Fetch recent matches from Riot API, analyze new ones, and store in DB."""
    match_ids = get_recent_matches(region, puuid, count=10)
    if not match_ids:
        return 0

    existing = {m.match_id for m in
                MatchAnalysis.query.filter(
                    MatchAnalysis.user_id == user_id,
                    MatchAnalysis.match_id.in_(match_ids),
                ).all()}

    new_ids = [mid for mid in match_ids if mid not in existing]
    if not new_ids:
        return 0

    watcher = get_watcher()
    routing = get_routing_value(region)
    saved = 0

    for match_id in new_ids:
        analysis = analyze_match(watcher, routing, puuid, match_id)
        if not analysis:
            continue

        row = MatchAnalysis(
            user_id=user_id,
            match_id=analysis['match_id'],
            champion=analysis['champion'],
            win=analysis['win'],
            kills=analysis['kills'],
            deaths=analysis['deaths'],
            assists=analysis['assists'],
            kda=analysis['kda'],
            gold_earned=analysis['gold_earned'],
            gold_per_min=analysis['gold_per_min'],
            total_damage=analysis['total_damage'],
            damage_per_min=analysis['damage_per_min'],
            vision_score=analysis['vision_score'],
            cs_total=analysis['cs_total'],
            game_duration=analysis['game_duration'],
            recommendations=analysis['recommendations'],
            queue_type=analysis.get('queue_type'),
            participants_json=analysis.get('participants'),
            game_start_timestamp=analysis.get('game_start_timestamp'),
        )
        db.session.add(row)
        saved += 1

    if saved:
        db.session.commit()
        logger.info("Synced %d new matches for user %d", saved, user_id)

    return saved


@dashboard_bp.route('/')
@login_required
def index():
    riot_account = RiotAccount.query.filter_by(user_id=current_user.id).first()
    discord_config = DiscordConfig.query.filter_by(user_id=current_user.id).first()

    if riot_account and riot_account.puuid:
        try:
            sync_recent_matches(current_user.id, riot_account.region, riot_account.puuid)
        except Exception as e:
            db.session.rollback()
            logger.error("Failed to sync matches for user %d: %s", current_user.id, e)

    base_query = MatchAnalysis.query.filter_by(user_id=current_user.id)

    analyses = base_query\
        .order_by(*_match_order).limit(10).all()

    total_games = base_query.count()
    wins = MatchAnalysis.query.filter_by(user_id=current_user.id, win=True).count()
    win_rate = round((wins / total_games) * 100, 1) if total_games > 0 else 0

    all_matches = base_query.all()
    avg_kda = round(sum(m.kda for m in all_matches) / len(all_matches), 2) if all_matches else 0

    initial_matches = _serialize_matches(analyses)

    return render_template('dashboard/index.html',
        analyses=analyses,
        initial_matches_json=initial_matches,
        total_games=total_games,
        wins=wins,
        win_rate=win_rate,
        avg_kda=avg_kda,
        riot_account=riot_account,
        discord_config=discord_config,
    )


def _serialize_match(m):
    """Serialize a MatchAnalysis row to a dict for JSON responses."""
    participants = m.participants_json or []
    player_team = None
    for p in participants:
        if p.get('is_player'):
            player_team = p.get('team_id')
            break

    enemies = []
    if player_team is not None:
        enemies = [
            {'champion': p['champion'], 'summoner_name': p.get('summoner_name', ''), 'tagline': p.get('tagline', '')}
            for p in participants
            if p.get('team_id') != player_team
        ]

    return {
        'id': m.id,
        'match_id': m.match_id,
        'champion': m.champion,
        'win': m.win,
        'kills': m.kills,
        'deaths': m.deaths,
        'assists': m.assists,
        'kda': m.kda,
        'gold_per_min': m.gold_per_min,
        'damage_per_min': m.damage_per_min,
        'vision_score': m.vision_score,
        'cs_total': m.cs_total,
        'game_duration': m.game_duration,
        'queue_type': m.queue_type or '',
        'has_llm_analysis': bool(m.llm_analysis),
        'enemies': enemies,
        'analyzed_at': m.analyzed_at.isoformat() if m.analyzed_at else '',
    }


def _serialize_matches(match_list):
    """Serialize a list of MatchAnalysis rows."""
    return [_serialize_match(m) for m in match_list]


@dashboard_bp.route('/api/matches')
@login_required
def api_matches():
    """JSON endpoint for match list with pagination and queue filter."""
    offset = request.args.get('offset', 0, type=int)
    limit = request.args.get('limit', 10, type=int)
    limit = min(limit, 50)
    queue = request.args.get('queue', '', type=str)

    query = MatchAnalysis.query.filter_by(user_id=current_user.id)

    if queue:
        queue_list = [q.strip() for q in queue.split(',')]
        query = query.filter(MatchAnalysis.queue_type.in_(queue_list))

    total = query.count()

    matches_list = query.order_by(*_match_order)\
        .offset(offset).limit(limit).all()

    return jsonify({
        'matches': _serialize_matches(matches_list),
        'total': total,
        'has_more': offset + limit < total,
    })


@dashboard_bp.route('/api/matches/<int:match_db_id>/ai-analysis', methods=['POST'])
@login_required
def api_ai_analysis(match_db_id):
    """Run or return cached AI analysis for a match."""
    match = MatchAnalysis.query.filter_by(id=match_db_id, user_id=current_user.id).first_or_404()

    if match.llm_analysis:
        return jsonify({'analysis': match.llm_analysis, 'cached': True})

    analysis_dict = {
        'champion': match.champion,
        'win': match.win,
        'kills': match.kills,
        'deaths': match.deaths,
        'assists': match.assists,
        'kda': match.kda,
        'gold_earned': match.gold_earned,
        'gold_per_min': match.gold_per_min,
        'total_damage': match.total_damage,
        'damage_per_min': match.damage_per_min,
        'vision_score': match.vision_score,
        'cs_total': match.cs_total,
        'game_duration': match.game_duration,
    }

    result, error = get_llm_analysis_detailed(analysis_dict)
    if error:
        return jsonify({'error': error}), 500

    match.llm_analysis = result
    db.session.commit()

    return jsonify({'analysis': result, 'cached': False})


@dashboard_bp.route('/matches')
@login_required
def matches():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    pagination = MatchAnalysis.query.filter_by(user_id=current_user.id)\
        .order_by(*_match_order)\
        .paginate(page=page, per_page=per_page, error_out=False)

    return render_template('dashboard/matches.html',
        matches=pagination.items,
        pagination=pagination,
    )


@dashboard_bp.route('/matches/<int:match_db_id>')
@login_required
def match_detail(match_db_id):
    analysis = MatchAnalysis.query.filter_by(id=match_db_id, user_id=current_user.id).first_or_404()
    return render_template('dashboard/match_detail.html', analysis=analysis)


@dashboard_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    riot_account = RiotAccount.query.filter_by(user_id=current_user.id).first()
    discord_config = DiscordConfig.query.filter_by(user_id=current_user.id).first()
    user_settings = current_user.settings

    riot_form = RiotAccountForm(prefix='riot')
    discord_form = DiscordConfigForm(prefix='discord')
    prefs_form = PreferencesForm(prefix='prefs')

    if riot_account:
        riot_form.summoner_name.data = riot_account.summoner_name
        riot_form.tagline.data = riot_account.tagline
        riot_form.region.data = riot_account.region

    if discord_config:
        discord_form.channel_id.data = discord_config.channel_id
        discord_form.guild_id.data = discord_config.guild_id

    if user_settings:
        prefs_form.check_interval.data = str(user_settings.check_interval)
        prefs_form.weekly_summary_day.data = user_settings.weekly_summary_day
        prefs_form.weekly_summary_time.data = user_settings.weekly_summary_time
        prefs_form.notifications_enabled.data = user_settings.notifications_enabled

    bot_invite_url = get_bot_invite_url()

    return render_template('dashboard/settings.html',
        riot_form=riot_form,
        discord_form=discord_form,
        prefs_form=prefs_form,
        riot_account=riot_account,
        discord_config=discord_config,
        bot_invite_url=bot_invite_url,
    )


@dashboard_bp.route('/settings/riot', methods=['POST'])
@login_required
def settings_riot():
    form = RiotAccountForm(prefix='riot')
    if form.validate_on_submit():
        puuid, error = resolve_puuid(form.summoner_name.data, form.tagline.data, form.region.data)
        if error:
            flash(error, 'error')
            return redirect(url_for('dashboard.settings'))

        riot_account = RiotAccount.query.filter_by(user_id=current_user.id).first()
        if riot_account:
            riot_account.summoner_name = form.summoner_name.data
            riot_account.tagline = form.tagline.data
            riot_account.region = form.region.data
            riot_account.puuid = puuid
            riot_account.is_verified = True
        else:
            riot_account = RiotAccount(
                user_id=current_user.id,
                summoner_name=form.summoner_name.data,
                tagline=form.tagline.data,
                region=form.region.data,
                puuid=puuid,
                is_verified=True,
            )
            db.session.add(riot_account)

        db.session.commit()

        try:
            count = sync_recent_matches(current_user.id, riot_account.region, riot_account.puuid)
            if count:
                flash(f'Riot account linked! Imported {count} recent matches.', 'success')
            else:
                flash('Riot account linked successfully!', 'success')
        except Exception as e:
            logger.error("Failed to sync matches after linking for user %d: %s", current_user.id, e)
            flash('Riot account linked, but match import failed. Matches will sync on dashboard.', 'warning')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{error}', 'error')

    return redirect(url_for('dashboard.settings'))


@dashboard_bp.route('/settings/discord', methods=['POST'])
@login_required
def settings_discord():
    form = DiscordConfigForm(prefix='discord')
    if form.validate_on_submit():
        discord_config = DiscordConfig.query.filter_by(user_id=current_user.id).first()
        if discord_config:
            discord_config.channel_id = form.channel_id.data
            discord_config.guild_id = form.guild_id.data
        else:
            discord_config = DiscordConfig(
                user_id=current_user.id,
                channel_id=form.channel_id.data,
                guild_id=form.guild_id.data,
            )
            db.session.add(discord_config)

        db.session.commit()
        flash('Discord configuration saved!', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{error}', 'error')

    return redirect(url_for('dashboard.settings'))


@dashboard_bp.route('/settings/preferences', methods=['POST'])
@login_required
def settings_preferences():
    form = PreferencesForm(prefix='prefs')
    if form.validate_on_submit():
        settings = current_user.settings
        if not settings:
            settings = UserSettings(user_id=current_user.id)
            db.session.add(settings)

        settings.check_interval = int(form.check_interval.data)
        settings.weekly_summary_day = form.weekly_summary_day.data
        settings.weekly_summary_time = form.weekly_summary_time.data
        settings.notifications_enabled = form.notifications_enabled.data

        db.session.commit()
        flash('Preferences saved!', 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(f'{error}', 'error')

    return redirect(url_for('dashboard.settings'))
