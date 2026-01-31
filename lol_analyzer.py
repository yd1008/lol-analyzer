"""
LoL Performance Analyzer - Discord Bot for League of Legends Game Analysis
https://github.com/yd1008/lol-analyzer
"""

import asyncio
import json
import logging
import time
from datetime import datetime, timedelta
import requests
import discord
from discord.ext import commands, tasks
from riotwatcher import LolWatcher, ApiError


class LoLAnalyzer:
    def __init__(self, config_file='lol_analyzer_config.json'):
        with open(config_file, 'r') as f:
            self.config = json.load(f)
        
        self.lol_watcher = LolWatcher(self.config['riot_api_key'])
        self.my_region = self.config['region']
        self.summoner_name = self.config['summoner_name']
        self.discord_token = self.config['discord_bot_token']
        self.channel_id = self.config['discord_channel_id']
        
        # Get summoner info - try using PUUID directly if available
        if 'summoner_puuid' in self.config and self.config['summoner_puuid']:
            self.puuid = self.config['summoner_puuid']
            try:
                self.summoner = self.lol_watcher.summoner.by_puuid(self.my_region, self.puuid)
            except:
                self.summoner = None
        else:
            self.summoner = None
            self.puuid = None
        
        # Setup Discord bot
        intents = discord.Intents.default()
        intents.message_content = True
        self.bot = commands.Bot(command_prefix='!', intents=intents)
        
        # Track last analyzed game
        self.last_game_id = None
        
        # Setup logging
        logging.basicConfig(level=logging.INFO)
        self.logger = logging.getLogger(__name__)
    
    async def analyze_match(self, match_id):
        """Analyze a single match and return insights"""
        try:
            match_detail = self.lol_watcher.match.by_id(self.my_region, match_id)
            
            # Find player's participant info
            player_index = None
            for i, participant in enumerate(match_detail['info']['participants']):
                if participant['puuid'] == self.puuid:
                    player_index = i
                    break
            
            if player_index is None:
                self.logger.error("Player not found in match")
                return None
            
            player_data = match_detail['info']['participants'][player_index]
            
            # Extract key metrics
            kda = (player_data['kills'] + player_data['assists']) / max(1, player_data['deaths'])
            gold_earned = player_data['goldEarned']
            total_damage = player_data['totalDamageDealt']
            vision_score = player_data['visionScore']
            cs_at_10 = player_data['totalMinionsKilled'] + player_data['neutralMinionsKilled']
            
            # Calculate additional metrics based on game length
            game_duration = match_detail['info']['gameDuration']
            game_duration_minutes = game_duration / 60
            
            gold_per_min = gold_earned / game_duration_minutes
            damage_per_min = total_damage / game_duration_minutes
            
            # Determine win/loss
            win = player_data['win']
            
            # Basic analysis
            analysis = {
                'match_id': match_id,
                'champion': player_data['championName'],
                'kda': round(kda, 2),
                'kills': player_data['kills'],
                'deaths': player_data['deaths'],
                'assists': player_data['assists'],
                'gold_earned': gold_earned,
                'gold_per_min': round(gold_per_min, 2),
                'total_damage': total_damage,
                'damage_per_min': round(damage_per_min, 2),
                'vision_score': vision_score,
                'cs_at_10': cs_at_10,
                'win': win,
                'game_duration': game_duration_minutes,
                'recommendations': self.generate_recommendations(player_data, match_detail)
            }
            
            return analysis
        except Exception as e:
            self.logger.error(f"Error analyzing match {match_id}: {str(e)}")
            return None
    
    def generate_recommendations(self, player_data, match_detail):
        """Generate personalized recommendations based on performance"""
        recs = []
        
        # KDA evaluation
        kda = (player_data['kills'] + player_data['assists']) / max(1, player_data['deaths'])
        if kda < 2.0:
            recs.append("Focus on survival - your death rate is high. Consider backing off in dangerous situations.")
        elif kda > 5.0:
            recs.append("Great KDA! Consider taking more calculated risks to snowball games.")
        
        # Vision score evaluation
        if player_data['visionScore'] < 15:
            recs.append("Vision score is low. Buy control wards and place them strategically.")
        
        # Gold efficiency
        team_gold = sum(p['goldEarned'] for p in match_detail['info']['participants'][:5])
        if team_gold > 0:
            gold_share = player_data['goldEarned'] / team_gold
            if gold_share > 0.25:
                recs.append("You're getting a high gold share - make sure to capitalize on your lead.")
            elif gold_share < 0.15:
                recs.append("Consider focusing more on farming or looking for opportunities to help your team.")
        
        # Damage contribution
        team_damage = sum(p['totalDamageDealt'] for p in match_detail['info']['participants'][:5])
        if team_damage > 0:
            damage_share = player_data['totalDamageDealt'] / team_damage
            if damage_share > 0.25:
                recs.append("High damage output - great job carrying!")
            elif damage_share < 0.15:
                recs.append("Look for ways to increase your damage contribution.")
        
        if not recs:
            recs.append("Overall solid performance. Keep practicing!")
        
        return recs
    
    async def get_latest_matches(self, count=10):
        """Get latest match IDs"""
        try:
            match_list = self.lol_watcher.match.matchlist_by_puuid(
                self.my_region, 
                self.puuid, 
                count=count
            )
            return match_list
        except Exception as e:
            self.logger.error(f"Error fetching match list: {str(e)}")
            return []
    
    async def format_analysis_report(self, analysis):
        """Format analysis into a Discord-friendly message"""
        result = "✅ WIN" if analysis['win'] else "❌ LOSS"
        
        report = f"""
🏆 **Match Analysis Report**
**Champion**: {analysis['champion']}
**Result**: {result}
**KDA**: {analysis['kills']}/{analysis['deaths']}/{analysis['assists']} ({analysis['kda']})
**Gold**: {analysis['gold_earned']} ({analysis['gold_per_min']}/min)
**Damage**: {analysis['total_damage']} ({analysis['damage_per_min']}/min)
**Vision Score**: {analysis['vision_score']}
**CS at 10m**: {analysis['cs_at_10']}
**Duration**: {round(analysis['game_duration'], 1)} min

💡 **Recommendations**:
"""
        for rec in analysis['recommendations']:
            report += f"- {rec}\n"
        
        return report
    
    @tasks.loop(minutes=5)
    async def check_new_games(self):
        """Check for new games and post analysis"""
        try:
            if not self.puuid:
                return
                
            latest_matches = await self.get_latest_matches(1)
            if not latest_matches:
                return
            
            latest_match_id = latest_matches[0]
            
            # Only analyze if it's a new game we haven't seen
            if self.last_game_id != latest_match_id:
                # Small delay to ensure game data is fully processed
                await asyncio.sleep(30)
                
                analysis = await self.analyze_match(latest_match_id)
                if analysis:
                    channel = self.bot.get_channel(int(self.channel_id))
                    if channel:
                        report = await self.format_analysis_report(analysis)
                        await channel.send(report)
                    
                    # Update last game ID
                    self.last_game_id = latest_match_id
                    self.logger.info(f"Analyzed and reported game: {latest_match_id}")
        
        except Exception as e:
            self.logger.error(f"Error in check_new_games: {str(e)}")
    
    @tasks.loop(hours=24)
    async def weekly_summary(self):
        """Generate and send weekly summary"""
        # Check if today is the configured summary day
        now = datetime.now()
        if 'schedule' not in self.config or 'weekly_summary_day' not in self.config['schedule']:
            return
        
        if now.strftime('%A') != self.config['schedule']['weekly_summary_day']:
            return
        
        hour, minute = map(int, self.config['schedule']['weekly_summary_time'].split(':'))
        if now.hour != hour or now.minute < minute or now.minute >= minute + 5:
            return
        
        # Get last week's matches
        end_time = int(time.time())
        start_time = end_time - (7 * 24 * 60 * 60)
        
        try:
            matches = self.lol_watcher.match.matchlist_by_puuid(
                self.my_region,
                self.puuid,
                start_timestamp=start_time * 1000,
                end_timestamp=end_time * 1000
            )
            
            if not matches:
                return
            
            # Analyze all matches from the week
            total_games = len(matches)
            wins = 0
            total_kda = 0
            total_gold = 0
            total_damage = 0
            
            for match_id in matches:
                analysis = await self.analyze_match(match_id)
                if analysis:
                    if analysis['win']:
                        wins += 1
                    total_kda += analysis['kda']
                    total_gold += analysis['gold_per_min']
                    total_damage += analysis['damage_per_min']
            
            avg_kda = total_kda / total_games if total_games > 0 else 0
            avg_gold = total_gold / total_games if total_games > 0 else 0
            avg_damage = total_damage / total_games if total_games > 0 else 0
            win_rate = (wins / total_games) * 100 if total_games > 0 else 0
            
            summary = f"""
📊 **Weekly Summary (Last 7 Days)**
**Total Games**: {total_games}
**Win Rate**: {win_rate:.1f}% ({wins}W/{total_games-wins}L)
**Avg KDA**: {avg_kda:.2f}
**Avg Gold/min**: {avg_gold:.2f}
**Avg Damage/min**: {avg_damage:.2f}

📈 **Improvement Focus**:
"""
            
            if win_rate < 50:
                summary += "- Focus on consistency and decision-making\n"
            if avg_kda < 3.0:
                summary += "- Work on survival and engagement timing\n"
            if avg_gold < 300:
                summary += "- Improve farming efficiency and objective taking\n"
            
            channel = self.bot.get_channel(int(self.channel_id))
            if channel:
                await channel.send(summary)
        
        except Exception as e:
            self.logger.error(f"Error in weekly_summary: {str(e)}")
    
    async def run(self):
        """Run the analyzer bot"""
        @self.bot.event
        async def on_ready():
            print(f'{self.bot.user} has logged in!')
            if self.puuid:
                self.check_new_games.start()
                self.weekly_summary.start()
        
        await self.bot.start(self.discord_token)


if __name__ == "__main__":
    analyzer = LoLAnalyzer()
    asyncio.run(analyzer.run())