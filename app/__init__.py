import os
from flask import Flask, render_template
from app.config import config
from app.extensions import db, login_manager, migrate, csrf
from app.analysis.champion_assets import champion_icon_url
from app.i18n import (
    champion_name,
    get_locale,
    item_name,
    js_i18n_payload,
    lane_label,
    localize_login_message,
    localize_recommendation,
    lt,
    queue_label,
    rank_tier_label,
    result_label,
    t,
    weekday_label,
)


def create_app(config_name=None):
    if config_name is None:
        config_name = os.environ.get('FLASK_CONFIG', 'default')

    app = Flask(__name__)
    app.config.from_object(config[config_name])

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)

    from app.main import main_bp
    app.register_blueprint(main_bp)

    from app.auth import auth_bp
    app.register_blueprint(auth_bp, url_prefix='/auth')

    from app.dashboard import dashboard_bp
    app.register_blueprint(dashboard_bp, url_prefix='/dashboard')

    from app.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    from app.models import User, RiotAccount, DiscordConfig, MatchAnalysis, WeeklySummary, UserSettings  # noqa: F401

    app.jinja_env.globals['champion_icon_url'] = champion_icon_url
    app.jinja_env.globals['t'] = t
    app.jinja_env.globals['lt'] = lt
    app.jinja_env.globals['queue_label'] = queue_label
    app.jinja_env.globals['lane_label'] = lane_label
    app.jinja_env.globals['rank_tier_label'] = rank_tier_label
    app.jinja_env.globals['result_label'] = result_label
    app.jinja_env.globals['recommendation_text'] = localize_recommendation
    app.jinja_env.globals['weekday_label'] = weekday_label
    app.jinja_env.globals['champion_name_i18n'] = champion_name
    app.jinja_env.globals['item_name_i18n'] = item_name

    login_manager.localize_callback = localize_login_message

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    @app.context_processor
    def inject_i18n_context():
        locale = get_locale()
        return {
            'current_locale': locale,
            'js_i18n': js_i18n_payload(locale),
        }

    return app
