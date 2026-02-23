"""
Analysis engine for match-level stat extraction and recommendation generation.
All functions are stateless and parameterized for multi-user use.
"""

import logging
from riotwatcher import LolWatcher, ApiError
from app.analysis.rate_limit import throttle_riot_api

logger = logging.getLogger(__name__)


QUEUE_TYPES = {
    400: "Normal Draft",
    420: "Ranked Solo",
    430: "Normal Blind",
    440: "Ranked Flex",
    450: "ARAM",
    700: "Clash",
    900: "ARURF",
    1020: "One for All",
    1300: "Nexus Blitz",
    1400: "Ultimate Spellbook",
}


def get_match_summary(watcher: LolWatcher, region: str, puuid: str, match_id: str) -> dict | None:
    """Fetch match detail and return lightweight summary for list view."""
    try:
        throttle_riot_api('match_by_id_summary')
        match_detail = watcher.match.by_id(region, match_id)

        player_data = None
        for participant in match_detail['info']['participants']:
            if participant['puuid'] == puuid:
                player_data = participant
                break

        if player_data is None:
            logger.error("Player not found in match %s", match_id)
            return None

        game_duration = match_detail['info']['gameDuration']
        queue_id = match_detail['info'].get('queueId', 0)

        return {
            'match_id': match_id,
            'champion': player_data['championName'],
            'win': player_data['win'],
            'kills': player_data['kills'],
            'deaths': player_data['deaths'],
            'assists': player_data['assists'],
            'game_duration': round(game_duration / 60, 1),
            'queue_type': QUEUE_TYPES.get(queue_id, "Other"),
        }
    except ApiError as e:
        logger.error("Riot API error fetching summary for match %s: %s", match_id, e)
        return None
    except Exception as e:
        logger.error("Error fetching summary for match %s: %s", match_id, e)
        return None


def derive_lane_context(participants: list[dict]) -> tuple[str, dict | None]:
    """Return (player_position, lane_opponent_dict_or_None).

    Finds the player's position and the enemy participant with the same
    position.  Returns ('', None) when position data is missing.
    """
    player = None
    for p in participants:
        if p.get('is_player'):
            player = p
            break

    if player is None or not player.get('position'):
        return '', None

    player_position = player['position']
    player_team = player.get('team_id')

    for p in participants:
        if p.get('team_id') != player_team and p.get('position') == player_position:
            return player_position, p

    return player_position, None


def analyze_match(watcher: LolWatcher, region: str, puuid: str, match_id: str) -> dict | None:
    """Analyze a single match and return insights."""
    try:
        throttle_riot_api('match_by_id_analyze')
        match_detail = watcher.match.by_id(region, match_id)

        player_index = None
        for i, participant in enumerate(match_detail['info']['participants']):
            if participant['puuid'] == puuid:
                player_index = i
                break

        if player_index is None:
            logger.error("Player not found in match %s", match_id)
            return None

        player_data = match_detail['info']['participants'][player_index]
        player_item_ids = [player_data.get(f'item{i}', 0) for i in range(7) if player_data.get(f'item{i}', 0)]

        kda = (player_data['kills'] + player_data['assists']) / max(1, player_data['deaths'])
        gold_earned = player_data['goldEarned']
        total_damage = player_data.get('totalDamageDealtToChampions', player_data.get('totalDamageDealt', 0))
        vision_score = player_data['visionScore']
        cs_total = player_data['totalMinionsKilled'] + player_data['neutralMinionsKilled']

        game_duration = match_detail['info']['gameDuration']
        game_duration_minutes = game_duration / 60

        gold_per_min = gold_earned / game_duration_minutes
        damage_per_min = total_damage / game_duration_minutes

        win = player_data['win']

        queue_id = match_detail['info'].get('queueId', 0)
        queue_type = QUEUE_TYPES.get(queue_id, "Other")

        participants = []
        for p in match_detail['info']['participants']:
            perks = p.get('perks', {})
            styles = perks.get('styles', []) if isinstance(perks, dict) else []
            primary_rune_id = 0
            secondary_style_id = 0
            if styles and isinstance(styles[0], dict):
                selections = styles[0].get('selections', [])
                if selections and isinstance(selections[0], dict):
                    primary_rune_id = selections[0].get('perk', 0) or 0
            if len(styles) > 1 and isinstance(styles[1], dict):
                secondary_style_id = styles[1].get('style', 0) or 0
            participants.append({
                'puuid': p.get('puuid', ''),
                'summoner_id': p.get('summonerId', ''),
                'champion': p['championName'],
                'champion_id': p.get('championId'),
                'summoner_name': p.get('riotIdGameName') or p.get('summonerName', ''),
                'tagline': p.get('riotIdTagline', ''),
                'team_id': p.get('teamId', 0),
                'kills': p['kills'],
                'deaths': p['deaths'],
                'assists': p['assists'],
                'win': p['win'],
                'is_player': p['puuid'] == puuid,
                'position': p.get('teamPosition', ''),
                'gold_earned': p.get('goldEarned', 0),
                'total_damage': p.get('totalDamageDealtToChampions', p.get('totalDamageDealt', 0)),
                'cs': p.get('totalMinionsKilled', 0) + p.get('neutralMinionsKilled', 0),
                'vision_score': p.get('visionScore', 0),
                'level': p.get('champLevel', 0),
                'item_ids': [p.get(f'item{i}', 0) for i in range(7) if p.get(f'item{i}', 0)],
                'primary_rune_id': primary_rune_id,
                'secondary_rune_style_id': secondary_style_id,
            })

        game_start_timestamp = match_detail['info'].get('gameStartTimestamp')

        player_position, lane_opponent = derive_lane_context(participants)

        analysis = {
            'match_id': match_id,
            'champion': player_data['championName'],
            'kda': round(kda, 2),
            'kills': player_data['kills'],
            'deaths': player_data['deaths'],
            'assists': player_data['assists'],
            'gold_earned': gold_earned,
            'gold_per_min': round(gold_per_min, 2),
            'total_damage': total_damage,
            'damage_per_min': round(damage_per_min, 2),
            'vision_score': vision_score,
            'cs_total': cs_total,
            'win': win,
            'game_duration': round(game_duration_minutes, 1),
            'recommendations': generate_recommendations(player_data, match_detail),
            'queue_type': queue_type,
            'queue_id': queue_id,
            'routing_region': region,
            'player_puuid': puuid,
            'player_summoner_id': player_data.get('summonerId', ''),
            'item_ids': player_item_ids,
            'participants': participants,
            'game_start_timestamp': game_start_timestamp,
            'player_position': player_position,
            'lane_opponent': lane_opponent,
        }

        return analysis
    except ApiError as e:
        logger.error("Riot API error analyzing match %s: %s", match_id, e)
        return None
    except Exception as e:
        logger.error("Error analyzing match %s: %s", match_id, e)
        return None


def generate_recommendations(player_data: dict, match_detail: dict) -> list[str]:
    """Generate personalized recommendations based on performance."""
    recs = []

    kda = (player_data['kills'] + player_data['assists']) / max(1, player_data['deaths'])
    if kda < 2.0:
        recs.append("Focus on survival - your death rate is high. Consider backing off in dangerous situations.")
    elif kda > 5.0:
        recs.append("Great KDA! Consider taking more calculated risks to snowball games.")

    if player_data['visionScore'] < 15:
        recs.append("Vision score is low. Buy control wards and place them strategically.")

    team_gold = sum(p['goldEarned'] for p in match_detail['info']['participants'][:5])
    if team_gold > 0:
        gold_share = player_data['goldEarned'] / team_gold
        if gold_share > 0.25:
            recs.append("You're getting a high gold share - make sure to capitalize on your lead.")
        elif gold_share < 0.15:
            recs.append("Consider focusing more on farming or looking for opportunities to help your team.")

    team_damage = sum(p.get('totalDamageDealtToChampions', p.get('totalDamageDealt', 0)) for p in match_detail['info']['participants'][:5])
    if team_damage > 0:
        damage_share = player_data.get('totalDamageDealtToChampions', player_data.get('totalDamageDealt', 0)) / team_damage
        if damage_share > 0.25:
            recs.append("High damage output - great job carrying!")
        elif damage_share < 0.15:
            recs.append("Look for ways to increase your damage contribution.")

    if not recs:
        recs.append("Overall solid performance. Keep practicing!")

    return recs


def format_analysis_report(analysis: dict) -> str:
    """Format analysis into a Discord-friendly message."""
    result = "WIN" if analysis['win'] else "LOSS"

    report = (
        f"**Match Analysis Report**\n"
        f"**Champion**: {analysis['champion']}\n"
        f"**Result**: {result}\n"
        f"**KDA**: {analysis['kills']}/{analysis['deaths']}/{analysis['assists']} ({analysis['kda']})\n"
        f"**Gold**: {analysis['gold_earned']} ({analysis['gold_per_min']}/min)\n"
        f"**Damage**: {analysis['total_damage']} ({analysis['damage_per_min']}/min)\n"
        f"**Vision Score**: {analysis['vision_score']}\n"
        f"**CS**: {analysis['cs_total']}\n"
        f"**Duration**: {analysis['game_duration']} min\n\n"
        f"**Recommendations**:\n"
    )
    for rec in analysis['recommendations']:
        report += f"- {rec}\n"

    return report


def generate_weekly_summary(analyses: list[dict]) -> dict:
    """Generate a weekly summary from a list of match analyses."""
    if not analyses:
        return None

    total_games = len(analyses)
    wins = sum(1 for a in analyses if a['win'])
    total_kda = sum(a['kda'] for a in analyses)
    total_gold = sum(a['gold_per_min'] for a in analyses)
    total_damage = sum(a['damage_per_min'] for a in analyses)

    avg_kda = round(total_kda / total_games, 2)
    avg_gold = round(total_gold / total_games, 2)
    avg_damage = round(total_damage / total_games, 2)
    win_rate = round((wins / total_games) * 100, 1)

    focus_areas = []
    if win_rate < 50:
        focus_areas.append("Focus on consistency and decision-making")
    if avg_kda < 3.0:
        focus_areas.append("Work on survival and engagement timing")
    if avg_gold < 300:
        focus_areas.append("Improve farming efficiency and objective taking")

    summary_text = (
        f"**Weekly Summary (Last 7 Days)**\n"
        f"**Total Games**: {total_games}\n"
        f"**Win Rate**: {win_rate}% ({wins}W/{total_games - wins}L)\n"
        f"**Avg KDA**: {avg_kda}\n"
        f"**Avg Gold/min**: {avg_gold}\n"
        f"**Avg Damage/min**: {avg_damage}\n"
    )

    if focus_areas:
        summary_text += "\n**Improvement Focus**:\n"
        for area in focus_areas:
            summary_text += f"- {area}\n"

    return {
        'total_games': total_games,
        'wins': wins,
        'avg_kda': avg_kda,
        'avg_gold_per_min': avg_gold,
        'avg_damage_per_min': avg_damage,
        'summary_text': summary_text,
    }
