import os
from dotenv import load_dotenv

load_dotenv()


def _fix_db_url(url):
    """Railway uses postgres:// but SQLAlchemy 2.x requires postgresql://."""
    if url and url.startswith('postgres://'):
        return url.replace('postgres://', 'postgresql://', 1)
    return url


def _to_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in ('1', 'true', 'yes', 'on')


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_DATABASE_URI = _fix_db_url(os.environ.get('DATABASE_URL', 'sqlite:///lol_analyzer.db'))
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_CONTENT_LENGTH', str(1024 * 1024)))

    RIOT_API_KEY = os.environ.get('RIOT_API_KEY', '')
    DISCORD_BOT_TOKEN = os.environ.get('DISCORD_BOT_TOKEN', '')
    DISCORD_CLIENT_ID = os.environ.get('DISCORD_CLIENT_ID', '')

    RIOT_VERIFICATION_UUID = os.environ.get(
        'RIOT_VERIFICATION_UUID', 'd0d11145-7370-4adc-804a-fe67f762154e'
    )

    CHECK_INTERVAL_MINUTES = int(os.environ.get('CHECK_INTERVAL_MINUTES', '5'))
    ASSET_REFRESH_HOURS = int(os.environ.get('ASSET_REFRESH_HOURS', '6'))
    WEEKLY_SUMMARY_DAY = os.environ.get('WEEKLY_SUMMARY_DAY', 'Monday')
    WEEKLY_SUMMARY_TIME = os.environ.get('WEEKLY_SUMMARY_TIME', '09:00')
    WORKER_MAX_WORKERS = int(os.environ.get('WORKER_MAX_WORKERS', '4'))

    ADMIN_EMAIL = os.environ.get('ADMIN_EMAIL', '')
    ADMIN_ANALYSIS_JSON_MAX_BYTES = int(os.environ.get('ADMIN_ANALYSIS_JSON_MAX_BYTES', str(256 * 1024)))
    LOGIN_RATE_LIMIT = os.environ.get('LOGIN_RATE_LIMIT', '5 per minute')

    LLM_API_KEY = os.environ.get('LLM_API_KEY', '')
    LLM_API_URL = os.environ.get('LLM_API_URL', '')
    LLM_MODEL = os.environ.get('LLM_MODEL', '')
    LLM_FALLBACK_MODELS = os.environ.get('LLM_FALLBACK_MODELS', '')
    LLM_TIMEOUT_SECONDS = int(os.environ.get('LLM_TIMEOUT_SECONDS', '30'))
    LLM_RETRIES = int(os.environ.get('LLM_RETRIES', '1'))
    LLM_RETRY_BACKOFF_SECONDS = float(os.environ.get('LLM_RETRY_BACKOFF_SECONDS', '1.5'))
    LLM_MAX_TOKENS = int(os.environ.get('LLM_MAX_TOKENS', '2048'))
    LLM_RESPONSE_TOKEN_TARGET = int(os.environ.get('LLM_RESPONSE_TOKEN_TARGET', '0'))
    LLM_KNOWLEDGE_EXTERNAL = _to_bool(os.environ.get('LLM_KNOWLEDGE_EXTERNAL'), True)
    LLM_KNOWLEDGE_FILE = os.environ.get('LLM_KNOWLEDGE_FILE', '')

    RATE_LIMIT_REDIS_URL = os.environ.get('RATE_LIMIT_REDIS_URL', '')
    RIOT_RATE_LIMIT_PER_MINUTE = int(os.environ.get('RIOT_RATE_LIMIT_PER_MINUTE', '100'))
    DISCORD_RATE_LIMIT_COUNT = int(os.environ.get('DISCORD_RATE_LIMIT_COUNT', '10'))
    DISCORD_RATE_LIMIT_WINDOW_SECONDS = int(os.environ.get('DISCORD_RATE_LIMIT_WINDOW_SECONDS', '10'))

    # Flask-Caching config (hybrid by default: Redis when configured, in-memory fallback).
    CACHE_REDIS_URL = os.environ.get('CACHE_REDIS_URL', '') or RATE_LIMIT_REDIS_URL
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get('CACHE_DEFAULT_TIMEOUT', str(6 * 3600)))
    CACHE_TYPE = 'RedisCache' if CACHE_REDIS_URL else 'SimpleCache'


class DevelopmentConfig(Config):
    DEBUG = True


class ProductionConfig(Config):
    DEBUG = False


config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig,
}
