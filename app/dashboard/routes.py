from flask import render_template, redirect, url_for, flash, request
from flask_login import login_required, current_user
from app.dashboard import dashboard_bp
from app.dashboard.forms import RiotAccountForm, DiscordConfigForm, PreferencesForm
from app.models import RiotAccount, DiscordConfig, MatchAnalysis, UserSettings
from app.analysis.riot_api import resolve_puuid
from app.analysis.discord_notifier import get_bot_invite_url
from app.extensions import db


@dashboard_bp.route('/')
@login_required
def index():
    analyses = MatchAnalysis.query.filter_by(user_id=current_user.id)\
        .order_by(MatchAnalysis.analyzed_at.desc()).limit(10).all()

    total_games = MatchAnalysis.query.filter_by(user_id=current_user.id).count()
    wins = MatchAnalysis.query.filter_by(user_id=current_user.id, win=True).count()
    win_rate = round((wins / total_games) * 100, 1) if total_games > 0 else 0

    all_matches = MatchAnalysis.query.filter_by(user_id=current_user.id).all()
    avg_kda = round(sum(m.kda for m in all_matches) / len(all_matches), 2) if all_matches else 0

    riot_account = RiotAccount.query.filter_by(user_id=current_user.id).first()
    discord_config = DiscordConfig.query.filter_by(user_id=current_user.id).first()

    return render_template('dashboard/index.html',
        analyses=analyses,
        total_games=total_games,
        wins=wins,
        win_rate=win_rate,
        avg_kda=avg_kda,
        riot_account=riot_account,
        discord_config=discord_config,
    )


@dashboard_bp.route('/matches')
@login_required
def matches():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    pagination = MatchAnalysis.query.filter_by(user_id=current_user.id)\
        .order_by(MatchAnalysis.analyzed_at.desc())\
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
        flash('Riot account linked successfully!', 'success')
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
