from datetime import datetime, timezone
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app.extensions import db, login_manager


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(16), nullable=False, default='user', server_default='user')
    created_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    is_active_user = db.Column(db.Boolean, default=True)

    riot_accounts = db.relationship('RiotAccount', backref='user', lazy=True, cascade='all, delete-orphan')
    discord_configs = db.relationship('DiscordConfig', backref='user', lazy=True, cascade='all, delete-orphan')
    match_analyses = db.relationship('MatchAnalysis', backref='user', lazy=True, cascade='all, delete-orphan')
    weekly_summaries = db.relationship('WeeklySummary', backref='user', lazy=True, cascade='all, delete-orphan')
    settings = db.relationship('UserSettings', backref='user', uselist=False, cascade='all, delete-orphan')
    admin_audit_logs = db.relationship('AdminAuditLog', backref='actor', lazy=True, cascade='all, delete-orphan')

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    @property
    def is_admin(self) -> bool:
        return (self.role or '').strip().lower() == 'admin'


@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))


class RiotAccount(db.Model):
    __tablename__ = 'riot_accounts'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    summoner_name = db.Column(db.String(64), nullable=False)
    tagline = db.Column(db.String(16), nullable=False)
    region = db.Column(db.String(16), nullable=False)
    puuid = db.Column(db.String(128), unique=True)
    is_verified = db.Column(db.Boolean, default=False)


class DiscordConfig(db.Model):
    __tablename__ = 'discord_configs'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    guild_id = db.Column(db.String(64))
    channel_id = db.Column(db.String(64), nullable=False)
    is_active = db.Column(db.Boolean, default=True)


class MatchAnalysis(db.Model):
    __tablename__ = 'match_analyses'
    __table_args__ = (
        db.UniqueConstraint('user_id', 'match_id', name='uq_match_analyses_user_match'),
    )

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    match_id = db.Column(db.String(64), nullable=False, index=True)
    champion = db.Column(db.String(32))
    win = db.Column(db.Boolean)
    kills = db.Column(db.Integer)
    deaths = db.Column(db.Integer)
    assists = db.Column(db.Integer)
    kda = db.Column(db.Float)
    gold_earned = db.Column(db.Integer)
    gold_per_min = db.Column(db.Float)
    total_damage = db.Column(db.Integer)
    damage_per_min = db.Column(db.Float)
    vision_score = db.Column(db.Integer)
    cs_total = db.Column(db.Integer)
    game_duration = db.Column(db.Float)
    recommendations = db.Column(db.JSON)
    llm_analysis = db.Column(db.Text)
    llm_analysis_en = db.Column(db.Text, nullable=True)
    llm_analysis_zh = db.Column(db.Text, nullable=True)
    queue_type = db.Column(db.String(32), nullable=True)
    participants_json = db.Column(db.JSON, nullable=True)
    game_start_timestamp = db.Column(db.BigInteger, nullable=True)
    analyzed_at = db.Column(db.DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))


class WeeklySummary(db.Model):
    __tablename__ = 'weekly_summaries'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    week_start = db.Column(db.Date, nullable=False)
    week_end = db.Column(db.Date, nullable=False)
    total_games = db.Column(db.Integer, default=0)
    wins = db.Column(db.Integer, default=0)
    avg_kda = db.Column(db.Float)
    avg_gold_per_min = db.Column(db.Float)
    avg_damage_per_min = db.Column(db.Float)
    summary_text = db.Column(db.Text)
    sent_at = db.Column(db.DateTime)


class UserSettings(db.Model):
    __tablename__ = 'user_settings'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, unique=True)
    check_interval = db.Column(db.Integer, default=5)
    weekly_summary_day = db.Column(db.String(16), default='Monday')
    weekly_summary_time = db.Column(db.String(8), default='09:00')
    notifications_enabled = db.Column(db.Boolean, default=True)
    preferred_locale = db.Column(db.String(8), nullable=False, default='zh-CN', server_default='zh-CN')


class AdminAuditLog(db.Model):
    __tablename__ = 'admin_audit_logs'

    id = db.Column(db.Integer, primary_key=True)
    actor_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True, index=True)
    action = db.Column(db.String(64), nullable=False)
    route = db.Column(db.String(256), nullable=False)
    method = db.Column(db.String(16), nullable=False)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(512), nullable=True)
    metadata_json = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
