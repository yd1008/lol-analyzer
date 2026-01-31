# 🎮 LoL Performance Analyzer

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/yd1008/lol-analyzer)](https://github.com/yd1008/lol-analyzer/stargazers)
[![Discord](https://img.shields.io/badge/Discord-Integration-purple.svg)](https://discord.com/)

A professional, Discord-integrated League of Legends performance analysis tool that automatically analyzes your ranked games and provides detailed improvement recommendations.

## ✨ Features

- 📊 **Automated Game Analysis** - Instant analysis after each ranked match
- 💡 **Smart Recommendations** - Personalized tips based on your gameplay
- 🔔 **Discord Integration** - Detailed reports delivered to your server
- 📈 **Weekly Summaries** - Comprehensive performance tracking over time
- 🎯 **Comprehensive Metrics** - KDA, gold, damage, vision, CS, and more
- ⚡ **Real-Time Updates** - Automatic game detection and analysis

## 🚀 Quick Start

### Prerequisites

- **Python 3.8+** - [Download here](https://www.python.org/downloads/)
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

3. **Configure the analyzer**
   ```bash
   python setup.py
   ```
   
   Or manually edit `lol_analyzer_config.json`:
   ```json
   {
     "riot_api_key": "YOUR_RIOT_API_KEY",
     "discord_bot_token": "YOUR_DISCORD_BOT_TOKEN",
     "discord_channel_id": "YOUR_CHANNEL_ID",
     "summoner_name": "YourSummonerName",
     "region": "na1"
   }
   ```

4. **Run the analyzer**
   ```bash
   python lol_analyzer.py
   ```

## 📊 Metrics Tracked

| Metric | Description |
|--------|-------------|
| **KDA** | Kill/Death/Assist ratio with detailed breakdown |
| **Gold Efficiency** | Total gold and gold per minute |
| **Damage Output** | Total damage and damage per minute |
| **Vision Score** | Overall vision control and ward placement |
| **CS Efficiency** | Creep score at 10/20 minutes |
| **Team Contribution** | Win impact and objective participation |

## 📝 Example Output

```
🏆 Match Analysis Report
**Champion**: Jinx
**Result**: ✅ WIN
**KDA**: 8/3/12 (6.67)
**Gold**: 14,500 (420/min)
**Damage**: 25,000 (720/min)
**Vision Score**: 28
**CS at 10m**: 85

💡 Recommendations:
- Great damage output! You're carrying team fights effectively
- Focus on CS efficiency - try to hit 80+ CS at 10 minutes
- Excellent vision score, keep up the ward placement
```

## 🔧 Configuration Options

```json
{
  "schedule": {
    "game_check_interval_minutes": 5,
    "weekly_summary_day": "Sunday",
    "weekly_summary_time": "20:00"
  },
  "analysis_metrics": [
    "kda",
    "gold_efficiency",
    "damage_dealt",
    "vision_score",
    "cs_at_10"
  ]
}
```

## 🏗️ Architecture

- **Riot API** - Match data and player statistics
- **Discord.py** - Bot integration and notifications
- **riotwatcher** - Python wrapper for Riot APIs
- **Scheduled Tasks** - Automatic game checking and weekly reports

## 📖 Documentation

- [Getting Started](docs/index.html)
- [API Documentation](docs/)
- [Terms of Service](TERMS_OF_SERVICE.md)
- [Privacy Policy](PRIVACY_POLICY.md)

## 🤝 Contributing

Contributions are welcome! Please read our [Contributing Guide](CONTRIBUTING.md) for details.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## ⚠️ Disclaimer

This project is not affiliated with, endorsed by, or sponsored by Riot Games, Inc. League of Legends is a trademark of Riot Games, Inc.

## 📧 Contact

- **GitHub Issues** - For bug reports and feature requests
- **Developer** - Elliot Dang (yd1008@nyu.edu)
- **Repository** - https://github.com/yd1008/lol-analyzer

## 🌟 Star History

If you find this tool helpful, please consider giving it a star on GitHub!

---

**Happy gaming! 🎮 Level up your performance today!**