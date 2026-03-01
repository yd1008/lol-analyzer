"""Shared test fixtures."""

import pytest
from app import create_app
from app.extensions import db as _db
from app.models import User, UserSettings


@pytest.fixture(scope="session")
def app():
    """Create a Flask application configured for testing."""
    app = create_app("default")
    app.config.update(
        TESTING=True,
        SQLALCHEMY_DATABASE_URI="sqlite:///:memory:",
        WTF_CSRF_ENABLED=False,
        SECRET_KEY="test-secret",
        RIOT_API_KEY="RGAPI-test-key",
        DISCORD_BOT_TOKEN="test-bot-token",
        DISCORD_CLIENT_ID="123456789",
        RIOT_VERIFICATION_UUID="test-uuid-1234",
        ADMIN_EMAIL="admin@test.com",
        LOGIN_RATE_LIMIT="1000 per minute",
        MAX_CONTENT_LENGTH=1024 * 1024,
        ADMIN_ANALYSIS_JSON_MAX_BYTES=64 * 1024,
        LLM_API_KEY="test-llm-key",
        LLM_API_URL="https://api.example.com/v1/chat/completions",
        LLM_MODEL="test-model",
        LLM_KNOWLEDGE_EXTERNAL=False,
        WORKER_MAX_WORKERS=2,
        RATE_LIMIT_REDIS_URL="",
        RIOT_RATE_LIMIT_PER_MINUTE=100,
        DISCORD_RATE_LIMIT_COUNT=10,
        DISCORD_RATE_LIMIT_WINDOW_SECONDS=10,
        CACHE_TYPE="SimpleCache",
    )
    with app.app_context():
        _db.create_all()
    yield app
    with app.app_context():
        _db.drop_all()


@pytest.fixture()
def db(app):
    """Provide a clean database for each test."""
    with app.app_context():
        _db.create_all()
        yield _db
        _db.session.rollback()
        for table in reversed(_db.metadata.sorted_tables):
            _db.session.execute(table.delete())
        _db.session.commit()


@pytest.fixture(autouse=True)
def session_isolation(app):
    """Reduce cross-test SQLAlchemy identity/session leakage."""
    with app.app_context():
        _db.session.expunge_all()
    yield
    with app.app_context():
        _db.session.rollback()
        _db.session.expunge_all()


@pytest.fixture()
def client(app, db):
    """A Flask test client."""
    c = app.test_client()
    c.set_cookie('lanescope-lang', 'en', domain='localhost')
    return c


@pytest.fixture()
def user(db):
    """Create a test user."""
    u = User(email="test@example.com")
    u.set_password("testpass123")
    db.session.add(u)
    db.session.flush()
    settings = UserSettings(user_id=u.id)
    db.session.add(settings)
    db.session.commit()
    return u


@pytest.fixture()
def auth_client(client, user):
    """A test client logged in as the test user."""
    client.post("/auth/login", data={
        "email": "test@example.com",
        "password": "testpass123",
    })
    return client


_ALLY_DATA = [
    {"puuid": "ally-1", "championName": "Garen", "teamPosition": "TOP", "kills": 5, "deaths": 4, "assists": 7, "goldEarned": 11000, "totalDamageDealt": 70000, "totalDamageDealtToChampions": 18000, "visionScore": 12, "totalMinionsKilled": 160, "neutralMinionsKilled": 10, "win": True, "teamId": 100, "riotIdGameName": "Ally1", "riotIdTagline": "NA1"},
    {"puuid": "ally-2", "championName": "LeeSin", "teamPosition": "JUNGLE", "kills": 6, "deaths": 3, "assists": 10, "goldEarned": 10500, "totalDamageDealt": 55000, "totalDamageDealtToChampions": 14000, "visionScore": 20, "totalMinionsKilled": 40, "neutralMinionsKilled": 120, "win": True, "teamId": 100, "riotIdGameName": "Ally2", "riotIdTagline": "NA1"},
    {"puuid": "ally-3", "championName": "Jinx", "teamPosition": "BOTTOM", "kills": 10, "deaths": 2, "assists": 8, "goldEarned": 14000, "totalDamageDealt": 100000, "totalDamageDealtToChampions": 28000, "visionScore": 15, "totalMinionsKilled": 200, "neutralMinionsKilled": 0, "win": True, "teamId": 100, "riotIdGameName": "Ally3", "riotIdTagline": "NA1"},
    {"puuid": "ally-4", "championName": "Thresh", "teamPosition": "UTILITY", "kills": 1, "deaths": 5, "assists": 18, "goldEarned": 7500, "totalDamageDealt": 20000, "totalDamageDealtToChampions": 6000, "visionScore": 45, "totalMinionsKilled": 25, "neutralMinionsKilled": 0, "win": True, "teamId": 100, "riotIdGameName": "Ally4", "riotIdTagline": "NA1"},
]

_ENEMY_DATA = [
    {"puuid": "enemy-0", "championName": "Darius", "teamPosition": "TOP", "kills": 4, "deaths": 6, "assists": 3, "goldEarned": 9500, "totalDamageDealt": 65000, "totalDamageDealtToChampions": 16000, "visionScore": 8, "totalMinionsKilled": 150, "neutralMinionsKilled": 5, "win": False, "teamId": 200, "riotIdGameName": "Enemy0", "riotIdTagline": "EUW"},
    {"puuid": "enemy-1", "championName": "Elise", "teamPosition": "JUNGLE", "kills": 3, "deaths": 7, "assists": 5, "goldEarned": 8500, "totalDamageDealt": 50000, "totalDamageDealtToChampions": 12000, "visionScore": 14, "totalMinionsKilled": 30, "neutralMinionsKilled": 100, "win": False, "teamId": 200, "riotIdGameName": "Enemy1", "riotIdTagline": "EUW"},
    {"puuid": "enemy-2", "championName": "Syndra", "teamPosition": "MIDDLE", "kills": 5, "deaths": 5, "assists": 4, "goldEarned": 10000, "totalDamageDealt": 75000, "totalDamageDealtToChampions": 20000, "visionScore": 10, "totalMinionsKilled": 170, "neutralMinionsKilled": 0, "win": False, "teamId": 200, "riotIdGameName": "Enemy2", "riotIdTagline": "EUW"},
    {"puuid": "enemy-3", "championName": "Ezreal", "teamPosition": "BOTTOM", "kills": 6, "deaths": 4, "assists": 3, "goldEarned": 11000, "totalDamageDealt": 80000, "totalDamageDealtToChampions": 22000, "visionScore": 9, "totalMinionsKilled": 190, "neutralMinionsKilled": 0, "win": False, "teamId": 200, "riotIdGameName": "Enemy3", "riotIdTagline": "EUW"},
    {"puuid": "enemy-4", "championName": "Lulu", "teamPosition": "UTILITY", "kills": 1, "deaths": 6, "assists": 8, "goldEarned": 7000, "totalDamageDealt": 18000, "totalDamageDealtToChampions": 5000, "visionScore": 35, "totalMinionsKilled": 20, "neutralMinionsKilled": 0, "win": False, "teamId": 200, "riotIdGameName": "Enemy4", "riotIdTagline": "EUW"},
]

SAMPLE_MATCH_DETAIL = {
    "info": {
        "gameDuration": 1800,
        "queueId": 420,
        "gameStartTimestamp": 1700000000000,
        "participants": [
            {
                "puuid": "test-puuid-123",
                "championName": "Ahri",
                "teamPosition": "MIDDLE",
                "kills": 8,
                "deaths": 3,
                "assists": 12,
                "goldEarned": 12500,
                "totalDamageDealt": 95000,
                "totalDamageDealtToChampions": 24000,
                "visionScore": 25,
                "totalMinionsKilled": 180,
                "neutralMinionsKilled": 20,
                "win": True,
                "teamId": 100,
                "riotIdGameName": "TestPlayer",
                "riotIdTagline": "NA1",
            },
            *_ALLY_DATA,
            *_ENEMY_DATA,
        ],
    }
}

SAMPLE_ANALYSIS = {
    "match_id": "NA1_1234567890",
    "champion": "Ahri",
    "win": True,
    "kills": 8,
    "deaths": 3,
    "assists": 12,
    "kda": 6.67,
    "gold_earned": 12500,
    "gold_per_min": 416.67,
    "total_damage": 24000,
    "damage_per_min": 800.0,
    "vision_score": 25,
    "cs_total": 200,
    "game_duration": 30.0,
    "player_position": "MIDDLE",
    "recommendations": ["Great KDA! Consider taking more calculated risks to snowball games."],
}
