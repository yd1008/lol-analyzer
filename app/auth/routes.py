from flask import current_app, flash, redirect, render_template, request, url_for
from flask_login import login_user, logout_user, current_user
from app.auth import auth_bp
from app.auth.forms import LoginForm, RegisterForm
from app.models import User, UserSettings
from app.extensions import db, limiter
from app.i18n import t


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit(lambda: current_app.config.get('LOGIN_RATE_LIMIT', '5 per minute'), methods=['POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(email=form.email.data.lower()).first()
        if user and user.check_password(form.password.data):
            login_user(user, remember=bool(form.remember.data))
            next_page = request.args.get('next')
            flash(t('flash.welcome_back'), 'success')
            return redirect(next_page or url_for('dashboard.index'))
        flash(t('flash.invalid_credentials'), 'error')

    return render_template('auth/login.html', form=form)


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    form = RegisterForm()
    if form.validate_on_submit():
        user = User(email=form.email.data.lower())
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.flush()

        settings = UserSettings(user_id=user.id)
        db.session.add(settings)
        db.session.commit()

        login_user(user)
        flash(t('flash.account_created'), 'success')
        return redirect(url_for('dashboard.settings'))

    return render_template('auth/register.html', form=form)


@auth_bp.route('/logout')
def logout():
    logout_user()
    flash(t('flash.logged_out'), 'info')
    return redirect(url_for('main.landing'))
