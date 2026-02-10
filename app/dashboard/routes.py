import logging

from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from sqlalchemy import func
from app.dashboard import dashboard_bp
from app.dashboard.forms import RiotAccountForm, DiscordConfigForm, PreferencesForm
from app.models import RiotAccount, DiscordConfig, MatchAnalysis, UserSettings
from app.analysis.riot_api import resolve_puuid, get_watcher, get_routing_value, get_recent_matches
from app.analysis.engine import analyze_match, derive_lane_context
from app.analysis.champion_assets import champion_icon_url, item_icon_url, rune_icons
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


_LANE_ORDER = {'TOP': 0, 'JUNGLE': 1, 'MIDDLE': 2, 'BOTTOM': 3, 'UTILITY': 4}
_LANE_LABEL = {'TOP': 'TOP', 'JUNGLE': 'JGL', 'MIDDLE': 'MID', 'BOTTOM': 'BOT', 'UTILITY': 'SUP'}


def _lane_sort_key(p):
    return _LANE_ORDER.get(p.get('position', ''), 9)


def _participant_view(p: dict, game_duration: float) -> dict:
    """Serialize participant data for UI rendering."""
    if not p:
        return {}
    kills = p.get('kills', 0)
    deaths = p.get('deaths', 0)
    assists = p.get('assists', 0)
    gold = p.get('gold_earned', 0)
    damage = p.get('total_damage', 0)
    cs = p.get('cs', 0)
    vision = p.get('vision_score', 0)
    duration = max(game_duration, 1.0)
    item_ids = p.get('item_ids', []) or []
    items = [
        {'id': item_id, 'icon': item_icon_url(item_id)}
        for item_id in item_ids
        if item_id
    ]
    runes = rune_icons(p.get('primary_rune_id'), p.get('secondary_rune_style_id'))
    return {
        'team_id': p.get('team_id'),
        'champion': p.get('champion', ''),
        'champion_icon': champion_icon_url(p.get('champion', ''), p.get('champion_id')),
        'summoner_name': p.get('summoner_name', ''),
        'tagline': p.get('tagline', ''),
        'position': p.get('position', ''),
        'lane_label': _LANE_LABEL.get(p.get('position', ''), ''),
        'kills': kills,
        'deaths': deaths,
        'assists': assists,
        'kda': round((kills + assists) / max(1, deaths), 2),
        'total_damage': damage,
        'vision_score': vision,
        'cs': cs,
        'gold_per_min': round(gold / duration, 2),
        'damage_per_min': round(damage / duration, 2),
        'cs_per_min': round(cs / duration, 2),
        'vision_per_min': round(vision / duration, 2),
        'gold_earned': gold,
        'primary_rune_id': p.get('primary_rune_id', 0),
        'secondary_rune_style_id': p.get('secondary_rune_style_id', 0),
        'runes': runes,
        'items': items,
        'is_player': bool(p.get('is_player')),
    }


def _serialize_match(m, include_scoreboard: bool = False):
    """Serialize a MatchAnalysis row to a dict for JSON responses."""
    participants = m.participants_json or []
    player_team = None
    player_position = ''
    player_participant = None
    game_duration = max(float(m.game_duration or 0), 1.0)
    for p in participants:
        if p.get('is_player'):
            player_team = p.get('team_id')
            player_position = p.get('position', '')
            player_participant = p
            break

    enemies = []
    allies = []
    ally_comp = []
    enemy_comp = []
    lane_matchups = []
    scoreboard_rows = []
    visuals = {
        'player': {},
        'team_avg': {},
        'lobby_avg': {},
        'shares': {},
        'lane': {},
    }
    if player_team is not None:
        enemy_participants = sorted(
            [p for p in participants if p.get('team_id') != player_team],
            key=_lane_sort_key,
        )
        ally_participants = sorted(
            [p for p in participants if p.get('team_id') == player_team],
            key=_lane_sort_key,
        )
        enemies = [_participant_view(p, game_duration) for p in enemy_participants]
        allies = [_participant_view(p, game_duration) for p in ally_participants if not p.get('is_player')]
        ally_comp = [_participant_view(p, game_duration) for p in ally_participants]
        enemy_comp = [_participant_view(p, game_duration) for p in enemy_participants]

        for lane in ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']:
            ally_lane = next((p for p in ally_participants if p.get('position') == lane), None)
            enemy_lane = next((p for p in enemy_participants if p.get('position') == lane), None)
            if ally_lane or enemy_lane:
                lane_matchups.append({
                    'lane': lane,
                    'lane_label': _LANE_LABEL.get(lane, lane),
                    'ally': _participant_view(ally_lane, game_duration) if ally_lane else None,
                    'enemy': _participant_view(enemy_lane, game_duration) if enemy_lane else None,
                })

        def _avg_rate(team: list[dict], key: str) -> float:
            if not team:
                return 0.0
            return round(sum(p.get(key, 0) for p in team) / len(team) / game_duration, 2)

        def _avg_kda(team: list[dict]) -> float:
            if not team:
                return 0.0
            total = 0.0
            for p in team:
                total += (p.get('kills', 0) + p.get('assists', 0)) / max(1, p.get('deaths', 0))
            return round(total / len(team), 2)

        ally_team_kills = sum(p.get('kills', 0) for p in ally_participants)
        player_gold = player_participant.get('gold_earned', 0) if player_participant else 0
        player_damage = player_participant.get('total_damage', 0) if player_participant else 0
        player_cs = player_participant.get('cs', 0) if player_participant else 0
        player_vision = player_participant.get('vision_score', 0) if player_participant else 0
        ally_total_gold = sum(p.get('gold_earned', 0) for p in ally_participants)
        ally_total_damage = sum(p.get('total_damage', 0) for p in ally_participants)
        ally_total_cs = sum(p.get('cs', 0) for p in ally_participants)
        ally_total_vision = sum(p.get('vision_score', 0) for p in ally_participants)
        player_kp = 0.0
        if ally_team_kills > 0 and player_participant:
            player_kp = round(((player_participant.get('kills', 0) + player_participant.get('assists', 0)) / ally_team_kills) * 100, 1)

        visuals['team_avg'] = {
            'gold_per_min': _avg_rate(ally_participants, 'gold_earned'),
            'damage_per_min': _avg_rate(ally_participants, 'total_damage'),
            'cs_per_min': _avg_rate(ally_participants, 'cs'),
            'vision_per_min': _avg_rate(ally_participants, 'vision_score'),
            'kda': _avg_kda(ally_participants),
        }
        visuals['lobby_avg'] = {
            'gold_per_min': _avg_rate(participants, 'gold_earned'),
            'damage_per_min': _avg_rate(participants, 'total_damage'),
            'cs_per_min': _avg_rate(participants, 'cs'),
            'vision_per_min': _avg_rate(participants, 'vision_score'),
            'kda': _avg_kda(participants),
        }
        visuals['shares'] = {
            'gold_share_pct': round((player_gold / ally_total_gold) * 100, 1) if ally_total_gold else 0.0,
            'damage_share_pct': round((player_damage / ally_total_damage) * 100, 1) if ally_total_damage else 0.0,
            'cs_share_pct': round((player_cs / ally_total_cs) * 100, 1) if ally_total_cs else 0.0,
            'vision_share_pct': round((player_vision / ally_total_vision) * 100, 1) if ally_total_vision else 0.0,
            'kill_participation_pct': player_kp,
        }

        lane_opponent = next(
            (p for p in enemy_participants if p.get('position') and p.get('position') == player_position),
            None,
        )
        if lane_opponent and player_participant:
            player_kda = round((player_participant.get('kills', 0) + player_participant.get('assists', 0)) / max(1, player_participant.get('deaths', 0)), 2)
            opp_kda = round((lane_opponent.get('kills', 0) + lane_opponent.get('assists', 0)) / max(1, lane_opponent.get('deaths', 0)), 2)
            visuals['lane'] = {
                'opponent': _participant_view(lane_opponent, game_duration),
                'gpm_delta': round((player_participant.get('gold_earned', 0) - lane_opponent.get('gold_earned', 0)) / game_duration, 2),
                'dpm_delta': round((player_participant.get('total_damage', 0) - lane_opponent.get('total_damage', 0)) / game_duration, 2),
                'cspm_delta': round((player_participant.get('cs', 0) - lane_opponent.get('cs', 0)) / game_duration, 2),
                'vpm_delta': round((player_participant.get('vision_score', 0) - lane_opponent.get('vision_score', 0)) / game_duration, 2),
                'kda_delta': round(player_kda - opp_kda, 2),
            }

        if include_scoreboard:
            scoreboard_participants = []
            for p in ally_participants:
                pv = _participant_view(p, game_duration)
                pv['side'] = 'ALLY'
                scoreboard_participants.append(pv)
            for p in enemy_participants:
                pv = _participant_view(p, game_duration)
                pv['side'] = 'ENEMY'
                scoreboard_participants.append(pv)
            max_damage = max((p.get('total_damage', 0) for p in scoreboard_participants), default=0)
            for pv in scoreboard_participants:
                pv['damage_pct'] = round((pv.get('total_damage', 0) / max_damage) * 100, 1) if max_damage else 0.0
                scoreboard_rows.append(pv)

    if player_participant:
        pv = _participant_view(player_participant, game_duration)
        visuals['player'] = {
            'gold_per_min': pv['gold_per_min'],
            'damage_per_min': pv['damage_per_min'],
            'cs_per_min': pv['cs_per_min'],
            'vision_per_min': pv['vision_per_min'],
            'kda': pv['kda'],
        }
    else:
        visuals['player'] = {
            'gold_per_min': m.gold_per_min,
            'damage_per_min': m.damage_per_min,
            'cs_per_min': round((m.cs_total or 0) / game_duration, 2),
            'vision_per_min': round((m.vision_score or 0) / game_duration, 2),
            'kda': m.kda,
        }

    return {
        'id': m.id,
        'match_id': m.match_id,
        'champion': m.champion,
        'champion_icon': champion_icon_url(m.champion),
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
        'player_position': player_position,
        'player_position_label': _LANE_LABEL.get(player_position, ''),
        'enemies': enemies,
        'allies': allies,
        'ally_comp': ally_comp,
        'enemy_comp': enemy_comp,
        'lane_matchups': lane_matchups,
        'scoreboard_rows': scoreboard_rows,
        'visuals': visuals,
        'analyzed_at': m.analyzed_at.isoformat() if m.analyzed_at else '',
    }


def _serialize_matches(match_list):
    """Serialize a list of MatchAnalysis rows."""
    return [_serialize_match(m, include_scoreboard=False) for m in match_list]


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
    riot_account = RiotAccount.query.filter_by(user_id=current_user.id).first()
    payload = request.get_json(silent=True)
    force = bool(payload.get('force')) if isinstance(payload, dict) else False

    if match.llm_analysis and not force:
        return jsonify({'analysis': match.llm_analysis, 'cached': True})

    participants = match.participants_json or []
    player_position, lane_opponent = derive_lane_context(participants)

    analysis_dict = {
        'match_id': match.match_id,
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
        'queue_type': match.queue_type,
        'player_position': player_position,
        'lane_opponent': lane_opponent,
        'participants': participants,
        'platform_region': riot_account.region if riot_account else '',
        'player_puuid': riot_account.puuid if riot_account else '',
    }

    result, error = get_llm_analysis_detailed(analysis_dict)
    if error:
        if match.llm_analysis:
            return jsonify({
                'analysis': match.llm_analysis,
                'cached': True,
                'stale': True,
                'error': error,
            }), 200
        status = 504 if 'timed out' in error.lower() else 502
        return jsonify({'error': error}), status

    match.llm_analysis = result
    db.session.commit()

    return jsonify({'analysis': result, 'cached': False, 'regenerated': force})


@dashboard_bp.route('/matches')
@login_required
def matches():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    pagination = MatchAnalysis.query.filter_by(user_id=current_user.id)\
        .order_by(*_match_order)\
        .paginate(page=page, per_page=per_page, error_out=False)
    initial_matches = _serialize_matches(pagination.items)

    return render_template('dashboard/matches.html',
        matches=pagination.items,
        pagination=pagination,
        initial_matches_json=initial_matches,
    )


@dashboard_bp.route('/matches/<int:match_db_id>')
@login_required
def match_detail(match_db_id):
    analysis = MatchAnalysis.query.filter_by(id=match_db_id, user_id=current_user.id).first_or_404()
    match_view = _serialize_match(analysis, include_scoreboard=True)
    return render_template('dashboard/match_detail.html', analysis=analysis, match_view=match_view)


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
