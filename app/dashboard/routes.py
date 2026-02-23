import json
import logging

from flask import render_template, redirect, url_for, flash, request, jsonify, Response, stream_with_context
from flask_login import login_required, current_user
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from app.dashboard import dashboard_bp
from app.dashboard.forms import RiotAccountForm, DiscordConfigForm, PreferencesForm
from app.models import RiotAccount, DiscordConfig, MatchAnalysis, UserSettings
from app.analysis.riot_api import resolve_puuid, get_watcher, get_routing_value, get_recent_matches
from app.analysis.engine import analyze_match, derive_lane_context
from app.analysis.champion_assets import champion_icon_url, item_icon_url, rune_icons
from app.analysis.llm import get_llm_analysis_detailed, iter_llm_analysis_stream
from app.analysis.discord_notifier import get_bot_invite_url
from app.i18n import (
    champion_name,
    get_locale,
    lane_label,
    lt,
    normalize_locale,
    queue_label,
    resolve_api_language,
    t,
    weekday_label,
)
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
        try:
            db.session.commit()
            saved += 1
        except IntegrityError:
            db.session.rollback()
            logger.info(
                "Skipped duplicate match insert user=%d match_id=%s due to unique constraint",
                user_id,
                analysis['match_id'],
            )

    if saved:
        logger.info("Synced %d new matches for user %d", saved, user_id)

    return saved


def _build_ai_coach_plan(matches: list[MatchAnalysis]) -> dict:
    """Build a deterministic AI coaching focus plan from recent matches."""
    if not matches:
        return {
            'coach_score': 0,
            'strengths': [],
            'focus_areas': [],
            'next_game_goal': lt('Play one match to unlock your first coaching plan.', '先完成一局对战即可生成你的首个教练计划。'),
        }

    total_games = len(matches)
    wins = sum(1 for m in matches if m.win)
    win_rate = (wins / total_games) * 100 if total_games else 0

    avg_kda = sum((m.kda or 0) for m in matches) / total_games
    avg_dpm = sum((m.damage_per_min or 0) for m in matches) / total_games
    avg_gpm = sum((m.gold_per_min or 0) for m in matches) / total_games
    avg_vision = sum((m.vision_score or 0) for m in matches) / total_games

    score = 50
    score += min(20, (win_rate - 50) * 0.8)
    score += min(15, max(-10, (avg_kda - 3.0) * 5))
    score += min(10, max(-10, (avg_dpm - 650) / 60))
    score += min(8, max(-8, (avg_gpm - 380) / 25))
    score += min(8, max(-8, (avg_vision - 22) / 3))
    coach_score = int(max(1, min(100, round(score))))

    strengths = []
    if win_rate >= 55:
        strengths.append(lt('Strong conversion: your recent win rate is above 55%.', '转化能力强：近期胜率高于 55%。'))
    if avg_kda >= 3.5:
        strengths.append(lt('Reliable skirmish execution with high average KDA.', '团战/小规模交锋执行稳定，平均 KDA 较高。'))
    if avg_dpm >= 700:
        strengths.append(lt('Healthy damage pressure in recent games.', '最近对局的输出压制力不错。'))
    if avg_vision >= 25:
        strengths.append(lt('Vision fundamentals are above baseline.', '视野基本功高于基准线。'))

    focus_areas = []
    if win_rate < 50:
        focus_areas.append(lt('Prioritize cleaner mid-game decision making around objectives.', '优先提升中期围绕资源点的决策质量。'))
    if avg_kda < 2.8:
        focus_areas.append(lt('Reduce avoidable deaths: in extended skirmishes, disengage before overextending and keep deaths at 4 or fewer per game.', '减少可避免死亡：优化推线后的回撤与转线时机。'))
    if avg_gpm < 360:
        focus_areas.append(lt('Improve economy: maintain farm tempo between fights.', '提升经济效率：团战间隙维持补刀节奏。'))
    if avg_vision < 18:
        focus_areas.append(lt('Upgrade vision routine: one control ward every reset cycle.', '强化视野习惯：每次回城至少补一个控制守卫。'))

    if not strengths:
        strengths.append(lt('Your baseline is stable—good foundation to scale from.', '你的基础盘面较稳定，是持续进步的良好起点。'))
    if not focus_areas:
        focus_areas.append(lt('Keep execution sharp and push for higher objective conversion.', '保持执行力，并进一步提高资源点转化率。'))

    next_game_goal = lt(
        'Next game goal: maintain deaths ≤ 4 while keeping gold/min above 380.',
        '下局目标：将死亡控制在 ≤4，同时保持每分钟经济 >380。',
    )
    if avg_kda >= 3.5 and avg_gpm >= 390:
        next_game_goal = lt(
            'Next game goal: convert your lead by securing first two neutral objectives.',
            '下局目标：把优势转化为前两条中立资源控制。',
        )

    return {
        'coach_score': coach_score,
        'strengths': strengths[:3],
        'focus_areas': focus_areas[:3],
        'next_game_goal': next_game_goal,
    }


def _build_trend_snapshot(matches: list[MatchAnalysis]) -> dict:
    """Compare recent window vs previous window to show trajectory."""
    if not matches:
        return {
            'headline': lt('No trend yet', '暂无趋势数据'),
            'signals': [lt('Complete more matches to unlock trend intelligence.', '完成更多对局后可解锁趋势洞察。')],
        }

    recent = matches[:5]
    previous = matches[5:10]
    if not previous:
        return {
            'headline': lt('Collecting baseline', '正在建立基线'),
            'signals': [lt('Play 5 more matches to compare your trajectory.', '再完成 5 局后可对比成长轨迹。')],
        }

    def _avg(rows: list[MatchAnalysis], field: str) -> float:
        vals = [getattr(r, field) or 0 for r in rows]
        return sum(vals) / len(vals) if vals else 0.0

    recent_win = sum(1 for r in recent if r.win) / len(recent)
    prev_win = sum(1 for r in previous if r.win) / len(previous)

    deltas = {
        'win_rate': round((recent_win - prev_win) * 100, 1),
        'kda': round(_avg(recent, 'kda') - _avg(previous, 'kda'), 2),
        'gpm': round(_avg(recent, 'gold_per_min') - _avg(previous, 'gold_per_min'), 1),
        'dpm': round(_avg(recent, 'damage_per_min') - _avg(previous, 'damage_per_min'), 1),
    }

    positives = sum(1 for value in deltas.values() if value > 0)
    if positives >= 3:
        headline = lt('You are trending up', '你正在上升期')
    elif positives <= 1:
        headline = lt('Stabilize fundamentals this week', '本周先稳住基本功')
    else:
        headline = lt('Mixed trend — refine execution', '趋势分化，建议精炼执行细节')

    def _signal(label_en: str, label_zh: str, value: float, suffix: str = '') -> str:
        arrow = '↑' if value > 0 else ('↓' if value < 0 else '→')
        prefix = '+' if value > 0 else ''
        text = f"{arrow} {lt(label_en, label_zh)} {prefix}{value}{suffix}"
        return text

    signals = [
        _signal('Win rate delta', '胜率变化', deltas['win_rate'], '%'),
        _signal('KDA delta', 'KDA 变化', deltas['kda']),
        _signal('Gold/min delta', '每分钟经济变化', deltas['gpm']),
        _signal('Damage/min delta', '每分钟伤害变化', deltas['dpm']),
    ]

    return {
        'headline': headline,
        'signals': signals,
    }


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

    avg_kda_raw = db.session.query(func.avg(MatchAnalysis.kda)).filter_by(user_id=current_user.id).scalar()
    avg_kda = round(float(avg_kda_raw), 2) if avg_kda_raw is not None else 0

    initial_matches = _serialize_matches(analyses)
    coach_plan = _build_ai_coach_plan(analyses)
    trend_snapshot = _build_trend_snapshot(analyses)

    return render_template('dashboard/index.html',
        analyses=analyses,
        initial_matches_json=initial_matches,
        total_games=total_games,
        wins=wins,
        win_rate=win_rate,
        avg_kda=avg_kda,
        coach_plan=coach_plan,
        trend_snapshot=trend_snapshot,
        riot_account=riot_account,
        discord_config=discord_config,
    )


_LANE_ORDER = {'TOP': 0, 'JUNGLE': 1, 'MIDDLE': 2, 'BOTTOM': 3, 'UTILITY': 4}


def _lane_sort_key(p):
    return _LANE_ORDER.get(p.get('position', ''), 9)


def _participant_view(p: dict, game_duration: float, locale: str | None = None) -> dict:
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
        'champion_label': champion_name(p.get('champion', ''), locale=locale),
        'champion_icon': champion_icon_url(p.get('champion', ''), p.get('champion_id')),
        'summoner_name': p.get('summoner_name', ''),
        'tagline': p.get('tagline', ''),
        'position': p.get('position', ''),
        'lane_label': lane_label(p.get('position', ''), short=True, locale=locale),
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


def _serialize_match(m, include_scoreboard: bool = False, locale: str | None = None):
    """Serialize a MatchAnalysis row to a dict for JSON responses."""
    locale = locale or get_locale()
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
        enemies = [_participant_view(p, game_duration, locale=locale) for p in enemy_participants]
        allies = [_participant_view(p, game_duration, locale=locale) for p in ally_participants if not p.get('is_player')]
        ally_comp = [_participant_view(p, game_duration, locale=locale) for p in ally_participants]
        enemy_comp = [_participant_view(p, game_duration, locale=locale) for p in enemy_participants]

        for lane in ['TOP', 'JUNGLE', 'MIDDLE', 'BOTTOM', 'UTILITY']:
            ally_lane = next((p for p in ally_participants if p.get('position') == lane), None)
            enemy_lane = next((p for p in enemy_participants if p.get('position') == lane), None)
            if ally_lane or enemy_lane:
                lane_matchups.append({
                    'lane': lane,
                    'lane_label': lane_label(lane, short=True, locale=locale),
                    'ally': _participant_view(ally_lane, game_duration, locale=locale) if ally_lane else None,
                    'enemy': _participant_view(enemy_lane, game_duration, locale=locale) if enemy_lane else None,
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
                'opponent': _participant_view(lane_opponent, game_duration, locale=locale),
                'gpm_delta': round((player_participant.get('gold_earned', 0) - lane_opponent.get('gold_earned', 0)) / game_duration, 2),
                'dpm_delta': round((player_participant.get('total_damage', 0) - lane_opponent.get('total_damage', 0)) / game_duration, 2),
                'cspm_delta': round((player_participant.get('cs', 0) - lane_opponent.get('cs', 0)) / game_duration, 2),
                'vpm_delta': round((player_participant.get('vision_score', 0) - lane_opponent.get('vision_score', 0)) / game_duration, 2),
                'kda_delta': round(player_kda - opp_kda, 2),
            }

        if include_scoreboard:
            scoreboard_participants = []
            for p in ally_participants:
                pv = _participant_view(p, game_duration, locale=locale)
                pv['side'] = 'ALLY'
                scoreboard_participants.append(pv)
            for p in enemy_participants:
                pv = _participant_view(p, game_duration, locale=locale)
                pv['side'] = 'ENEMY'
                scoreboard_participants.append(pv)
            max_damage = max((p.get('total_damage', 0) for p in scoreboard_participants), default=0)
            for pv in scoreboard_participants:
                pv['damage_pct'] = round((pv.get('total_damage', 0) / max_damage) * 100, 1) if max_damage else 0.0
                scoreboard_rows.append(pv)

    if player_participant:
        pv = _participant_view(player_participant, game_duration, locale=locale)
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

    initial_ai_analysis = _get_cached_analysis(m, locale) or ''
    has_llm_analysis_en = bool(m.llm_analysis_en or m.llm_analysis)
    has_llm_analysis_zh = bool(m.llm_analysis_zh)
    has_llm_analysis = has_llm_analysis_zh if locale == 'zh-CN' else has_llm_analysis_en

    return {
        'id': m.id,
        'match_id': m.match_id,
        'champion': m.champion,
        'champion_label': champion_name(m.champion, locale=locale),
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
        'queue_type_label': queue_label(m.queue_type or '', locale=locale),
        'initial_ai_analysis': initial_ai_analysis,
        'has_llm_analysis': has_llm_analysis,
        'has_llm_analysis_en': has_llm_analysis_en,
        'has_llm_analysis_zh': has_llm_analysis_zh,
        'player_position': player_position,
        'player_position_label': lane_label(player_position, short=True, locale=locale),
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
    locale = get_locale()
    return [_serialize_match(m, include_scoreboard=False, locale=locale) for m in match_list]


_ALLOWED_COACH_MODES = {'balanced', 'aggressive', 'supportive'}


def _resolve_coach_mode(value: str | None) -> str:
    mode = (value or '').strip().lower()
    return mode if mode in _ALLOWED_COACH_MODES else 'balanced'


def _build_llm_analysis_payload(
    match: MatchAnalysis,
    riot_account: RiotAccount | None,
    coach_mode: str = 'balanced',
) -> dict:
    participants = match.participants_json or []
    player_position, lane_opponent = derive_lane_context(participants)
    return {
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
        'coach_mode': _resolve_coach_mode(coach_mode),
    }


_ALLOWED_COACH_FOCUS = {
    'general',
    'laning',
    'teamfight',
    'macro',
    'vision',
    'mechanics',
}


def _resolve_coach_focus(value: str | None) -> str:
    focus = (value or '').strip().lower()
    return focus if focus in _ALLOWED_COACH_FOCUS else 'general'


def _analysis_column_for_language(language: str) -> str:
    return 'llm_analysis_zh' if language == 'zh-CN' else 'llm_analysis_en'


def _get_cached_analysis(match: MatchAnalysis, language: str) -> str | None:
    column = _analysis_column_for_language(language)
    cached = getattr(match, column, None)
    if cached:
        return cached
    if language == 'en' and match.llm_analysis:
        return match.llm_analysis
    return None


def _set_cached_analysis(match: MatchAnalysis, language: str, analysis_text: str) -> None:
    column = _analysis_column_for_language(language)
    setattr(match, column, analysis_text)
    # Keep legacy column populated for backward compatibility.
    if language == 'en':
        match.llm_analysis = analysis_text


def _ai_error_status(error: str) -> int:
    error_l = (error or '').lower()
    if 'timed out' in error_l:
        return 504
    if (
        'not compatible with /chat/completions' in error_l
        or 'not available on opencode zen' in error_l
        or 'llm_' in error_l
    ):
        return 400
    return 502


def _ndjson_line(event: dict) -> str:
    return json.dumps(event, ensure_ascii=False) + '\n'


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
    language = resolve_api_language(payload.get('language') if isinstance(payload, dict) else None)
    coach_mode = _resolve_coach_mode(payload.get('coach_mode') if isinstance(payload, dict) else None)
    focus = _resolve_coach_focus(payload.get('focus') if isinstance(payload, dict) else None)
    cache_read_enabled = focus == 'general'
    persist_generated_analysis = True
    cached_analysis = _get_cached_analysis(match, language) if cache_read_enabled else None

    if cached_analysis and not force:
        return jsonify({'analysis': cached_analysis, 'cached': True, 'language': language, 'focus': focus, 'persisted': True})

    analysis_dict = _build_llm_analysis_payload(match, riot_account, coach_mode=coach_mode)

    result, error = get_llm_analysis_detailed(analysis_dict, language=language, focus=focus)
    if error:
        if cached_analysis:
            return jsonify({
                'analysis': cached_analysis,
                'cached': True,
                'stale': True,
                'error': error,
                'language': language,
                'focus': focus,
                'persisted': True,
            }), 200
        status = _ai_error_status(error)
        return jsonify({'error': error, 'language': language, 'focus': focus}), status

    if result and persist_generated_analysis:
        _set_cached_analysis(match, language, result)
        db.session.commit()

    return jsonify({
        'analysis': result,
        'cached': False,
        'regenerated': force or (not cache_read_enabled),
        'language': language,
        'focus': focus,
        'persisted': persist_generated_analysis,
    })


@dashboard_bp.route('/api/matches/<int:match_db_id>/ai-analysis/stream', methods=['POST'])
@login_required
def api_ai_analysis_stream(match_db_id):
    """Stream AI analysis events as NDJSON for progressive UI rendering."""
    match = MatchAnalysis.query.filter_by(id=match_db_id, user_id=current_user.id).first_or_404()
    riot_account = RiotAccount.query.filter_by(user_id=current_user.id).first()
    payload = request.get_json(silent=True)
    force = bool(payload.get('force')) if isinstance(payload, dict) else False
    language = resolve_api_language(payload.get('language') if isinstance(payload, dict) else None)
    coach_mode = _resolve_coach_mode(payload.get('coach_mode') if isinstance(payload, dict) else None)
    focus = _resolve_coach_focus(payload.get('focus') if isinstance(payload, dict) else None)
    cache_read_enabled = focus == 'general'
    persist_generated_analysis = True
    cached_analysis = _get_cached_analysis(match, language) if cache_read_enabled else None

    def event_stream():
        if cached_analysis and not force:
            yield _ndjson_line({'type': 'meta', 'cached': True, 'regenerated': False, 'language': language, 'focus': focus, 'persisted': True})
            yield _ndjson_line({
                'type': 'done',
                'analysis': cached_analysis,
                'cached': True,
                'regenerated': False,
                'language': language,
                'focus': focus,
                'persisted': True,
            })
            return

        yield _ndjson_line({'type': 'meta', 'cached': False, 'regenerated': force or (not cache_read_enabled), 'language': language, 'focus': focus, 'persisted': persist_generated_analysis})
        analysis_dict = _build_llm_analysis_payload(match, riot_account, coach_mode=coach_mode)
        for event in iter_llm_analysis_stream(analysis_dict, language=language, focus=focus):
            event_type = event.get('type')
            if event_type == 'chunk':
                delta = event.get('delta', '')
                if delta:
                    yield _ndjson_line({'type': 'chunk', 'delta': delta})
                continue

            if event_type == 'done':
                final_text = event.get('analysis', '')
                if final_text and persist_generated_analysis:
                    _set_cached_analysis(match, language, final_text)
                    db.session.commit()
                yield _ndjson_line({
                    'type': 'done',
                    'analysis': final_text,
                    'cached': False,
                    'regenerated': force or (not cache_read_enabled),
                    'language': language,
                    'focus': focus,
                    'persisted': persist_generated_analysis,
                })
                return

            if event_type == 'error':
                error = event.get('error') or t('flash.ai_failed', locale=language)
                if cached_analysis:
                    yield _ndjson_line({
                        'type': 'stale',
                        'analysis': cached_analysis,
                        'cached': True,
                        'stale': True,
                        'error': error,
                        'language': language,
                        'focus': focus,
                        'persisted': True,
                    })
                else:
                    yield _ndjson_line({
                        'type': 'error',
                        'error': error,
                        'status': _ai_error_status(error),
                        'language': language,
                        'focus': focus,
                        'persisted': persist_generated_analysis,
                    })
                return

        fallback_error = lt('AI analysis stream ended without a final result.', 'AI 分析流结束但未返回最终结果。', locale=language)
        if cached_analysis:
            yield _ndjson_line({
                'type': 'stale',
                'analysis': cached_analysis,
                'cached': True,
                'stale': True,
                'error': fallback_error,
                'language': language,
                'focus': focus,
                'persisted': True,
            })
        else:
            yield _ndjson_line({
                'type': 'error',
                'error': fallback_error,
                'status': 502,
                'language': language,
                'focus': focus,
                'persisted': persist_generated_analysis,
            })

    response = Response(stream_with_context(event_stream()), mimetype='application/x-ndjson')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'
    return response


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
    initial_ai_analysis = _get_cached_analysis(analysis, get_locale()) or ''
    match_view = _serialize_match(analysis, include_scoreboard=True, locale=get_locale())
    return render_template(
        'dashboard/match_detail.html',
        analysis=analysis,
        match_view=match_view,
        initial_ai_analysis=initial_ai_analysis,
    )


@dashboard_bp.route('/settings', methods=['GET', 'POST'])
@login_required
def settings():
    riot_account = RiotAccount.query.filter_by(user_id=current_user.id).first()
    discord_config = DiscordConfig.query.filter_by(user_id=current_user.id).first()
    user_settings = current_user.settings

    riot_form = RiotAccountForm(prefix='riot')
    discord_form = DiscordConfigForm(prefix='discord')
    prefs_form = PreferencesForm(prefix='prefs')
    prefs_form.weekly_summary_day.choices = [
        (day, weekday_label(day))
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    ]

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
                flash(
                    lt('Riot account linked! Imported {count} recent matches.', 'Riot 账号已绑定！已导入最近 {count} 场对局。').format(count=count),
                    'success',
                )
            else:
                flash(lt('Riot account linked successfully!', 'Riot 账号绑定成功！'), 'success')
        except Exception as e:
            logger.error("Failed to sync matches after linking for user %d: %s", current_user.id, e)
            flash(
                lt(
                    'Riot account linked, but match import failed. Matches will sync on dashboard.',
                    'Riot 账号已绑定，但导入对局失败。后续会在仪表盘自动同步。',
                ),
                'warning',
            )
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(t(error), 'error')

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
        flash(lt('Discord configuration saved!', 'Discord 配置已保存！'), 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(t(error), 'error')

    return redirect(url_for('dashboard.settings'))


@dashboard_bp.route('/settings/preferences', methods=['POST'])
@login_required
def settings_preferences():
    form = PreferencesForm(prefix='prefs')
    form.weekly_summary_day.choices = [
        (day, weekday_label(day))
        for day in ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']
    ]
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
        flash(lt('Preferences saved!', '偏好设置已保存！'), 'success')
    else:
        for field, errors in form.errors.items():
            for error in errors:
                flash(t(error), 'error')

    return redirect(url_for('dashboard.settings'))


@dashboard_bp.route('/settings/locale', methods=['POST'])
@login_required
def settings_locale():
    """Persist user's preferred locale for worker-side language generation."""
    payload = request.get_json(silent=True) or {}
    locale_raw = payload.get('locale')
    if locale_raw not in ('en', 'zh-CN'):
        return jsonify({
            'error': lt('Unsupported locale.', '不支持的语言。'),
            'supported': ['en', 'zh-CN'],
        }), 400

    preferred_locale = normalize_locale(locale_raw)
    settings = current_user.settings
    if not settings:
        settings = UserSettings(user_id=current_user.id)
        db.session.add(settings)

    settings.preferred_locale = preferred_locale
    db.session.commit()
    return jsonify({'ok': True, 'locale': preferred_locale})
