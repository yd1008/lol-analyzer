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
        LLM_API_KEY="test-llm-key",
        LLM_API_URL="https://api.example.com/v1/chat/completions",
        LLM_MODEL="test-model",
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


@pytest.fixture()
def client(app, db):
    """A Flask test client."""
    return app.test_client()


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


SAMPLE_MATCH_DETAIL = {
    "info": {
        "gameDuration": 1800,
        "queueId": 420,
        "participants": [
            {
                "puuid": "test-puuid-123",
                "championName": "Ahri",
                "kills": 8,
                "deaths": 3,
                "assists": 12,
                "goldEarned": 12500,
                "totalDamageDealt": 95000,
                "visionScore": 25,
                "totalMinionsKilled": 180,
                "neutralMinionsKilled": 20,
                "win": True,
            },
            *[
                {
                    "puuid": f"enemy-{i}",
                    "championName": "Garen",
                    "kills": 3,
                    "deaths": 5,
                    "assists": 4,
                    "goldEarned": 9000,
                    "totalDamageDealt": 60000,
                    "visionScore": 10,
                    "totalMinionsKilled": 120,
                    "neutralMinionsKilled": 0,
                    "win": False,
                }
                for i in range(9)
            ],
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
    "total_damage": 95000,
    "damage_per_min": 3166.67,
    "vision_score": 25,
    "cs_total": 200,
    "game_duration": 30.0,
    "recommendations": ["Great KDA! Consider taking more calculated risks to snowball games."],
}
