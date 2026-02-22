"""Background jobs for checking matches and sending summaries."""

import logging
import time
from datetime import datetime, date, timedelta, timezone

logger = logging.getLogger(__name__)


def check_all_users_matches(app):
    """Check for new matches for all active users with linked Riot accounts."""
    with app.app_context():
        from app.extensions import db
        from app.models import User, RiotAccount, DiscordConfig, MatchAnalysis, UserSettings
        from app.analysis.riot_api import get_watcher, get_routing_value
        from app.analysis.engine import analyze_match, format_analysis_report
        from app.analysis.llm import get_llm_analysis
        from app.analysis.discord_notifier import send_message

        users = User.query.filter_by(is_active_user=True).all()

        for user in users:
            try:
                riot_account = RiotAccount.query.filter_by(
                    user_id=user.id, is_verified=True
                ).first()
                if not riot_account:
                    continue

                watcher = get_watcher()
                routing = get_routing_value(riot_account.region)

                # Get latest match
                try:
                    match_list = watcher.match.matchlist_by_puuid(
                        routing, riot_account.puuid, count=5
                    )
                except Exception as e:
                    logger.error("Error fetching matches for user %d: %s", user.id, e)
                    continue

                if not match_list:
                    continue

                for match_id in match_list:
                    # Skip already analyzed matches
                    existing = MatchAnalysis.query.filter_by(
                        user_id=user.id, match_id=match_id
                    ).first()
                    if existing:
                        continue

                    analysis = analyze_match(watcher, routing, riot_account.puuid, match_id)
                    if not analysis:
                        continue
                    analysis['platform_region'] = riot_account.region

                    # Run LLM analysis
                    llm_text = None
                    try:
                        llm_text = get_llm_analysis(analysis)
                    except Exception as e:
                        logger.error("LLM analysis failed for match %s: %s", match_id, e)

                    # Save to database
                    record = MatchAnalysis(
                        user_id=user.id,
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
                        llm_analysis=llm_text,
                        llm_analysis_en=llm_text,
                        llm_analysis_zh=None,
                        queue_type=analysis.get('queue_type'),
                        participants_json=analysis.get('participants'),
                        game_start_timestamp=analysis.get('game_start_timestamp'),
                    )
                    db.session.add(record)
                    db.session.commit()

                    # Send Discord notification
                    settings = UserSettings.query.filter_by(user_id=user.id).first()
                    if settings and not settings.notifications_enabled:
                        continue

                    discord_config = DiscordConfig.query.filter_by(
                        user_id=user.id, is_active=True
                    ).first()
                    if discord_config:
                        report = format_analysis_report(analysis)
                        if llm_text:
                            report += f"\n**AI Coach**:\n{llm_text[:800]}"
                        send_message(discord_config.channel_id, report)

                    logger.info("Analyzed match %s for user %d", match_id, user.id)

            except Exception as e:
                logger.error("Error processing user %d: %s", user.id, e)
                continue


def send_weekly_summaries(app):
    """Generate and send weekly summaries for eligible users."""
    with app.app_context():
        from app.extensions import db
        from app.models import User, DiscordConfig, MatchAnalysis, WeeklySummary, UserSettings
        from app.analysis.engine import generate_weekly_summary
        from app.analysis.discord_notifier import send_message

        now = datetime.now(timezone.utc)
        today = now.strftime('%A')

        users = User.query.filter_by(is_active_user=True).all()

        for user in users:
            try:
                settings = UserSettings.query.filter_by(user_id=user.id).first()
                if not settings:
                    continue

                if settings.weekly_summary_day != today:
                    continue

                hour_str = settings.weekly_summary_time.split(':')[0]
                if now.hour != int(hour_str):
                    continue

                # Check if summary already sent this week
                week_start = (now - timedelta(days=7)).date()
                existing = WeeklySummary.query.filter_by(
                    user_id=user.id, week_start=week_start
                ).first()
                if existing:
                    continue

                # Get this week's analyses
                week_analyses = MatchAnalysis.query.filter(
                    MatchAnalysis.user_id == user.id,
                    MatchAnalysis.analyzed_at >= now - timedelta(days=7)
                ).all()

                if not week_analyses:
                    continue

                analyses_dicts = [{
                    'win': a.win,
                    'kda': a.kda,
                    'gold_per_min': a.gold_per_min,
                    'damage_per_min': a.damage_per_min,
                } for a in week_analyses]

                summary_data = generate_weekly_summary(analyses_dicts)
                if not summary_data:
                    continue

                # Save summary
                summary = WeeklySummary(
                    user_id=user.id,
                    week_start=week_start,
                    week_end=now.date(),
                    total_games=summary_data['total_games'],
                    wins=summary_data['wins'],
                    avg_kda=summary_data['avg_kda'],
                    avg_gold_per_min=summary_data['avg_gold_per_min'],
                    avg_damage_per_min=summary_data['avg_damage_per_min'],
                    summary_text=summary_data['summary_text'],
                    sent_at=now,
                )
                db.session.add(summary)
                db.session.commit()

                # Send to Discord
                if not settings.notifications_enabled:
                    continue

                discord_config = DiscordConfig.query.filter_by(
                    user_id=user.id, is_active=True
                ).first()
                if discord_config:
                    send_message(discord_config.channel_id, summary_data['summary_text'])

                logger.info("Sent weekly summary to user %d", user.id)

            except Exception as e:
                logger.error("Error sending weekly summary for user %d: %s", user.id, e)
                continue


def refresh_game_assets(app):
    """Warm Data Dragon champion/item/rune icon caches periodically."""
    with app.app_context():
        from app.analysis.champion_assets import refresh_asset_caches

        try:
            result = refresh_asset_caches()
            logger.info(
                "Refreshed game assets cache. version=%s champion_aliases=%s items=%s runes=%s styles=%s",
                result.get('version', ''),
                result.get('champion_aliases', 0),
                result.get('items', 0),
                result.get('runes', 0),
                result.get('styles', 0),
            )
        except Exception as e:
            logger.error("Error refreshing game assets cache: %s", e)
