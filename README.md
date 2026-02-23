# LoL Performance Analyzer

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Flask](https://img.shields.io/badge/Flask-3.1-green.svg)](https://flask.palletsprojects.com/)

A multi-user web platform for League of Legends performance analysis. Automatically analyzes your ranked games, provides personalized improvement recommendations, and delivers match reports to your Discord channel.

## Features

- **Web Dashboard** - Full match history, performance stats, and analysis accessible from your browser
- **Automated Game Analysis** - Background worker detects and analyzes new matches automatically
- **Smart Recommendations** - Personalized tips based on KDA, vision, gold efficiency, and damage contribution
- **Discord Notifications** - Match reports delivered to your Discord channel via bot REST API
- **Weekly Summaries** - Scheduled performance digests with improvement focus areas
- **Multi-User** - Each user links their own Riot account and Discord channel

## Quick Start

### Prerequisites

- **Python 3.10+** - [Download here](https://www.python.org/downloads/)
- **Riot Games API Key** - [Get one here](https://developer.riotgames.com/)
- **Discord Bot Token** - [Create one here](https://discord.com/developers/applications)

### Installation

1. **Clone the repository**
   ```bash
   git clone https://github.com/yd1008/lol-analyzer.git
   cd lol-analyzer
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your API keys and settings
   ```

4. **Initialize the database**
   ```bash
   flask db init
   flask db migrate -m "Initial migration"
   flask db upgrade
   ```

5. **Run the web server (development)**
   ```bash
   python run.py
   ```
   Visit http://localhost:5000

6. **Run the background worker** (separate terminal)
   ```bash
   python worker_run.py
   ```

### Local Quality Checks

Run the project test suite before opening or updating PRs:
```bash
python -m pytest tests/
```
Expect a green result similar to `137 passed` (warnings are okay when listed).

### Production Deployment

```bash
# Uses Gunicorn as the WSGI server
gunicorn wsgi:app --bind 0.0.0.0:${PORT:-5000} --timeout 120
```

## Architecture

```
lol-analyzer/
├── app/                    # Flask application
│   ├── __init__.py         # App factory
│   ├── config.py           # Configuration classes
│   ├── extensions.py       # Flask extensions (db, login, migrate, csrf)
│   ├── models.py           # SQLAlchemy models
│   ├── auth/               # Authentication blueprint (login, register)
│   ├── dashboard/          # Dashboard blueprint (matches, settings)
│   ├── main/               # Public pages blueprint (landing, legal)
│   ├── analysis/           # Analysis engine, Riot API, Discord notifier
│   ├── templates/          # Jinja2 templates
│   └── static/             # CSS, JS, riot.txt
├── worker/                 # Background job scheduler
│   ├── scheduler.py        # APScheduler config
│   └── jobs.py             # Match checking and weekly summary jobs
├── run.py                  # Development entry point
├── wsgi.py                 # Production entry point
└── worker_run.py           # Background worker entry point
```

### Key Design Decisions

- **Discord REST API** instead of Gateway WebSocket - simpler multi-user message delivery without maintaining a persistent connection
- **APScheduler** for background jobs - lightweight, no message broker required
- **SQLAlchemy + SQLite/PostgreSQL** - SQLite for development, PostgreSQL for production
- **Stateless analysis functions** - `analyze_match()`, `generate_recommendations()` extracted as pure functions parameterized by user

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Flask session secret | `dev-secret-key-change-in-production` |
| `DATABASE_URL` | Database connection string | `sqlite:///lol_analyzer.db` |
| `RIOT_API_KEY` | Riot Games API key | (required) |
| `DISCORD_BOT_TOKEN` | Discord bot token | (required) |
| `DISCORD_CLIENT_ID` | Discord application client ID | (optional, for invite URL) |
| `RIOT_VERIFICATION_UUID` | Riot API verification UUID | (set in .env) |
| `LLM_API_KEY` | LLM provider API key | (required for AI analysis) |
| `LLM_API_URL` | OpenAI-compatible chat completions endpoint | (required for AI analysis) |
| `LLM_MODEL` | Model name sent to provider | `deepseek-chat` |
| `LLM_TIMEOUT_SECONDS` | Timeout per LLM request attempt | `30` |
| `LLM_RETRIES` | Retries for timeout/5xx failures | `1` |
| `LLM_RETRY_BACKOFF_SECONDS` | Base exponential retry backoff | `1.5` |
| `LLM_MAX_TOKENS` | Max completion tokens for AI analysis | `2048` |
| `LLM_RESPONSE_TOKEN_TARGET` | Optional soft response token target for prompt guidance (`0` disables) | `0` |
| `CHECK_INTERVAL_MINUTES` | How often to check for new matches | `5` |
| `WEEKLY_SUMMARY_DAY` | Day of week for summary | `Monday` |
| `WEEKLY_SUMMARY_TIME` | Time for summary (HH:MM) | `09:00` |
| `WORKER_MAX_WORKERS` | Max worker threads for match sync job | `4` |
| `LOGIN_RATE_LIMIT` | Auth login POST rate limit | `5 per minute` |
| `MAX_CONTENT_LENGTH` | Max HTTP request payload bytes | `1048576` |
| `ADMIN_ANALYSIS_JSON_MAX_BYTES` | Max bytes for admin test LLM JSON payload | `262144` |
| `RATE_LIMIT_REDIS_URL` | Optional Redis URL for shared rate-limit state | (optional) |
| `RIOT_RATE_LIMIT_PER_MINUTE` | Client-side Riot API throttle budget | `100` |
| `DISCORD_RATE_LIMIT_COUNT` | Client-side Discord message burst count | `10` |
| `DISCORD_RATE_LIMIT_WINDOW_SECONDS` | Discord burst window seconds | `10` |

## Metrics Tracked

| Metric | Description |
|--------|-------------|
| **KDA** | Kill/Death/Assist ratio with detailed breakdown |
| **Gold Efficiency** | Total gold and gold per minute |
| **Damage Output** | Total damage and damage per minute |
| **Vision Score** | Overall vision control and ward placement |
| **CS** | Total creep score |
| **Team Contribution** | Gold share and damage share analysis |

## User Flow

1. Register an account at the web dashboard
2. Link your Riot Games summoner name (name + tagline + region)
3. Add the Discord bot to your server and configure a channel ID
4. Play games - the background worker automatically detects and analyzes matches
5. View analysis in Discord and on the web dashboard

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Riot Games, Inc. League of Legends is a trademark of Riot Games, Inc.

## Contact

- **GitHub Issues** - For bug reports and feature requests
- **Developer** - Elliot Dang (yd1008@nyu.edu)
- **Repository** - https://github.com/yd1008/lol-analyzer
