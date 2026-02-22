import os
from flask import Flask, flash, jsonify, render_template, request
from app.config import config
from app.extensions import cache, csrf, db, limiter, login_manager, migrate
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

    # Keep limiter state shared when Redis is configured; otherwise fall back to process memory.
    rate_limit_storage = app.config.get('RATE_LIMIT_REDIS_URL', '').strip()
    app.config['RATELIMIT_STORAGE_URI'] = rate_limit_storage or 'memory://'

    db.init_app(app)
    login_manager.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    cache.init_app(app)
    limiter.init_app(app)

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

    @app.errorhandler(413)
    def request_entity_too_large(e):
        if request.path.startswith('/admin/'):
            flash(lt('Request payload is too large.', '请求内容过大。'), 'error')
            return render_template('admin/test_llm.html', analysis_data=None, match_list=None, result=None), 413
        return jsonify({'error': lt('Request payload is too large.', '请求内容过大。')}), 413

    @app.errorhandler(429)
    def too_many_requests(e):
        if request.path == '/auth/login' and request.method == 'POST':
            from app.auth.forms import LoginForm
            flash(t('flash.too_many_attempts'), 'error')
            return render_template('auth/login.html', form=LoginForm()), 429
        if request.accept_mimetypes.best == 'application/json':
            return jsonify({'error': t('flash.too_many_attempts')}), 429
        flash(t('flash.too_many_attempts'), 'error')
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    @app.context_processor
    def inject_i18n_context():
        locale = get_locale()
        return {
            'current_locale': locale,
            'js_i18n': js_i18n_payload(locale),
            'admin_email': app.config.get('ADMIN_EMAIL', ''),
        }

    return app
