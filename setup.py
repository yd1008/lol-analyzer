#!/usr/bin/env python3
"""
Setup script for LoL Analyzer
This script helps configure the analyzer with your credentials
"""

import json
import os
from pathlib import Path

def main():
    print("LoL Performance Analyzer - Setup")
    print("=" * 40)
    
    # Check if config file exists
    config_path = Path("lol_analyzer_config.json")
    
    if config_path.exists():
        print("Configuration file already exists!")
        response = input("Do you want to overwrite it? (y/N): ")
        if response.lower() != 'y':
            print("Setup cancelled.")
            return
    
    print("\nLet's configure your LoL Performance Analyzer...")
    print("\nYou'll need:")
    print("- Your Riot Games API key (get it from https://developer.riotgames.com/)")
    print("- Your Discord bot token (get it from https://discord.com/developers/applications)")
    print("- Your League of Legends summoner name")
    print("- Your region (e.g., NA, KR, EUW, etc.)")
    
    # Collect user inputs
    riot_api_key = input("\nEnter your Riot API key: ").strip()
    discord_bot_token = input("Enter your Discord bot token: ").strip()
    summoner_name = input("Enter your League of Legends summoner name: ").strip()
    region = input("Enter your region (e.g., na1, kr, euw1): ").strip().lower()
    channel_id = input("Enter your Discord channel ID: ").strip()
    
    # Validate inputs
    if not all([riot_api_key, discord_bot_token, summoner_name, region, channel_id]):
        print("Error: All fields are required!")
        return
    
    # Create configuration
    config = {
        "riot_api_key": riot_api_key,
        "discord_bot_token": discord_bot_token,
        "discord_channel_id": channel_id,
        "summoner_name": summoner_name,
        "region": region,
        "analysis_metrics": [
            "kda",
            "gold_efficiency",
            "damage_dealt",
            "vision_score",
            "cs_at_10",
            "team_contribution",
            "win_probability_impact"
        ],
        "schedule": {
            "game_check_interval_minutes": 5,
            "weekly_summary_day": "Sunday",
            "weekly_summary_time": "20:00"
        }
    }
    
    # Write configuration file
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)
    
    print(f"\nConfiguration saved to {config_path}")
    print("\nNext steps:")
    print("1. Make sure you've added your Discord bot to your server")
    print("2. Ensure the bot has permissions to send messages in the target channel")
    print("3. Run the analyzer with: python lol_analyzer.py")
    print(f"\nNote: The bot will automatically post to channel ID: {channel_id}")

if __name__ == "__main__":
    main()