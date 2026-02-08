from flask import render_template, current_app
from app.main import main_bp


@main_bp.route('/')
def landing():
    return render_template('main/landing.html')


@main_bp.route('/riot.txt')
def riot_txt():
    return current_app.config['RIOT_VERIFICATION_UUID'], 200, {'Content-Type': 'text/plain'}


@main_bp.route('/terms')
def terms():
    return render_template('main/terms.html')


@main_bp.route('/privacy')
def privacy():
    return render_template('main/privacy.html')
