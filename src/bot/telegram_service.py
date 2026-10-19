"""
Garmin AI Coach - Telegram Bot Service
Handles athlete-specific push notifications and interactive coaching commands.
"""
import logging
from typing import Optional, Dict, Any, List
import telebot
from telebot.types import Message

from src.config import TELEGRAM_BOT_TOKEN, load_users_config
from src.database.db import (
    get_daily_health,
    get_recent_daily_health,
    get_recent_activities,
    get_latest_insight,
)
from src.ai.gemini_client import GeminiCoach

logger = logging.getLogger(__name__)

bot: Optional[telebot.TeleBot] = None
if TELEGRAM_BOT_TOKEN:
    try:
        bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
    except Exception as e:
        logger.error(f"Failed to initialize Telegram bot: {e}")


def get_athlete_by_chat_id(chat_id: int) -> Optional[Dict[str, Any]]:
    users = load_users_config()
    for u in users:
        if u.get("telegram_chat_id") == chat_id:
            return u
    return None


def send_notification(chat_id: int, text: str) -> bool:
    """Sends a message to a specific Telegram chat ID with Markdown and plain-text fallback."""
    if not bot or not chat_id:
        return False

    try:
        # Split into chunks if message exceeds Telegram limit (4096 chars)
        max_len = 4000
        for i in range(0, len(text), max_len):
            chunk = text[i:i + max_len]
            try:
                bot.send_message(chat_id, chunk, parse_mode="Markdown")
            except Exception as e:
                # If markdown fails due to unescaped special characters, fallback cleanly to plain text
                logger.warning(f"Markdown parsing failed on Telegram message ({e}). Retrying with plain text.")
                bot.send_message(chat_id, chunk, parse_mode="")
        return True
    except Exception as e:
        logger.error(f"Failed to send Telegram message to {chat_id}: {e}")
        return False


def setup_bot_handlers():
    """Configures message and command handlers on the telebot instance."""
    if not bot:
        return

    ai_coach = GeminiCoach()

    @bot.message_handler(commands=["start", "help"])
    def handle_start(message: Message):
        chat_id = message.chat.id
        athlete = get_athlete_by_chat_id(chat_id)

        if athlete:
            name = athlete.get("display_name", "Athlete")
            sports = ", ".join(athlete.get("primary_sports", []))
            reply = (
                f"👋 *Welcome back, {name}!* 🏃‍♂️\n\n"
                f"Your Garmin AI Coach is active.\n"
                f"• *Tracked Sports:* {sports}\n\n"
                f"*Available Commands:*\n"
                f"• `/readiness` — View today's sleep score, HRV, and morning AI verdict\n"
                f"• `/workout` — Review your latest workout breakdown\n"
                f"• `/coach <question>` — Ask for training advice or recovery tips\n"
            )
        else:
            reply = (
                "👋 *Welcome to Garmin AI Coach!*\n\n"
                "Your Telegram Chat ID is: `" + str(chat_id) + "`\n\n"
                "To link this chat to your Garmin account, add this ID to `config/users.yaml`:\n"
                "```yaml\n"
                f"telegram_chat_id: {chat_id}\n"
                "```"
            )
        bot.reply_to(message, reply)

    @bot.message_handler(commands=["readiness"])
    def handle_readiness(message: Message):
        chat_id = message.chat.id
        athlete = get_athlete_by_chat_id(chat_id)
        if not athlete:
            bot.reply_to(message, "⚠️ You are not registered in `config/users.yaml`.")
            return

        user_id = athlete["id"]
        insight = get_latest_insight(user_id, "morning")
        if insight:
            bot.reply_to(message, f"🌅 *Morning Readiness Briefing:*\n\n{insight['text']}")
        else:
            bot.reply_to(message, "No morning readiness briefing generated yet today. Siphon Garmin data first!")

    @bot.message_handler(commands=["workout"])
    def handle_workout(message: Message):
        chat_id = message.chat.id
        athlete = get_athlete_by_chat_id(chat_id)
        if not athlete:
            bot.reply_to(message, "⚠️ You are not registered in `config/users.yaml`.")
            return

        user_id = athlete["id"]
        activities = get_recent_activities(user_id, limit=1)
        if not activities:
            bot.reply_to(message, "No recent workouts found in database.")
            return

        last_act = activities[0]
        act_id = str(last_act["activity_id"])
        insight = get_latest_insight(user_id, "post_activity", act_id)

        header = f"🏃 *Last Workout:* {last_act.get('name')} ({last_act.get('sport_type')})\n"
        if insight:
            bot.reply_to(message, f"{header}\n{insight['text']}")
        else:
            bot.reply_to(message, f"{header}\nDuration: {round(last_act.get('duration_seconds', 0)/60, 1)} min | Distance: {round(last_act.get('distance_meters', 0)/1000, 2)} km")

    @bot.message_handler(commands=["coach"])
    def handle_coach_command(message: Message):
        chat_id = message.chat.id
        athlete = get_athlete_by_chat_id(chat_id)
        if not athlete:
            bot.reply_to(message, "⚠️ You are not registered in `config/users.yaml`.")
            return

        question = message.text.replace("/coach", "").strip()
        if not question:
            bot.reply_to(message, "Please provide a question. Example: `/coach Should I do my interval session today?`")
            return

        bot.send_chat_action(chat_id, "typing")
        user_id = athlete["id"]
        recent_health = get_recent_daily_health(user_id, days=7)
        recent_acts = get_recent_activities(user_id, limit=7)

        response = ai_coach.ask_coach(athlete, question, recent_health, recent_acts)
        bot.reply_to(message, response)

    @bot.message_handler(func=lambda msg: not msg.text.startswith("/"))
    def handle_plain_text(message: Message):
        chat_id = message.chat.id
        athlete = get_athlete_by_chat_id(chat_id)
        if not athlete:
            return

        bot.send_chat_action(chat_id, "typing")
        user_id = athlete["id"]
        recent_health = get_recent_daily_health(user_id, days=7)
        recent_acts = get_recent_activities(user_id, limit=7)

        response = ai_coach.ask_coach(athlete, message.text, recent_health, recent_acts)
        bot.reply_to(message, response)


def start_telegram_polling():
    """Starts the bot polling loop."""
    if not bot:
        logger.warning("Telegram bot token not provided. Polling disabled.")
        return

    setup_bot_handlers()
    logger.info("Starting Telegram bot polling...")
    bot.infinity_polling()
