# ================== IMPORTS ================== #
from twitchio.ext import commands
import inspect
import requests
import asyncio
from datetime import datetime, timedelta
import pytz
import json
import time
import os

# ================== CONFIG ================== #
import logging
import configparser
import os

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Load configuration
config = configparser.ConfigParser()
config_file = 'bot_config.ini'

def load_config():
    """Load configuration from environment variables or file or create default"""
    # Try environment variables first (for Railway deployment)
    riot_api_key = os.getenv('RIOT_API_KEY')
    game_name = os.getenv('GAME_NAME')
    tag_line = os.getenv('TAG_LINE')
    region = os.getenv('REGION', 'europe')
    twitch_token = os.getenv('TWITCH_TOKEN')
    channel = os.getenv('TWITCH_CHANNEL')
    twitch_client_id = os.getenv('TWITCH_CLIENT_ID')
    twitch_client_secret = os.getenv('TWITCH_CLIENT_SECRET')
    twitch_bot_id = os.getenv('TWITCH_BOT_ID')
    sleep_in_game = os.getenv('SLEEP_IN_GAME', '25')
    sleep_out_game = os.getenv('SLEEP_OUT_GAME', '120')
    
    if riot_api_key and game_name and tag_line and twitch_token and channel:
        # Use environment variables
        config.add_section('RIOT')
        config.set('RIOT', 'api_key', riot_api_key)
        config.set('RIOT', 'game_name', game_name)
        config.set('RIOT', 'tag_line', tag_line)
        config.set('RIOT', 'region', region)

        config.add_section('TWITCH')
        config.set('TWITCH', 'token', twitch_token)
        config.set('TWITCH', 'channel', channel)
        config.set('TWITCH', 'client_id', twitch_client_id or '')
        config.set('TWITCH', 'client_secret', twitch_client_secret or '')
        config.set('TWITCH', 'bot_id', twitch_bot_id or '')

        config.add_section('BOT')
        config.set('BOT', 'sleep_in_game', sleep_in_game)
        config.set('BOT', 'sleep_out_game', sleep_out_game)
        
        logger.info("Configuration loaded from environment variables")
        return
    
    # Fallback to file
    if os.path.exists(config_file):
        config.read(config_file)
        logger.info("Configuration loaded from file")
    else:
        # Create default config
        config.add_section('RIOT')
        config.set('RIOT', 'api_key', 'RGAPI-8ca0fbb3-1bf4-498f-9669-5e35fbdf4072')
        config.set('RIOT', 'game_name', 'TheVirginVeigar')
        config.set('RIOT', 'tag_line', 'RPG')
        config.set('RIOT', 'region', 'europe')

        config.add_section('TWITCH')
        config.set('TWITCH', 'token', '2kxwdq17xr22vdjlskeeyv5bjd3n2a')
        config.set('TWITCH', 'channel', 'ruben_irpg')
        config.set('TWITCH', 'client_id', '')
        config.set('TWITCH', 'client_secret', '')
        config.set('TWITCH', 'bot_id', '')

        config.add_section('BOT')
        config.set('BOT', 'sleep_in_game', '25')
        config.set('BOT', 'sleep_out_game', '120')

        with open(config_file, 'w') as f:
            config.write(f)
        logger.info("Default configuration created")

load_config()

# Check if using default API key
if config.get('RIOT', 'api_key') == 'RGAPI-4b2d6c1f-584d-458a-8a55-177b8cf985c9':
    logger.warning("Using default Riot API key - please update bot_config.ini with a valid key")
    print("⚠️  WARNING: Using default API key. Update bot_config.ini with your Riot API key.")

# Load from config
RIOT_API_KEY = config.get('RIOT', 'api_key')
GAME_NAME = config.get('RIOT', 'game_name')
TAG_LINE = config.get('RIOT', 'tag_line')
REGION = config.get('RIOT', 'region')

TWITCH_TOKEN = config.get('TWITCH', 'token')
CHANNEL = config.get('TWITCH', 'channel')
TWITCH_CLIENT_ID = config.get('TWITCH', 'client_id', fallback='')
TWITCH_CLIENT_SECRET = config.get('TWITCH', 'client_secret', fallback='')
TWITCH_BOT_ID = config.get('TWITCH', 'bot_id', fallback='')

SLEEP_IN_GAME = config.getint('BOT', 'sleep_in_game')
SLEEP_OUT_GAME = config.getint('BOT', 'sleep_out_game')
# Keep out-of-game polling responsive while still respecting API rate limits
SLEEP_OUT_GAME = min(SLEEP_OUT_GAME, 30)

# ================== CHAMPIONS ================== #
CHAMPIONS_FILE = "champions.json"

def cargar_campeones():
    """Load champions from cache or API"""
    if os.path.exists(CHAMPIONS_FILE):
        try:
            with open(CHAMPIONS_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
            print("✅ Champions loaded from cache")
            return data
        except Exception as e:
            print(f"❌ Error loading champions cache: {e}")
    
    # Fetch from API
    print("🔄 Fetching champions from API...")
    url = "https://ddragon.leagueoflegends.com/cdn/13.24.1/data/en_US/champion.json"
    response = requests.get(url)
    response.raise_for_status()
    data = response.json()["data"]

    champ_dict = {}
    for champ in data.values():
        champ_dict[int(champ["key"])] = champ["id"]

    # Save to cache
    try:
        with open(CHAMPIONS_FILE, "w", encoding='utf-8') as f:
            json.dump(champ_dict, f)
        print("✅ Champions cached")
    except Exception as e:
        print(f"❌ Error saving champions cache: {e}")

    return champ_dict

champions = cargar_campeones()

# ================== ANTI SPAM ================== #
cooldowns = {}

def can_use(user, command, seconds=3):
    key = f"{user}_{command}"
    now = time.time()

    if key in cooldowns and now - cooldowns[key] < seconds:
        return False

    cooldowns[key] = now
    return True

def has_permission(ctx, owner_only=False):
    """Check if user has permission: owner_only=True for owner only, False for owner and mods"""
    is_owner = ctx.author.name.lower() in ["ruben_irpg", "your_twitch_username"]
    if owner_only:
        return is_owner
    else:
        return is_owner or ctx.author.is_mod



def resolve_send_channel(bot):
    """Get a channel object for sending messages safely."""
    print(f"🔍 [resolve_send_channel] Looking for channel '{CHANNEL}'")
    print(f"🔍 [resolve_send_channel] Connected channels: {bot.connected_channels}")
    # Try an existing cached value first (can be Channel object or channel name)
    cached = getattr(bot, '_cached_channel', None)
    if cached:
        # If cached is a channel object and it's still in connected_channels
        try:
            if cached in getattr(bot, 'connected_channels', []):
                print(f"✅ [resolve_send_channel] Using cached channel object: {cached}")
                return cached
        except Exception:
            pass

        # If cached is a name, try to resolve to a channel object
        try:
            name = None
            if isinstance(cached, str):
                name = cached.lstrip('#').lower()
            else:
                name = getattr(cached, 'name', None)
                if name:
                    name = name.lstrip('#').lower()

            if name:
                ch = bot.get_channel(name) or bot.get_channel(f'#{name}')
                if ch:
                    bot._cached_channel = ch
                    print(f"✅ [resolve_send_channel] Resolved cached name to channel: {ch}")
                    return ch
        except Exception:
            pass

    # If any connected channel is available, prefer that and cache it
    if getattr(bot, 'connected_channels', None):
        try:
            channel = bot.connected_channels[0]
            bot._cached_channel = channel
            print(f"✅ [resolve_send_channel] Using connected channel: {channel}")
            return channel
        except Exception:
            pass

    # Fall back to get_channel by configured name
    channel_name = CHANNEL.lstrip('#').lower()
    print(f"🔍 [resolve_send_channel] Trying bot.get_channel('{channel_name}')")
    try:
        channel = bot.get_channel(channel_name) or bot.get_channel(f'#{channel_name}')
        if channel:
            bot._cached_channel = channel
            print(f"✅ [resolve_send_channel] Found channel via get_channel: {channel}")
            return channel
    except Exception:
        pass

    print(f"❌ [resolve_send_channel] Failed to find channel '{CHANNEL}' - returning None")
    return None

async def send_channel_message(bot, message, retries=3, delay=0.5):
    """Send a message to the configured Twitch channel safely with retries."""
    if not message:
        print(f'❌ [send_channel_message] Empty message, skipping')
        return False
    
    print(f"📤 [send_channel_message] Attempting to send message (max {retries} retries): {message[:80]}...")
    
    for attempt in range(1, retries + 1):
        try:
            channel = resolve_send_channel(bot)
            if channel is None:
                print(f'❌ [send_channel_message] No channel found (attempt {attempt}/{retries})')
                if attempt < retries:
                    await asyncio.sleep(delay)
                continue
            
            print(f'📨 [send_channel_message] Sending via channel.send() (attempt {attempt}/{retries})')
            await channel.send(message)
            print(f'✅ [send_channel_message] Message sent successfully!')
            return True
            
        except Exception as e:
            print(f'❌ [send_channel_message] Send failed (attempt {attempt}/{retries}): {type(e).__name__}: {str(e)[:100]}')
            if attempt < retries:
                print(f'⏳ [send_channel_message] Retrying in {delay}s...')
                await asyncio.sleep(delay)
    
    print(f'❌ [send_channel_message] All {retries} attempts failed!')
    return False

def roman_to_int(roman):
    roman_map = {'I': 1, 'V': 5, 'X': 10, 'L': 50, 'C': 100, 'D': 500, 'M': 1000}
    total = 0
    prev_value = 0
    for char in reversed(roman.upper()):
        value = roman_map.get(char, 0)
        if value < prev_value:
            total -= value
        else:
            total += value
        prev_value = value
    return total

def format_rank(ranked_data):
    """Format rank data with better error handling"""
    if not ranked_data:
        return "Unranked"

    # Try solo queue first
    solo_queue = next((q for q in ranked_data if q.get("queueType") == "RANKED_SOLO_5x5"), None)
    if solo_queue:
        tier = solo_queue.get('tier', 'UNKNOWN').lower()
        rank_roman = solo_queue.get('rank', 'I')
        rank_num = roman_to_int(rank_roman)
        lp = solo_queue.get('leaguePoints', 0)
        wins = solo_queue.get('wins', 0)

        # Handle special cases
        if tier == 'master' or tier == 'grandmaster' or tier == 'challenger':
            return f"{tier} {lp}PL {wins} Wins"
        else:
            return f"{tier} {rank_num} {lp}PL {wins} Wins"

    # If no solo queue, try flex queue
    flex_queue = next((q for q in ranked_data if q.get("queueType") == "RANKED_FLEX_SR"), None)
    if flex_queue:
        tier = flex_queue.get('tier', 'UNKNOWN').lower()
        rank_roman = flex_queue.get('rank', 'I')
        rank_num = roman_to_int(rank_roman)
        lp = flex_queue.get('leaguePoints', 0)
        wins = flex_queue.get('wins', 0)
        return f"{tier} {rank_num} {lp}PL {wins} Wins (Flex)"

    return "Unranked"

def format_detailed_game_stats(player_data, match_data, game_type):
    """Format detailed game statistics like LouisGameDev's bot"""
    try:
        # Basic info
        champ = player_data["championName"]
        k = player_data["kills"]
        d = player_data["deaths"] 
        a = player_data["assists"]
        win = player_data["win"]
        
        # Position
        position = player_data.get("individualPosition", player_data.get("teamPosition", "UNKNOWN"))
        if position == "TOP":
            position = "Top"
        elif position == "JUNGLE":
            position = "Jungle"
        elif position == "MIDDLE":
            position = "Mid"
        elif position == "BOTTOM":
            position = "Bot"
        elif position == "UTILITY":
            position = "Support"
        
        # Result emoji
        result_emoji = "🏆Win" if win else "💀Lose"
        
        # Kill Participation
        team_id = player_data["teamId"]
        team_players = [p for p in match_data["info"]["participants"] if p["teamId"] == team_id]
        team_kills = sum(p["kills"] for p in team_players)
        kp = int((k + a) / team_kills * 100) if team_kills > 0 else 0
        
        # Total damage (format with k)
        total_dmg = player_data["totalDamageDealtToChampions"]
        dmg_str = f"{total_dmg/1000:.1f}k dmg" if total_dmg >= 1000 else f"{total_dmg} dmg"
        
        # Game duration (MM:SS)
        duration_sec = match_data["info"]["gameDuration"]
        minutes = duration_sec // 60
        seconds = duration_sec % 60
        duration_str = f"{minutes:02d}:{seconds:02d}"
        
        # CS per minute
        cs = player_data["totalMinionsKilled"] + player_data.get("totalAllyJungleMinionsKilled", 0) + player_data.get("totalEnemyJungleMinionsKilled", 0)
        cs_per_min = cs / (duration_sec / 60) if duration_sec > 0 else 0
        
        # Gold per minute
        gold = player_data["goldEarned"]
        gold_per_min = gold / (duration_sec / 60) if duration_sec > 0 else 0
        
        # Damage per minute
        dmg_per_min = total_dmg / (duration_sec / 60) if duration_sec > 0 else 0
        
        # Self-mitigated damage per minute
        self_mitigated = player_data.get("damageSelfMitigated", 0)
        self_mitigated_per_min = self_mitigated / (duration_sec / 60) if duration_sec > 0 else 0
        
        # CC time per minute
        cc_time = player_data.get("timeCCingOthers", 0)
        cc_per_min = cc_time / (duration_sec / 60) if duration_sec > 0 else 0
        
        # Vision score per minute
        vision_score = player_data.get("visionScore", 0)
        vision_per_min = vision_score / (duration_sec / 60) if duration_sec > 0 else 0
        
        # Format the message
        nickname = f"{GAME_NAME}#{TAG_LINE}"
        msg = f"{nickname} game results: {result_emoji} | {champ} | {position} | {k}/{d}/{a} | {kp}% KP | {dmg_str} | {duration_str} | {cs_per_min:.1f} cs/min | {gold_per_min:.0f} gold/min | {dmg_per_min/1000:.1f}k dmg/min | {self_mitigated_per_min/1000:.1f}k self-mitigated/min | {cc_per_min:.1f}s CC/min | {vision_per_min:.1f} vision/min"
        
        return msg
        
    except Exception as e:
        print(f"❌ Error formatting detailed stats: {e}")
        # Fallback to simple message
        champ = player_data.get("championName", "Unknown")
        k = player_data.get("kills", 0)
        d = player_data.get("deaths", 0)
        a = player_data.get("assists", 0)
        result = "🏆Win" if player_data.get("win", False) else "💀Lose"
        return f"{GAME_NAME}#{TAG_LINE} game results: {result} | {champ} | {k}/{d}/{a}"

def calculate_recent_ranked_stats(puuid, num_games=15):
    """Calculate KDA and winrate from last N ranked Solo Queue games"""
    try:
        matches = get_matches(puuid, count=num_games * 2)  # Get more to account for non-ranked games
        if not matches:
            return {"kda": 0, "winrate": 0, "games_analyzed": 0}
        
        # Load excluded matches
        cache_data = load_match_cache(puuid)
        excluded_matches = set(cache_data.get("excluded_matches", []))
        
        total_kills = 0
        total_deaths = 0
        total_assists = 0
        wins = 0
        games_analyzed = 0
        
        for match_id in matches:
            if games_analyzed >= num_games:
                break
                
            # Skip excluded matches
            if match_id in excluded_matches:
                continue
                
            match_data = get_match_data(match_id)
            if not match_data or "info" not in match_data:
                continue
            
            # Only ranked Solo Queue games
            if match_data["info"].get("queueId") != 420:
                continue
            
            # Skip remakes
            if match_data["info"]["gameDuration"] < 300:
                continue
            
            # Find player
            player = next((p for p in match_data["info"]["participants"] if p["puuid"] == puuid), None)
            if not player:
                continue
            
            # Add to totals
            total_kills += player["kills"]
            total_deaths += player["deaths"]
            total_assists += player["assists"]
            
            if player["win"]:
                wins += 1
            
            games_analyzed += 1
        
        if games_analyzed == 0:
            return {"kda": 0, "winrate": 0, "games_analyzed": 0}
        
        # Calculate averages
        avg_kda = round((total_kills + total_assists) / total_deaths, 2) if total_deaths > 0 else total_kills + total_assists
        winrate = int((wins / games_analyzed) * 100)
        
        return {
            "kda": avg_kda,
            "winrate": winrate,
            "games_analyzed": games_analyzed
        }
        
    except Exception as e:
        print(f"❌ Error calculating recent ranked stats: {e}")
        return {"kda": 0, "winrate": 0, "games_analyzed": 0}

# ================== IRELIA DATA ================== #

def cargar_datos():
    try:
        with open("irelia_data.json", "r") as f:
            return json.load(f)
    except:
        return {"games": 288, "wins": 0, "last_match_id": ""}

def guardar_datos(data):
    with open("irelia_data.json", "w") as f:
        json.dump(data, f)

# ================== PERSISTENT STATS ================== #

PERSISTENT_FILE = "bot_persistent_stats.json"

def load_persistent_stats():
    """Load persistent stats from file"""
    if os.path.exists(PERSISTENT_FILE):
        try:
            with open(PERSISTENT_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # Convert session_start back to timestamp if it's a string
                if isinstance(data.get("session_start"), str):
                    data["session_start"] = datetime.fromisoformat(data["session_start"]).timestamp()
                return data
        except Exception as e:
            print(f"⚠️ Error loading persistent stats: {e}")
    return {}

def save_persistent_stats():
    """Save current stats to file"""
    # Persist only long-term streaks and last game summary.
    # Do NOT persist per-startup session fields such as today's observed games or recent games list.
    data = {
        "win_streak": cache.get("win_streak", 0),
        "lose_streak": cache.get("lose_streak", 0),
        "max_win_streak": cache.get("max_win_streak", 0),
        "max_lose_streak": cache.get("max_lose_streak", 0),
        "last_game_id": cache.get("last_game_id"),
        "last_game": cache.get("last_game"),
        "final_message_sent_for": cache.get("final_message_sent_for")
    }
    try:
        with open(PERSISTENT_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print("💾 Streaks saved to disk")
    except Exception as e:
        print(f"⚠️ Error saving persistent stats: {e}")

def calculate_stats_from_match_cache(puuid, hours=24):
    """Use the local match cache to calculate wins/losses for the past N hours."""
    try:
        cache_data = load_match_cache(puuid)
        if not cache_data or not cache_data.get("matches"):
            return None

        now = datetime.now(pytz.timezone("UTC"))
        cutoff_time = now - timedelta(hours=hours)

        wins = 0
        losses = 0
        games = []

        for item in cache_data.get("matches", []):
            timestamp = item.get("timestamp")
            if timestamp is None:
                continue

            match_time = datetime.fromtimestamp(timestamp / 1000, tz=pytz.timezone("UTC"))
            if match_time < cutoff_time:
                continue

            result = item.get("result")
            if result == "W":
                wins += 1
                games.append("W")
            elif result == "L":
                losses += 1
                games.append("L")

        return {"wins": wins, "losses": losses, "games": games}
    except Exception as e:
        print(f"❌ Error calculating stats from match cache: {e}")
        return None


def calculate_stats_for_today(puuid):
    """Calculate ranked solo queue wins/losses for matches played since local midnight.

    This function uses timezone-aware datetimes to compare Riot's gameCreation (UTC ms)
    against the local Europe/Madrid date. It returns games in newest->oldest order.
    """
    try:
        matches = get_matches(puuid, count=200)
        if not matches:
            return {"wins": 0, "losses": 0, "games": []}

        tz = pytz.timezone("Europe/Madrid")
        today = datetime.now(tz).date()

        wins = 0
        losses = 0
        games = []  # newest -> oldest

        for match_id in matches:
            match_data = get_match_data(match_id)
            if not match_data or "info" not in match_data:
                continue

            # Riot's gameCreation is milliseconds since epoch (UTC)
            creation_ms = match_data["info"].get("gameCreation", 0)
            creation_dt = datetime.fromtimestamp(creation_ms / 1000, tz=pytz.UTC).astimezone(tz)

            # If this match is older than today and matches are sorted newest->oldest, we can stop
            if creation_dt.date() < today:
                break

            # Only consider matches from today
            if creation_dt.date() != today:
                continue

            if match_data["info"].get("queueId") != 420:
                continue
            if match_data["info"].get("gameDuration", 0) < 300:
                continue

            player = next((p for p in match_data["info"]["participants"] if p.get("puuid") == puuid), None)
            if not player:
                continue

            if player.get("win"):
                wins += 1
                games.append("W")
            else:
                losses += 1
                games.append("L")

        return {"wins": wins, "losses": losses, "games": games}
    except Exception as e:
        print(f"❌ Error calculating today's stats: {e}")
        return None


def get_today_stats(puuid):
    """Return today's ranked stats based on local Europe/Madrid game history."""
    today = datetime.now(pytz.timezone("Europe/Madrid")).date()

    if cache.get("today_date") != str(today):
        cache["today_date"] = str(today)
        cache["today_wins"] = 0
        cache["today_losses"] = 0
        cache["games"] = []

    api_stats = calculate_stats_for_today(puuid)
    if api_stats is None:
        return {
            "wins": cache.get("today_wins", 0),
            "losses": cache.get("today_losses", 0),
            "games": cache.get("games", [])
        }

    cache["today_wins"] = api_stats["wins"]
    cache["today_losses"] = api_stats["losses"]
    cache["games"] = api_stats.get("games", [])
    return {
        "wins": api_stats["wins"],
        "losses": api_stats["losses"],
        "games": api_stats.get("games", [])
    }


def _format_last_game_summary(data, puuid):
    if not data or "info" not in data:
        return None

    player = next((p for p in data["info"]["participants"] if p.get("puuid") == puuid), None)
    if not player:
        return None

    win = player.get("win", False)
    k = player.get("kills", 0)
    d = player.get("deaths", 0)
    a = player.get("assists", 0)
    champ = player.get("championName", "Unknown")
    duration = data["info"].get("gameDuration", 0)

    if duration < 300:
        resultado_text = "⏱️ REMAKE"
    else:
        resultado_text = "✅ WIN" if win else "❌ LOSE"

    return f"{champ} {k}/{d}/{a} {resultado_text}"


def load_last_game_from_cache(puuid):
    if cache.get("last_game"):
        return cache["last_game"]

    if cache.get("last_game_id"):
        data = get_match_data(cache["last_game_id"])
        summary = _format_last_game_summary(data, puuid) if data else None
        if summary:
            cache["last_game"] = summary
            return summary

    cache_data = load_match_cache(puuid)
    for item in cache_data.get("matches", []):
        match_id = item.get("match_id")
        if not match_id:
            continue
        data = get_match_data(match_id)
        if not data:
            continue
        summary = _format_last_game_summary(data, puuid)
        if summary:
            cache["last_game"] = summary
            cache["last_game_id"] = match_id
            save_persistent_stats()
            return summary

    matches = get_matches(puuid, count=5)
    for match_id in matches:
        data = get_match_data(match_id)
        if not data:
            continue
        summary = _format_last_game_summary(data, puuid)
        if summary:
            cache["last_game"] = summary
            cache["last_game_id"] = match_id
            save_persistent_stats()
            return summary

    return None


def get_authoritative_last_game(puuid, max_matches=20):
    """Fetch the most recent non-remake ranked match from Riot and return a summary string.

    This bypasses potentially stale cache and formats a clear summary for display.
    """
    try:
        matches = get_matches(puuid, count=max_matches)
        if not matches:
            return None

        for match_id in matches:
            data = get_match_data(match_id)
            if not data or "info" not in data:
                continue

            # Only ranked Solo Queue and non-remakes
            if data["info"].get("queueId") != 420:
                continue
            if data["info"].get("gameDuration", 0) < 300:
                continue

            summary = _format_last_game_summary(data, puuid)
            if summary:
                # Update in-memory cache/persistent id for future quick reads
                cache["last_game"] = summary
                cache["last_game_id"] = match_id
                save_persistent_stats()
                return summary

        return None
    except Exception as e:
        print(f"❌ Error fetching authoritative last game: {e}")
        return None


def initialize_last_game(puuid):
    recovered = False

    if cache.get("last_game_id"):
        recovered = bool(cache.get("last_game"))
        recovered = recovered or bool(load_last_game_from_cache(puuid))
    else:
        matches = get_matches(puuid, count=1)
        if not matches:
            return
        cache["last_game_id"] = matches[0]
        recovered = bool(load_last_game_from_cache(puuid))

    if recovered:
        print("✅ Last game recovered from persistence or API")
    save_persistent_stats()


async def process_finished_match(bot, match_id, data, puuid):
    """Try to send a final message for a finished match when the match data is available."""
    if not data or "info" not in data:
        return False

    player = next((p for p in data["info"]["participants"] if p["puuid"] == puuid), None)
    if not player:
        return False

    win = player["win"]
    k, d, a = player["kills"], player["deaths"], player["assists"]
    champ = player["championName"]
    queue_id = data["info"].get("queueId", 0)

    remake = data["info"].get("gameDuration", 0) < 300
    afk_detectado = False

    team_players = [
        p for p in data["info"]["participants"]
        if p["teamId"] == player["teamId"] and p["puuid"] != puuid
    ]

    if len(team_players) > 0:
        avg_gold = sum(p["goldEarned"] for p in team_players) / len(team_players)
        avg_damage = sum(p["totalDamageDealtToChampions"] for p in team_players) / len(team_players)
        avg_level = sum(p["champLevel"] for p in team_players) / len(team_players)

            for p in team_players:
                time_played = p.get("timePlayed", data["info"].get("gameDuration", 0))
                if time_played < (data["info"].get("gameDuration", 0) * 0.5):
                    afk_detectado = True
                    break

            condiciones = 0
            if p["goldEarned"] < (avg_gold * 0.35):
                condiciones += 1
            if p["totalDamageDealtToChampions"] < (avg_damage * 0.20):
                condiciones += 1
            if p["champLevel"] < (avg_level - 4):
                condiciones += 1
            if condiciones >= 2:
                afk_detectado = True
                break

    if remake:
        resultado_tipo = "REMAKE"
    elif afk_detectado and not win:
        resultado_tipo = "MITIGATED"
    elif win:
        resultado_tipo = "WIN"
    else:
        resultado_tipo = "LOSS"

    cache["last_game"] = f"{champ} {k}/{d}/{a} {'✅ WIN 🔥🔥🔥' if resultado_tipo == 'WIN' else '❌ LOSE 💀' if resultado_tipo == 'LOSS' else '🛡️ LOSS MITIGATED' if resultado_tipo == 'MITIGATED' else '⏱️ REMAKE'}"
    save_persistent_stats()

    # Only send message if we haven't already sent it for this match
    stored_final = cache.get("final_message_sent_for")
    print(f"🔎 [process_finished_match] final_message_sent_for stored={stored_final} (type={type(stored_final)}) vs match_id={match_id} (type={type(match_id)})")
    if stored_final is not None and str(stored_final) == str(match_id):
        print("ℹ️ [process_finished_match] Final message already sent for this match (skip)")
        return False

    game_type = "⭐ RANKED 🏆" if queue_id == 420 else "🧩 FLEX 5V5" if queue_id == 440 else "🎲 ARAM 🎪" if queue_id == 450 else "⚔️ ARENA 🗡️" if queue_id in [1700, 1710, 1720] else f"❓ GAME #{queue_id}"
    try:
        detailed_msg = format_detailed_game_stats(player, data, game_type)
        sent = await send_channel_message(bot, detailed_msg)
        if not sent:
            raise RuntimeError("Failed to send detailed message")
    except Exception:
        result = "WIN 🔥" if resultado_tipo == "WIN" else "LOSE 💀" if resultado_tipo == "LOSS" else "LOSS MITIGATED 🛡️" if resultado_tipo == "MITIGATED" else "REMAKE ⏱️"
        msg = f"🏁 [{game_type}] {champ.upper()} | K/D/A: {k}/{d}/{a} | {result}"
        sent = await send_channel_message(bot, msg)
        if not sent:
            print(f"❌ Failed to send fallback game end message for match {match_id}")
            return False

    cache["final_message_sent_for"] = str(match_id)
    cache["last_game_id"] = match_id
    save_persistent_stats()
    return True


async def update_match_stats_after_finish(bot, data, match_id, puuid):
    """Update ranked stats, streaks and session counters after a finished match."""
    if not data or "info" not in data:
        return False

    player = next((p for p in data["info"]["participants"] if p.get("puuid") == puuid), None)
    if not player:
        return False

    queue_id = data["info"].get("queueId", 0)
    if queue_id != 420:
        cache["last_game_id"] = match_id
        save_persistent_stats()
        return False

    if data["info"].get("gameDuration", 0) < 300:
        cache["last_game_id"] = match_id
        save_persistent_stats()
        return False

    win = player["win"]
    if win:
        old_lose_streak = cache.get("lose_streak", 0)
        cache["win_streak"] = cache.get("win_streak", 0) + 1
        cache["lose_streak"] = 0
        if old_lose_streak >= 2:
            try:
                await send_channel_message(bot, f"🔥 Lose streak of {old_lose_streak} broken! 🔥")
            except Exception as e:
                print(f"❌ Error sending streak break message: {e}")

        if cache["win_streak"] > cache.get("max_win_streak", 0):
            cache["max_win_streak"] = cache["win_streak"]

        cache["today_wins"] = cache.get("today_wins", 0) + 1
        cache["session_wins"] = cache.get("session_wins", 0) + 1
        cache["ranked_wins"] = cache.get("ranked_wins", 0) + 1
        cache["games"].insert(0, "W")
    else:
        old_win_streak = cache.get("win_streak", 0)
        cache["lose_streak"] = cache.get("lose_streak", 0) + 1
        cache["win_streak"] = 0
        if old_win_streak >= 2:
            try:
                await send_channel_message(bot, f"💀 Win streak of {old_win_streak} broken! 💀")
            except Exception as e:
                print(f"❌ Error sending streak break message: {e}")

        if cache["lose_streak"] > cache.get("max_lose_streak", 0):
            cache["max_lose_streak"] = cache["lose_streak"]

        cache["today_losses"] = cache.get("today_losses", 0) + 1
        cache["session_losses"] = cache.get("session_losses", 0) + 1
        cache["ranked_losses"] = cache.get("ranked_losses", 0) + 1
        cache["games"].insert(0, "L")

    cache["games"] = cache["games"][:5]

    zona = pytz.timezone("Europe/Madrid")
    ahora = datetime.now(zona)
    hoy = ahora.date()

    if cache.get("today_date") != str(hoy):
        cache["today_date"] = str(hoy)
        cache["today_wins"] = 0
        cache["today_losses"] = 0

    if cache.get("session_start") is None:
        cache["session_start"] = ahora.timestamp()
    elif ahora.timestamp() - cache.get("session_start", 0) >= 86400:
        cache["session_start"] = ahora.timestamp()
        cache["session_wins"] = 0
        cache["session_losses"] = 0

    cache["kda"] = round((player.get("kills", 0) + player.get("assists", 0)) / max(1, player.get("deaths", 0)), 2)
    total_session = cache.get("session_wins", 0) + cache.get("session_losses", 0)
    if total_session:
        cache["winrate"] = int((cache["session_wins"] / total_session) * 100)

    cache["last_game_id"] = match_id
    save_persistent_stats()

    if cache["win_streak"] >= 3:
        await send_channel_message(bot, f"🔥 {cache['win_streak']} win streak! (Max: {cache['max_win_streak']})")
    elif cache["lose_streak"] >= 2:
        await send_channel_message(bot, f"💀 {cache['lose_streak']} lose streak! (Max: {cache['max_lose_streak']})")

    return True


def calculate_stats_from_api(puuid, hours=24):
    """Calculate wins/losses from API match history for last N hours"""
    try:
        # Try local cache first to avoid expensive API requests
        cached_stats = calculate_stats_from_match_cache(puuid, hours)
        cache_data = load_match_cache(puuid)
        cache_recent = cache_data.get("last_updated", 0) > time.time() - 3600
        if cached_stats is not None and (cache_recent or (cached_stats["wins"] + cached_stats["losses"] > 0)):
            return cached_stats

        count = None if hours == float('inf') else 200
        matches = get_matches(puuid, count=count)
        if not matches:
            return {"wins": 0, "losses": 0, "games": []}
        
        # Load excluded matches
        cache_data = load_match_cache(puuid)
        excluded_matches = set(cache_data.get("excluded_matches", []))
        
        wins = 0
        losses = 0
        games = []
        cutoff_time = datetime.now(pytz.timezone("UTC")) - timedelta(hours=hours)
        
        for i, match_id in enumerate(matches):
            if i % 100 == 0:
                print(f"DEBUG: Processing match {i+1}/{len(matches)}")
            match_data = get_match_data(match_id)
            if not match_data or "info" not in match_data:
                continue
            
            # Skip excluded matches
            if match_id in excluded_matches:
                print(f"DEBUG: Skipping excluded match {match_id}")
                continue
            
            # Only ranked games (queue_id 420 = RANKED_SOLO_5x5)
            if match_data["info"].get("queueId") != 420:
                continue
            
            # Check if match is within time window
            match_time = datetime.fromtimestamp(match_data["info"]["gameCreation"] / 1000, tz=pytz.timezone("UTC"))
            if match_time < cutoff_time and hours != float('inf'):
                break  # Stop checking older matches
            
            # Find player in match
            player = next((p for p in match_data["info"]["participants"] if p["puuid"] == puuid), None)
            if not player:
                continue
            
            # Skip very short games (remakes)
            if match_data["info"]["gameDuration"] < 300:
                continue
            
            if player["win"]:
                wins += 1
                games.append("W")
            else:
                losses += 1
                games.append("L")
        
        print(f"DEBUG: Final stats: wins={wins}, losses={losses}")
        return {"wins": wins, "losses": losses, "games": games}
    except Exception as e:
        print(f"❌ Error calculating stats from API: {e}")
        return {"wins": 0, "losses": 0, "games": []}

def calculate_streak_from_api(puuid):
    """Calculate current win/lose streak from API match history"""
    try:
        matches = get_matches(puuid, count=100)  # Get last 100 matches for streak calculation
        if not matches:
            return {"win_streak": 0, "lose_streak": 0}
        
        # Load excluded matches
        cache_data = load_match_cache(puuid)
        excluded_matches = set(cache_data.get("excluded_matches", []))
        
        win_streak = 0
        lose_streak = 0
        
        for match_id in matches:
            # Skip excluded matches
            if match_id in excluded_matches:
                continue
                
            match_data = get_match_data(match_id)
            if not match_data or "info" not in match_data:
                continue
            
            # Only ranked games
            if match_data["info"].get("queueId") != 420:
                continue
            
            # Skip very short games
            if match_data["info"]["gameDuration"] < 300:
                continue
            
            # Find player in match
            player = next((p for p in match_data["info"]["participants"] if p["puuid"] == puuid), None)
            if not player:
                continue
            
            if player["win"]:
                if lose_streak > 0:
                    break  # Streak was broken
                win_streak += 1
            else:
                if win_streak > 0:
                    break  # Streak was broken
                lose_streak += 1
        
        return {"win_streak": win_streak, "lose_streak": lose_streak}
    except Exception as e:
        print(f"❌ Error calculating streak from API: {e}")
        return {"win_streak": 0, "lose_streak": 0}

def initialize_ranked_stats(puuid):
    """Initialize ranked wins/losses from API on startup if cache is empty"""
    try:
        cache_data = load_match_cache(puuid)
        
        # If cache is empty or old (older than 1 hour), update it
        if not cache_data["matches"] or time.time() - cache_data["last_updated"] > 3600:
            print("🔄 Updating match cache on startup...")
            update_match_cache(puuid)
            cache_data = load_match_cache(puuid)
        
        # Update global cache
        cache["ranked_wins"] = cache_data["ranked_stats"]["wins"]
        cache["ranked_losses"] = cache_data["ranked_stats"]["losses"]
        
        # Save to persistent file
        save_persistent_stats()
        
        print(f"✅ Cache loaded: {cache['ranked_wins']}W/{cache['ranked_losses']}L")
    except Exception as e:
        print(f"❌ Error initializing ranked stats: {e}")

# ================== MATCH CACHE ================== #

MATCH_CACHE_FILE = "match_cache.json"

def load_match_cache(puuid=None):
    """Load cached match data with improved validation and error handling"""
    try:
        if not os.path.exists(MATCH_CACHE_FILE):
            logger.info("Match cache file does not exist, will create new one")
            return {"matches": [], "last_updated": 0, "ranked_stats": {"wins": 0, "losses": 0}, "excluded_matches": []}

        with open(MATCH_CACHE_FILE, "r", encoding='utf-8') as f:
            data = json.load(f)

        # Validate cache structure
        if not isinstance(data, dict):
            logger.warning("Invalid cache format, resetting")
            return {"matches": [], "last_updated": 0, "ranked_stats": {"wins": 0, "losses": 0}, "excluded_matches": []}

        # Validate cache is for current PUUID
        if puuid and data.get("puuid") != puuid:
            logger.info(f"Cache PUUID mismatch: cache has {data.get('puuid')}, current is {puuid}")
            return {"matches": [], "last_updated": 0, "ranked_stats": {"wins": 0, "losses": 0}, "excluded_matches": []}

        # Ensure required fields exist
        if "matches" not in data:
            data["matches"] = []
        if "ranked_stats" not in data:
            data["ranked_stats"] = {"wins": 0, "losses": 0}
        if "excluded_matches" not in data:
            data["excluded_matches"] = []
        if "last_updated" not in data:
            data["last_updated"] = 0

        # Validate ranked_stats structure
        stats = data["ranked_stats"]
        if not isinstance(stats, dict) or "wins" not in stats or "losses" not in stats:
            logger.warning("Invalid ranked_stats in cache, resetting")
            data["ranked_stats"] = {"wins": 0, "losses": 0}

        logger.debug("Match cache loaded successfully")
        return data

    except json.JSONDecodeError as e:
        logger.error(f"Corrupted cache file: {e}, resetting")
        return {"matches": [], "last_updated": 0, "ranked_stats": {"wins": 0, "losses": 0}, "excluded_matches": []}
    except Exception as e:
        logger.error(f"Error loading match cache: {e}")
        return {"matches": [], "last_updated": 0, "ranked_stats": {"wins": 0, "losses": 0}, "excluded_matches": []}

def save_match_cache(cache_data, puuid=None):
    """Save match data to cache with error handling"""
    if puuid:
        cache_data["puuid"] = puuid

    try:
        # Create backup of existing cache
        if os.path.exists(MATCH_CACHE_FILE):
            backup_file = MATCH_CACHE_FILE + ".backup"
            os.replace(MATCH_CACHE_FILE, backup_file)

        with open(MATCH_CACHE_FILE, "w", encoding='utf-8') as f:
            json.dump(cache_data, f, indent=2, ensure_ascii=False)

        logger.debug("Match cache saved successfully")

    except Exception as e:
        logger.error(f"Error saving match cache: {e}")
        # Try to restore backup
        backup_file = MATCH_CACHE_FILE + ".backup"
        if os.path.exists(backup_file):
            try:
                os.replace(backup_file, MATCH_CACHE_FILE)
                logger.info("Restored cache from backup")
            except Exception as e2:
                logger.error(f"Failed to restore backup: {e2}")

def update_match_cache(puuid, max_matches=50):
    """Update the match cache with latest data"""
    print(f"🔄 Updating match cache (max {max_matches} matches)...")
    try:
        # Get recent matches
        matches = get_matches(puuid, count=max_matches)
        if not matches:
            print("⚠️ No matches to cache")
            return

        # Process matches for ranked stats
        wins = 0
        losses = 0
        processed_matches = []

        for i, match_id in enumerate(matches):
            if i % 20 == 0 and i > 0:
                print(f"📊 Processing match {i+1}/{len(matches)}")
            match_data = get_match_data(match_id)
            if not match_data or "info" not in match_data:
                continue

            # Only ranked games
            if match_data["info"].get("queueId") != 420:
                continue

            # Find player
            player = next((p for p in match_data["info"]["participants"] if p["puuid"] == puuid), None)
            if not player:
                continue

            # Skip remakes
            if match_data["info"]["gameDuration"] < 300:
                continue

            # Record the result
            result = "W" if player["win"] else "L"
            processed_matches.append({
                "match_id": match_id,
                "result": result,
                "timestamp": match_data["info"]["gameCreation"]
            })

            if player["win"]:
                wins += 1
            else:
                losses += 1

        # Save to cache
        cache_data = {
            "matches": processed_matches,
            "last_updated": time.time(),
            "ranked_stats": {"wins": wins, "losses": losses}
        }
        save_match_cache(cache_data, puuid)
        print(f"✅ Cache updated with {len(processed_matches)} ranked games: {wins}W/{losses}L")

    except Exception as e:
        print(f"❌ Error updating match cache: {e}")

def get_cached_stats(puuid=None):
    """Get stats from cache"""
    cache_data = load_match_cache(puuid)
    return cache_data["ranked_stats"]

# ================== CACHE ================== #

cache = {
    "games": [],
    "last_game_id": None,
    "today_date": "",
    "today_wins": 0,
    "today_losses": 0,
    "session_start": None,  # When current session started (24h window)
    "session_wins": 0,     # Wins in current session
    "session_losses": 0,   # Losses in current session
    "ranked_wins": 0,      # Total ranked wins (persistent)
    "ranked_losses": 0,    # Total ranked losses (persistent)
    "win_streak": 0,       # Current win streak (persistent)
    "lose_streak": 0,      # Current lose streak (persistent)
    "max_win_streak": 0,   # Max win streak ever
    "max_lose_streak": 0,  # Max lose streak ever
    "kda": 0,
    "winrate": 0,
    "last_game": None,
    "final_message_sent_for": None,
    "rank": "cargando...",
    "rank_last_update": None,
    "api_status": "checking...",
    "last_rank_check": 0  # Timestamp of last rank API call
}

# Load persistent stats on startup
persistent_stats = load_persistent_stats()
cache.update(persistent_stats)

# Ensure today's observed stats are zeroed at process start so !today only reflects games
# observed since this process started (no fabricated/stale data from previous runs).
zona = pytz.timezone("Europe/Madrid")
cache["today_date"] = str(datetime.now(zona).date())
cache["today_wins"] = 0
cache["today_losses"] = 0
cache["games"] = []

STARTUP_TIMESTAMP = time.time()

PUUID = None

in_game = False
last_game_live_id = None
bad_play_alerted = False

# Sentinel used when spectator API returns a transient error instead of a normal "not in game"
SPECTATOR_API_ERROR = object()

# ================== API ================== #

class RiotAPI:
    """Improved Riot API client with better rate limiting and error handling"""

    def __init__(self, api_key):
        self.api_key = api_key
        self.last_request_time = 0
        self.request_count = 0
        self.rate_limit_reset = 0

    def _wait_for_rate_limit(self):
        """Handle rate limiting intelligently"""
        current_time = time.time()

        # Reset counter every 2 minutes
        if current_time - self.rate_limit_reset > 120:
            self.request_count = 0
            self.rate_limit_reset = current_time

        # If we've made 20 requests in 2 minutes, wait
        if self.request_count >= 20:
            wait_time = 120 - (current_time - self.rate_limit_reset)
            if wait_time > 0:
                logger.warning(f"Rate limit reached, waiting {wait_time:.1f} seconds")
                time.sleep(wait_time)
                self.request_count = 0
                self.rate_limit_reset = time.time()

        # Minimum delay between requests
        time_since_last = current_time - self.last_request_time
        if time_since_last < 1.2:  # 50 requests per minute max
            time.sleep(1.2 - time_since_last)

        self.last_request_time = time.time()
        self.request_count += 1

    def make_request(self, url, max_retries=3):
        """Make API request with improved error handling and rate limiting"""
        self._wait_for_rate_limit()

        for attempt in range(max_retries):
            try:
                logger.debug(f"Making API request: {url}")
                res = requests.get(url, headers={"X-Riot-Token": self.api_key}, timeout=15)

                if res.status_code == 200:
                    logger.debug("API request successful")
                    return res.json()
                elif res.status_code == 429:  # Rate limit
                    retry_after = int(res.headers.get('Retry-After', 60))
                    logger.warning(f"Rate limited, waiting {retry_after} seconds")
                    time.sleep(min(retry_after, 120))
                    continue
                elif res.status_code == 404:  # Not found
                    if "spectator" in url:
                        logger.debug("Player not in game (expected 404)")
                        return None
                    logger.warning(f"API 404 - Resource not found: {url}")
                    return None
                elif res.status_code == 403:  # Forbidden
                    logger.error("API key expired or insufficient permissions")
                    return None
                elif res.status_code == 401:  # Unauthorized
                    logger.error("API key invalid")
                    return None
                elif res.status_code == 503:  # Service unavailable
                    logger.warning("Riot API service unavailable, retrying...")
                    time.sleep(5)
                    continue
                else:
                    logger.error(f"API error {res.status_code}: {res.text}")
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
            except requests.exceptions.Timeout:
                logger.warning(f"Request timeout (attempt {attempt + 1}/{max_retries})")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None
            except requests.exceptions.RequestException as e:
                logger.error(f"Network error: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                return None

        logger.error("All API request attempts failed")
        return None

# Initialize API client
riot_api = RiotAPI(RIOT_API_KEY)

def make_api_request(url, max_retries=3):
    """Legacy function for backward compatibility"""
    return riot_api.make_request(url, max_retries)

def get_puuid():
    """Get PUUID with improved error handling"""
    global PUUID
    if PUUID:
        return PUUID

    try:
        url = f"https://europe.api.riotgames.com/riot/account/v1/accounts/by-riot-id/{GAME_NAME}/{TAG_LINE}"
        data = riot_api.make_request(url)

        if data and "puuid" in data:
            cache["api_status"] = "working"
            PUUID = data["puuid"]
            logger.info(f"Successfully retrieved PUUID for {GAME_NAME}#{TAG_LINE}")
            return PUUID
        else:
            cache["api_status"] = "API error - check key"
            logger.error("Failed to get PUUID - check API key and summoner details")
            return None
    except Exception as e:
        logger.error(f"Error getting PUUID: {e}")
        cache["api_status"] = "API error"
        return None

def get_matches(puuid, count=None):
    """Get match IDs with improved error handling and validation"""
    if not puuid:
        logger.error("No PUUID provided to get_matches")
        return []

    try:
        all_matches = []
        start = 0
        batch_size = 100

        while True:
            url = f"https://europe.api.riotgames.com/lol/match/v5/matches/by-puuid/{puuid}/ids?start={start}&count={batch_size}"
            data = riot_api.make_request(url)

            if not data:
                logger.warning("No match data received")
                break

            if not isinstance(data, list):
                logger.error(f"Invalid match data format: {type(data)}")
                break

            all_matches.extend(data)

            # If we got fewer than batch_size, we've reached the end
            if len(data) < batch_size:
                break

            start += batch_size

            # Safety limit to prevent infinite loops
            if start > 1000:
                logger.warning("Reached maximum match fetch limit (1000+ matches)")
                break

            # If count is specified and we've reached it, stop
            if count and len(all_matches) >= count:
                all_matches = all_matches[:count]
                break

        logger.debug(f"Retrieved {len(all_matches)} matches for PUUID")
        return all_matches

    except Exception as e:
        logger.error(f"Error getting matches: {e}")
        return []

def get_match_data(match_id):
    """Get match data with validation"""
    if not match_id:
        logger.error("No match_id provided")
        return None

    try:
        url = f"https://europe.api.riotgames.com/lol/match/v5/matches/{match_id}"
        data = riot_api.make_request(url)

        if not data:
            return None

        # Validate required fields
        if "info" not in data or "participants" not in data["info"]:
            logger.warning(f"Invalid match data structure for match {match_id}")
            return None

        return data

    except Exception as e:
        logger.error(f"Error getting match data for {match_id}: {e}")
        return None

def get_rank(puuid):
    url = f"https://euw1.api.riotgames.com/lol/league/v4/entries/by-puuid/{puuid}"
    data = make_api_request(url)
    return data if data else []

def get_spectator_data(puuid):
    """Get current game spectator data with improved error handling"""
    if not puuid:
        logger.error("No PUUID provided to get_spectator_data")
        return None

    try:
        url = f"https://euw1.api.riotgames.com/lol/spectator/v5/active-games/by-puuid/{puuid}"
        riot_api._wait_for_rate_limit()
        res = requests.get(url, headers={"X-Riot-Token": riot_api.api_key}, timeout=15)

        if res.status_code == 200:
            data = res.json()
            required_fields = ["gameId", "participants", "gameQueueConfigId"]
            if not all(field in data for field in required_fields):
                logger.warning("Invalid spectator data structure")
                cache["api_status"] = "spectator API error"
                return SPECTATOR_API_ERROR

            cache["api_status"] = "working"
            return data

        if res.status_code == 404:
            logger.debug("Player not in game (spectator API 404)")
            cache["api_status"] = "working - player not in game"
            return None

        if res.status_code == 429:
            retry_after = int(res.headers.get('Retry-After', 60))
            logger.warning(f"Spectator rate limited, waiting {retry_after} seconds")
            cache["api_status"] = "spectator rate limited"
            return SPECTATOR_API_ERROR

        if res.status_code == 503:
            logger.warning("Spectator service unavailable (503)")
            cache["api_status"] = "spectator API error"
            return SPECTATOR_API_ERROR

        logger.error(f"Spectator API error {res.status_code}: {res.text}")
        cache["api_status"] = "spectator API error"
        return SPECTATOR_API_ERROR

    except requests.exceptions.Timeout:
        logger.warning("Spectator request timeout")
        cache["api_status"] = "spectator API error"
        return SPECTATOR_API_ERROR
    except requests.exceptions.RequestException as e:
        logger.error(f"Spectator request exception: {e}")
        cache["api_status"] = "spectator API error"
        return SPECTATOR_API_ERROR
    except Exception as e:
        logger.error(f"Unexpected error getting spectator data: {e}")
        cache["api_status"] = "spectator API error"
        return SPECTATOR_API_ERROR


def check_bad_midgame_performance(game_data, puuid):
    """Detect poor mid-game performance and return a warning message if needed."""
    if not game_data or "participants" not in game_data:
        return None

    player = next((p for p in game_data["participants"] if p.get("puuid") == puuid), None)
    if not player:
        return None

    # Use spectator API timing fields when available
    game_time = game_data.get("gameLength") or game_data.get("gameTime") or player.get("timePlayed") or 0
    try:
        game_minutes = int(game_time // 60)
    except Exception:
        game_minutes = 0

    # Farming threshold: below 150 CS at minute 20
    total_cs = player.get("totalMinionsKilled", 0) + player.get("totalAllyJungleMinionsKilled", 0) + player.get("totalEnemyJungleMinionsKilled", 0)

    # Very poor KDA: many deaths and low score
    kills = player.get("kills", 0)
    deaths = player.get("deaths", 0)
    assists = player.get("assists", 0)
    kda_ratio = (kills + assists) / max(1, deaths)

    if game_minutes >= 20 and total_cs < 150:
        return "Estas inteando debes de Jugar mejor amigo deja de suic*darte NOOB"

    if deaths >= 10 and kda_ratio < 0.7:
        return "Estas inteando debes de Jugar mejor amigo deja de suic*darte NOOB"

    return None

# ================== IRELIA RECIENTE ================== #

def calcular_irelia_reciente(puuid, num_games=20, max_matches=200):
    matches = get_matches(puuid, count=max_matches)

    wins = games = k = d = a = 0

    for match_id in matches:
        if games >= num_games:
            break

        data = get_match_data(match_id)
        if not data or "info" not in data:
            continue

        if data["info"].get("queueId") != 420:
            continue

        if data["info"]["gameDuration"] < 300:
            continue

        player = next(
            (p for p in data["info"]["participants"] if p["puuid"] == puuid and p["championName"] == "Irelia"),
            None
        )

        if not player:
            continue

        games += 1
        wins += int(player["win"])
        k += player["kills"]
        d += player["deaths"]
        a += player["assists"]

    if games == 0:
        return None

    return {
        "games": games,
        "wins": wins,
        "wr": int((wins / games) * 100),
        "kda": round((k + a) / d, 2) if d else k + a
    }
                
# ================= GAME CHECK ================= #
async def actualizar_datos(bot):
    global PUUID, in_game, last_game_live_id, bad_play_alerted

    consecutive_errors = 0
    max_consecutive_errors = 5
    spectator_not_in_game_count = 0
    spectator_error_count = 0
    
    print("🚀 [actualizar_datos] STARTING game update loop...")

    while True:
        try:
            if PUUID is None:
                PUUID = await asyncio.to_thread(get_puuid)
                if PUUID is None:
                    logger.warning("Cannot get PUUID - API key issue, retrying in 60 seconds")
                    await asyncio.sleep(60)
                    continue

                # Initialize ranked stats on first PUUID acquisition
                await asyncio.to_thread(initialize_ranked_stats, PUUID)
                await asyncio.to_thread(initialize_last_game, PUUID)

            puuid = PUUID

            # Check if in game (spectator API - may not be available)
            game_data = await asyncio.to_thread(get_spectator_data, puuid)

            if game_data is SPECTATOR_API_ERROR:
                spectator_error_count += 1
                spectator_not_in_game_count = 0
                logger.warning("Spectator API transient error detected; keeping previous state")
                await asyncio.sleep(5)
                continue

            if game_data is None:
                spectator_not_in_game_count += 1
                spectator_error_count = 0
                if in_game and spectator_not_in_game_count < 2:
                    logger.debug("Transient spectator no-game read; waiting for confirmation")
                    await asyncio.sleep(5)
                    continue

                if game_data is None:
                    logger.info("Spectator API confirmed player not in game")
                    game_data = False

            else:
                spectator_not_in_game_count = 0
                spectator_error_count = 0

            logger.debug(f"Game status: {'IN GAME' if game_data else 'NOT IN GAME'}")


            # ================= IN GAME ================= #
            # If spectator API returned a dict, player is in a game
            if game_data and game_data is not False:
                current_game_id = game_data.get("gameId")
                if not current_game_id:
                    await asyncio.sleep(5)
                    continue

                queue_id = game_data.get("gameQueueConfigId", 0)

                print("🎮 IN GAME | ID:", current_game_id, "| QUEUE:", queue_id)

                if queue_id == 420:
                    tipo = "RANKED 🏆"
                elif queue_id == 450:
                    tipo = "ARAM 🎲"
                elif queue_id == 440:
                    tipo = "FLEX 🧩"
                elif queue_id in [1700, 1710, 1720]:
                    tipo = "ARENA ⚔️"
                else:
                    tipo = "NORMAL 🎮"

                # START detected — suppress START messages (avoid noisy/incorrect starts)
                if current_game_id != last_game_live_id:
                    print("🚀 START DETECTADO (start message suppressed)")
                    in_game = True
                    last_game_live_id = current_game_id

            # ================= NO GAME ================= #
            # If spectator API returned explicit False, player is not in a game
            elif game_data is False:
                print("❌ NO GAME DETECTED")

                # END detected — defer final message sending to the tracker logic
                if in_game:
                    print("🏁 END DETECTADO (deferring final message to tracker)")
                    in_game = False
                    last_game_live_id = None
                    # Brief pause to let Riot's match lists settle; tracker will detect and send final message
                    await asyncio.sleep(5)
            # ==============TRAKER ================= #
            ranked = get_rank(puuid) or []
            r = next((q for q in ranked if q["queueType"] == "RANKED_SOLO_5x5"), None)
            cache["rank"] = f"{r['tier']} {r['rank']} ({r['wins']}W/{r['losses']}L)" if r else "Sin rango"

            matches = get_matches(puuid, 1) or []
            if not matches or not isinstance(matches, list):
                await asyncio.sleep(30)
                continue

            last_id = matches[0]
            data = get_match_data(last_id)
            if not data or "info" not in data:
                continue
            
            # ==============RANK UPDATE ================= #
            # Update rank periodically regardless of game status
            now = time.time()
            if now - cache["last_rank_check"] > 300:  # 5 minutes
                ranked = await asyncio.to_thread(get_rank, puuid) or []
                if ranked:
                    old_rank = cache["rank"]
                    cache["rank"] = format_rank(ranked)
                    cache["rank_last_update"] = datetime.now()
                    cache["api_status"] = "working"
                    cache["last_rank_check"] = now
                    if old_rank != cache["rank"]:
                        print(f"✅ Rank updated: {cache['rank']}")
                    else:
                        print("✅ Rank checked (no change)")
                else:
                    cache["api_status"] = "API error - check key"
                    cache["last_rank_check"] = now

            matches = await asyncio.to_thread(get_matches, puuid, 1) or []
            if not matches or not isinstance(matches, list):
                await asyncio.sleep(30)
                continue

            last_id = matches[0]
            data = await asyncio.to_thread(get_match_data, last_id)
            if not data or "info" not in data:
                await asyncio.sleep(30)
                continue
            
            # 🧠 PRIMERA EJECUCIÓN (NO CONTAR)
            if cache["last_game_id"] is None:
                cache["last_game_id"] = last_id
                print("ℹ️  First run - skipping this match to avoid spam")
                continue
            
            # 🔥 ANTI SPAM - Skip if same match and already announced
            if last_id == cache["last_game_id"]:
                if str(cache.get("final_message_sent_for")) == str(last_id):
                    print(f"ℹ️  Same match {last_id} already announced, sleeping")
                    await asyncio.sleep(SLEEP_OUT_GAME)
                    continue
                print(f"ℹ️  Same match {last_id} seen again but announcement not sent yet, retrying")
            else:
                print(f"🎉 NEW MATCH DETECTED: {last_id}")

            # ---- IRELIA ----
            data_guardada = cargar_datos()

            if last_id != data_guardada.get("last_match_id", ""):

                if data["info"]["gameDuration"] >= 300:
                    for p in data["info"]["participants"]:
                        if p["puuid"] == puuid and p["championName"] == "Irelia":
                            data_guardada["games"] += 1
                            data_guardada["wins"] += int(p["win"])

                data_guardada["last_match_id"] = last_id
                guardar_datos(data_guardada)

            # ---- GENERAL ----

            queue_id = data["info"]["queueId"]

            # Get game type
            if queue_id == 420:
                game_type = "⭐ RANKED 🏆"
            elif queue_id == 440:
                game_type = "🧩 FLEX 5V5"
            elif queue_id == 450:
                game_type = "🎲 ARAM 🎪"
            elif queue_id in [1700, 1710, 1720]:
                game_type = "⚔️ ARENA 🗡️"
            elif queue_id in [400, 430]:
                game_type = "🎮 NORMAL 🎯"
            else:
                game_type = f"❓ GAME #{queue_id}"

            player = next((p for p in data["info"]["participants"] if p["puuid"] == puuid), None)
            if not player:
                cache["last_game_id"] = last_id
                continue

            win = player["win"]
            k, d, a = player["kills"], player["deaths"], player["assists"]
            champ = player["championName"]

            # ================= TIPO DE PARTIDA ================= #
            duracion = data["info"]["gameDuration"]

            remake = duracion < 300
            afk_detectado = False

            team_players = [
                p for p in data["info"]["participants"]
                if p["teamId"] == player["teamId"] and p["puuid"] != puuid
            ]

            if len(team_players) > 0:
                avg_gold = sum(p["goldEarned"] for p in team_players) / len(team_players)
                avg_damage = sum(p["totalDamageDealtToChampions"] for p in team_players) / len(team_players)
                avg_level = sum(p["champLevel"] for p in team_players) / len(team_players)

                for p in team_players:
                    time_played = p.get("timePlayed", duracion)
                    if time_played < (duracion * 0.5):
                        afk_detectado = True
                        break

                    condiciones = 0

                    if p["goldEarned"] < (avg_gold * 0.35):
                        condiciones += 1
                    if p["totalDamageDealtToChampions"] < (avg_damage * 0.20):
                        condiciones += 1
                    if p["champLevel"] < (avg_level - 4):
                        condiciones += 1

                    if condiciones >= 2:
                        afk_detectado = True
                        break

            if remake:
                resultado_tipo = "REMAKE"
            elif afk_detectado and not win:
                resultado_tipo = "MITIGATED"
            elif win:
                resultado_tipo = "WIN"
            else:
                resultado_tipo = "LOSS"

            cache["resultado_tipo"] = resultado_tipo

            # TEXTO
            if resultado_tipo == "WIN":
                texto = "✅ WIN 🔥🔥🔥"
            elif resultado_tipo == "LOSS":
                texto = "❌ LOSE 💀"
            elif resultado_tipo == "MITIGATED":
                texto = "🛡️ LOSS MITIGATED"
            else:
                texto = "⏱️ REMAKE"

            cache["last_game"] = f"{champ} {k}/{d}/{a} {texto}"
            save_persistent_stats()

            # 🔥 SEND END GAME MESSAGE FOR ALL GAME TYPES 🔥
            stored_final = cache.get("final_message_sent_for")
            print(f"🔎 [NEW MATCH END] Checking if message already sent: stored={stored_final}, current_id={last_id}")
            
            if stored_final is None or str(stored_final) != str(last_id):
                print(f"🚨 [NEW MATCH END] Need to send message for match {last_id}")
                sent = False
                
                # Try detailed message
                try:
                    print(f"📝 [NEW MATCH END] Trying detailed message...")
                    detailed_msg = format_detailed_game_stats(player, data, game_type)
                    sent = await send_channel_message(bot, detailed_msg, retries=3)
                except Exception as e:
                    print(f"❌ [NEW MATCH END] Detailed message error: {e}")
                
                # If detailed failed, try simple message
                if not sent:
                    try:
                        simple_msg = f"🏁 [{game_type}] {champ} | {k}/{d}/{a} | {texto}"
                        print(f"⚠️ [NEW MATCH END] Trying simple message...")
                        sent = await send_channel_message(bot, simple_msg, retries=3)
                    except Exception as e:
                        print(f"❌ [NEW MATCH END] Simple message error: {e}")
                
                if sent:
                    print(f"✅ [NEW MATCH END] Message sent successfully!")
                    cache["final_message_sent_for"] = str(last_id)
                    save_persistent_stats()
                else:
                    print(f"⚠️ [NEW MATCH END] Message send failed, will retry later")
                    # Keep last_game_id so this match remains visible for retry,
                    # but do not mark final_message_sent_for until success.
                    cache["last_game_id"] = last_id
                    save_persistent_stats()
            else:
                print(f"ℹ️ [NEW MATCH END] Message already sent for this match, skipping")

            # Ensure last_game_id is always updated
            cache["last_game_id"] = last_id
            save_persistent_stats()

            # Only update daily stats for ranked games
            if queue_id != 420:
                print(f"ℹ️  {game_type} game detected (not ranked) - skipping streak update")
                await asyncio.sleep(SLEEP_OUT_GAME)
                continue

            print(f"ℹ️  Ranked game detected - updating stats...")
            await update_match_stats_after_finish(bot, data, last_id, puuid)

        except Exception as e:
            consecutive_errors += 1
            logger.error(f"💥 ERROR GENERAL (#{consecutive_errors}): {e}")

            if consecutive_errors >= max_consecutive_errors:
                logger.critical(f"Too many consecutive errors ({consecutive_errors}), restarting in 5 minutes")
                await asyncio.sleep(300)  # 5 minutes
                consecutive_errors = 0
            else:
                await asyncio.sleep(30)  # Shorter wait for transient errors

        if in_game:
            await asyncio.sleep(SLEEP_IN_GAME)
        else:
            await asyncio.sleep(SLEEP_OUT_GAME)
# ================== BOT ================== #

class Bot(commands.Bot):

    def __init__(self):
        bot_kwargs = {
            'token': TWITCH_TOKEN,
            'prefix': '!',
            'initial_channels': [CHANNEL]
        }

        bot_init_sig = inspect.signature(commands.Bot.__init__)
        required_twitch_kwargs = []
        for name in ('client_id', 'client_secret', 'bot_id'):
            param = bot_init_sig.parameters.get(name)
            if param is not None:
                bot_kwargs[name] = globals().get(f'TWITCH_{name.upper()}', '')
                if param.default is inspect._empty:
                    required_twitch_kwargs.append(name)

        if required_twitch_kwargs:
            missing = [name for name in required_twitch_kwargs if not bot_kwargs.get(name)]
            if missing:
                raise RuntimeError(
                    'TwitchIO configuration requires: ' + ', '.join(missing) + 
                    '. Add them to your Railway environment variables or bot_config.ini.'
                )

        super().__init__(**bot_kwargs)
        self._cached_channel = None

    async def event_ready(self):
        print(f'🚀 Bot conectado como {self.nick}')
        print(f'📡 [Bot.event_ready] Connected channels: {self.connected_channels}')
        print(f'📡 [Bot.event_ready] Configured channel: {CHANNEL}')
        print(f'📡 [Bot.event_ready] Total connected channels: {len(self.connected_channels)}')
        self.loop.create_task(actualizar_datos(self))

    @commands.command()
    async def hora(self, ctx):
        if not can_use(ctx.author.name, "hora"): return
        zona = pytz.timezone("Europe/Madrid")
        await ctx.send(datetime.now(zona).strftime("Hora: %H:%M:%S"))

    @commands.command()
    async def rank(self, ctx):
        if not can_use(ctx.author.name, "rank"): return

        rank_info = cache["rank"]
        if cache["rank_last_update"]:
            # Show how fresh the data is
            time_diff = datetime.now() - cache["rank_last_update"]
            minutes_ago = int(time_diff.total_seconds() / 60)
            if minutes_ago < 1:
                freshness = " (just updated)"
            elif minutes_ago == 1:
                freshness = " (1 min ago)"
            else:
                freshness = f" ({minutes_ago} mins ago)"
            rank_info += freshness

        await ctx.send(rank_info)

    @commands.command()
    async def apistatus(self, ctx):
        if not can_use(ctx.author.name, "apistatus"): return
        if not has_permission(ctx, owner_only=True): await ctx.send("❌ Permission denied"); return
        status = cache["api_status"]
        await ctx.send(f"API Status: {status}")

    @commands.command()
    async def rankrefresh(self, ctx):
        if not can_use(ctx.author.name, "rankrefresh"): return
        if not has_permission(ctx, owner_only=False): await ctx.send("❌ Permission denied"); return

        # Manual rank refresh
        if PUUID:
            ranked = await asyncio.to_thread(get_rank, PUUID) or []
            if ranked:
                cache["rank"] = format_rank(ranked)
                cache["rank_last_update"] = datetime.now()
                cache["api_status"] = "working"
                await ctx.send(f"✅ Rank updated: {cache['rank']}")
            else:
                await ctx.send("❌ Failed to refresh rank - check API status")
        else:
            await ctx.send("❌ Cannot refresh - PUUID not available")

    @commands.command()
    async def clearcache(self, ctx):
        if not can_use(ctx.author.name, "clearcache"): return
        if not has_permission(ctx, owner_only=False): await ctx.send("❌ Permission denied"); return
        
        try:
            import os
            if os.path.exists(MATCH_CACHE_FILE):
                os.remove(MATCH_CACHE_FILE)
                await ctx.send("🗑️ Cache cleared! Use !refresh to rebuild it.")
            else:
                await ctx.send("📁 No cache file found.")
        except Exception as e:
            await ctx.send(f"❌ Error clearing cache: {str(e)}")

    @commands.command()
    async def refresh(self, ctx):
        if not can_use(ctx.author.name, "refresh"): return
        if not has_permission(ctx, owner_only=False): await ctx.send("❌ Permission denied"); return
        
        if not PUUID:
            await ctx.send("❌ Cannot refresh - PUUID not available")
            return
        
        await ctx.send("🔄 Refreshing match cache... This may take a while.")
        
        # Run in background to avoid blocking
        import asyncio
        asyncio.create_task(self.refresh_cache_async(ctx, PUUID))

    async def refresh_cache_async(self, ctx, puuid):
        try:
            await asyncio.to_thread(update_match_cache, puuid)
            cache_data = await asyncio.to_thread(load_match_cache, puuid)
            stats = cache_data["ranked_stats"]
            await ctx.send(f"✅ Cache refreshed! Current stats: {stats['wins']}W/{stats['losses']}L")
        except Exception as e:
            await ctx.send(f"❌ Error refreshing cache: {str(e)}")

    @commands.command()
    async def updatekey(self, ctx, new_key: str = None):
        """Update API key - usage: !updatekey RGAPI-xxxxx"""
        if ctx.author.name.lower() not in ["ruben_irpg", "your_twitch_username"]:  # Only allow bot owner
            await ctx.send("❌ Only bot owner can update API key")
            return

        if not new_key or not new_key.startswith("RGAPI-"):
            await ctx.send("❌ Invalid key format. Use: !updatekey RGAPI-xxxxx")
            return

        try:
            # Update config file
            config.set('RIOT', 'api_key', new_key)
            with open(config_file, 'w') as f:
                config.write(f)

            # Update runtime variable
            global RIOT_API_KEY, riot_api
            RIOT_API_KEY = new_key
            riot_api = RiotAPI(RIOT_API_KEY)

            # Test the new key
            test_puuid = get_puuid()
            if test_puuid:
                global PUUID
                PUUID = test_puuid  # Update PUUID with new key
                await ctx.send("✅ API key updated and working!")
                logger.info("API key updated successfully")
            else:
                await ctx.send("❌ API key updated but not working - check the key")
                logger.warning("API key updated but validation failed")

        except Exception as e:
            await ctx.send(f"❌ Error updating API key: {str(e)}")
            logger.error(f"Error updating API key: {e}")

    @commands.command()
    async def health(self, ctx):
        """Check bot health and API status"""
        if not can_use(ctx.author.name, "health"): return
        if not has_permission(ctx, owner_only=False): await ctx.send("❌ Permission denied"); return

        health_status = {
            "puuid": "✅ Available" if PUUID else "❌ Missing",
            "api_status": cache.get("api_status", "unknown"),
            "cache_loaded": "✅ Yes" if os.path.exists(MATCH_CACHE_FILE) else "❌ No",
            "config_loaded": "✅ Yes" if os.path.exists(config_file) else "❌ No",
            "last_rank_update": cache.get("rank_last_update", "Never"),
            "uptime": "Bot running"
        }

        response = "🤖 Bot Health Check:\n" + "\n".join(f"• {k}: {v}" for k, v in health_status.items())
        await ctx.send(response)

    @commands.command()
    async def irelia(self, ctx):
        if not can_use(ctx.author.name, "irelia"): return
        puuid = PUUID or get_puuid()

        if not puuid:
            await ctx.send("❌ Cannot calculate - PUUID not available")
            return

        reciente = await asyncio.to_thread(calcular_irelia_reciente, puuid, 20, 100)

        if not reciente:
            await ctx.send("No hay partidas recientes de Irelia en Solo Queue")
            return

        await ctx.send(
            f"⚔️ Irelia SoloQ last {reciente['games']} games: {reciente['wins']}W/{reciente['games']-reciente['wins']}L | WR {reciente['wr']}% | KDA {reciente['kda']}"
        )

    @commands.command(aliases=["lastgame", "ult"])
    async def last(self, ctx):
        if not can_use(ctx.author.name, "last"): return

        puuid = PUUID or get_puuid()
        if not puuid:
            await ctx.send("❌ Cannot calculate - PUUID not available")
            return

        # Try authoritative fetch from Riot first, then fall back to cache
        last_game_text = await asyncio.to_thread(get_authoritative_last_game, puuid)
        if not last_game_text:
            last_game_text = cache.get("last_game") or await asyncio.to_thread(load_last_game_from_cache, puuid)

        if last_game_text:
            await ctx.send(f"Last game: {last_game_text}")
        else:
            await ctx.send("No last game data available")

    @commands.command(aliases=["todaystats", "hoy", "sesion"])
    async def today(self, ctx):
        if not can_use(ctx.author.name, "today"): return
        
        puuid = PUUID or get_puuid()
        if not puuid:
            await ctx.send("❌ Cannot calculate - PUUID not available")
            return
        
        stats = await asyncio.to_thread(get_today_stats, puuid)
        total = stats["wins"] + stats["losses"]
        
        if total == 0:
            await ctx.send("📅 Today (24h): No ranked games observed since bot startup")
        else:
            wr = int((stats["wins"] / total) * 100)
            
            # Create visual representation: 🟦 for wins, 🟥 for losses (newest -> oldest)
            visual_games = ["🟦" if game == "W" else "🟥" for game in stats.get("games", [])]
            visual_str = "".join(visual_games)

            await ctx.send(f"📅 Today (24h): {stats['wins']}W/{stats['losses']}L Winrate {wr}% {visual_str}")

    @commands.command(aliases=["victorias", "w"])
    async def wins(self, ctx):
        if not can_use(ctx.author.name, "wins"): return
        
        puuid = PUUID or get_puuid()
        if not puuid:
            await ctx.send("❌ Cannot calculate - PUUID not available")
            return
        
        stats = await asyncio.to_thread(get_today_stats, puuid)
        await ctx.send(f"🏆 Today's Ranked Wins: {stats['wins']}")

    @commands.command(aliases=["derrotas", "l"])
    async def losses(self, ctx):
        if not can_use(ctx.author.name, "losses"): return
        
        puuid = PUUID or get_puuid()
        if not puuid:
            await ctx.send("❌ Cannot calculate - PUUID not available")
            return
        
        stats = await asyncio.to_thread(get_today_stats, puuid)
        await ctx.send(f"💀 Today's Ranked Losses: {stats['losses']}")

    @commands.command(aliases=["help"])
    async def cmd(self, ctx):
        if not can_use(ctx.author.name, "cmd"): return
        help_text = """
🎮 Bot Commands:
!hora - Show current time
!rank - Show current League rank
!apistatus - Check API status (owner only)
!rankrefresh - Manually refresh rank (owner only and mods)
!clearcache - Clear match cache (owner only and mods)
!refresh - Rebuild match cache from API (owner only and mods)
!updatekey <key> - Update Riot API key (owner only)
!health - Check bot health and status (owner only and mods)
!irelia - Show Irelia stats
!last (aliases: !lastgame, !ult) - Show last game result
!today (aliases: !sesion, !todaystats, !hoy) - Show session stats (24h) with visual history
!wins (aliases: !victorias, !w) - Show today's ranked wins (24h)
!losses (aliases: !derrotas, !l) - Show today's ranked losses (24h)
!cmd (!help) - List all commands (help)
!kda (aliases: !kd, !stats) - Show average KDA from last 15 ranked games
!winrate (aliases: !wr) - Show winrate from last 15 ranked games
!tilt (aliases: !tilted, !tilteado) - Check lose streak
!winstreak (aliases: !streak, !racha) - Show current win streak
!historial (aliases: !history, !games) - Show recent games
!clearlose - Remove most recent loss from today's stats (owner only and mods)
!setstreak <number> - Manually set win streak (owner only and mods)

🔥 Automatic Game End Messages:
Bot automatically posts detailed game results with K/D/A, Kill Participation, damage, CS/min, gold/min, and more - just like LouisGameDev's bot!
        """.strip()
        await ctx.send(help_text)

    @commands.command(aliases=["kd", "stats"])
    async def kda(self, ctx):
        if not can_use(ctx.author.name, "kda"): return
        
        puuid = PUUID or get_puuid()
        if not puuid:
            await ctx.send("❌ Cannot calculate - PUUID not available")
            return
        
        # Calculate from last 15 ranked games
        stats = await asyncio.to_thread(calculate_recent_ranked_stats, puuid, 15)
        
        if stats["games_analyzed"] == 0:
            await ctx.send("❌ No recent ranked games found")
        else:
            await ctx.send(f"KDA: {stats['kda']} (Last {stats['games_analyzed']} ranked games)")

    @commands.command(aliases=["wr"])
    async def winrate(self, ctx):
        if not can_use(ctx.author.name, "winrate"): return
        
        puuid = PUUID or get_puuid()
        if not puuid:
            await ctx.send("❌ Cannot calculate - PUUID not available")
            return
        
        # Calculate from last 15 ranked games
        stats = await asyncio.to_thread(calculate_recent_ranked_stats, puuid, 15)
        
        if stats["games_analyzed"] == 0:
            await ctx.send("❌ No recent ranked games found")
        else:
            await ctx.send(f"WR: {stats['winrate']}% (Last {stats['games_analyzed']} ranked games)")

    @commands.command(aliases=["tilted", "tilteado"])
    async def tilt(self, ctx):
        if not can_use(ctx.author.name, "tilt"): return
        
        puuid = PUUID or get_puuid()
        if not puuid:
            await ctx.send("❌ Cannot calculate - PUUID not available")
            return
        
        # Recalculate streak from API
        streak_data = await asyncio.to_thread(calculate_streak_from_api, puuid)
        cache["lose_streak"] = streak_data["lose_streak"]
        
        # Update max lose streak
        if cache["lose_streak"] > cache["max_lose_streak"]:
            cache["max_lose_streak"] = cache["lose_streak"]
            save_persistent_stats()
        
        if cache["lose_streak"] >= 2:
            await ctx.send(f"💀 {cache['lose_streak']} loss streak! (Max: {cache['max_lose_streak']})")
        else:
            await ctx.send("Chill 😎")

    @commands.command(aliases=["streak", "racha"])
    async def winstreak(self, ctx):
        if not can_use(ctx.author.name, "winstreak"): return
        
        puuid = PUUID or get_puuid()
        if not puuid:
            await ctx.send("❌ Cannot calculate - PUUID not available")
            return
        
        # Recalculate streak from API
        streak_data = await asyncio.to_thread(calculate_streak_from_api, puuid)
        cache["win_streak"] = streak_data["win_streak"]
        cache["lose_streak"] = streak_data["lose_streak"]
        
        # Update max win streak
        if cache["win_streak"] > cache["max_win_streak"]:
            cache["max_win_streak"] = cache["win_streak"]
            save_persistent_stats()
        
        if cache["win_streak"] > 0:
            await ctx.send(f"🔥 {cache['win_streak']} win streak! (Max: {cache['max_win_streak']})")
        elif cache["lose_streak"] > 0:
            await ctx.send(f"💀 {cache['lose_streak']} lose streak! (Max: {cache['max_lose_streak']})")
        else:
            await ctx.send("No active streak")

    @commands.command(aliases=["history", "games"])
    async def historial(self, ctx):
        if not can_use(ctx.author.name, "historial"): return
        await ctx.send(" - ".join(cache["games"]) or "Sin historial")

    @commands.command()
    async def clearlose(self, ctx):
        if not can_use(ctx.author.name, "clearlose"): return
        if not has_permission(ctx, owner_only=False): await ctx.send("❌ Permission denied"); return
        
        if not PUUID:
            await ctx.send("❌ Cannot clear loss - PUUID not available")
            return
        
        try:
            # Get recent matches to find the last loss
            matches = get_matches(PUUID, count=20)  # Get last 20 matches
            if not matches:
                await ctx.send("❌ No recent matches found")
                return
            
            # Load current cache
            cache_data = load_match_cache(PUUID)
            excluded_matches = set(cache_data.get("excluded_matches", []))
            
            # Find the most recent loss that isn't already excluded
            last_loss_match = None
            for match_id in matches:
                if match_id in excluded_matches:
                    continue
                    
                match_data = get_match_data(match_id)
                if not match_data or "info" not in match_data:
                    continue
                
                # Only ranked games
                if match_data["info"].get("queueId") != 420:
                    continue
                
                # Check if within 24 hours
                match_time = datetime.fromtimestamp(match_data["info"]["gameCreation"] / 1000, tz=pytz.timezone("UTC"))
                cutoff_time = datetime.now(pytz.timezone("UTC")) - timedelta(hours=24)
                if match_time < cutoff_time:
                    break  # No more recent matches
                
                # Skip remakes
                if match_data["info"]["gameDuration"] < 300:
                    continue
                
                # Find player
                player = next((p for p in match_data["info"]["participants"] if p["puuid"] == PUUID), None)
                if not player:
                    continue
                
                # Check if it's a loss
                if not player["win"]:
                    last_loss_match = match_id
                    break  # Found the most recent loss
            
            if not last_loss_match:
                await ctx.send("❌ No recent losses found to clear")
                return
            
            # Add to excluded matches
            excluded_matches.add(last_loss_match)
            cache_data["excluded_matches"] = list(excluded_matches)
            save_match_cache(cache_data, PUUID)
            
            await ctx.send(f"✅ Cleared most recent loss (match {last_loss_match[:10]}...)")
            
        except Exception as e:
            await ctx.send(f"❌ Error clearing loss: {str(e)}")

    @commands.command()
    async def setstreak(self, ctx, new_streak: int = None):
        if not can_use(ctx.author.name, "setstreak"): return
        if not has_permission(ctx, owner_only=False): await ctx.send("❌ Permission denied"); return
        
        if new_streak is None:
            await ctx.send("❌ Usage: !setstreak <number> (e.g. !setstreak 5)")
            return
        
        if new_streak < 0:
            await ctx.send("❌ Streak cannot be negative")
            return
        
        try:
            # Set the win streak
            cache["win_streak"] = new_streak
            cache["lose_streak"] = 0  # Reset lose streak when manually setting win streak
            
            # Save to persistent stats
            save_persistent_stats()
            
            await ctx.send(f"✅ Win streak set to {new_streak}")
            
        except Exception as e:
            await ctx.send(f"❌ Error setting streak: {str(e)}")

# ================== RUN ================== #

async def main():
    bot = Bot()
    await bot.start()

asyncio.run(main())
