"""
Garmin AI Coach - Multi-User Background Sync Worker
Periodically ingests health metrics & activities, detects new workouts, and sends proactive AI pushes.
"""
import time
import logging
import argparse
from datetime import datetime, date, timedelta
from typing import Dict, Any

from src.config import load_users_config, SYNC_INTERVAL_MINUTES
from src.database.db import (
    init_db,
    upsert_athlete,
    upsert_daily_health,
    upsert_activity,
    get_daily_health,
    get_recent_daily_health,
    get_recent_activities,
    get_latest_insight,
)
from src.collectors.garmin_client import GarminCoachClient
from src.ai.gemini_client import GeminiCoach
from src.bot.telegram_service import send_notification

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def is_recent_activity(act: Dict[str, Any], max_hours: int = 6) -> bool:
    """Checks if an activity occurred recently (within max_hours) to prevent alerting on old historical workouts."""
    start_str = act.get("startTimeLocal") or act.get("start_time") or ""
    if not start_str:
        return False
    try:
        clean_str = start_str.replace("Z", "").split(".")[0]
        if "T" in clean_str:
            act_dt = datetime.fromisoformat(clean_str)
        else:
            act_dt = datetime.strptime(clean_str, "%Y-%m-%d %H:%M:%S")
        return (datetime.now() - act_dt) <= timedelta(hours=max_hours)
    except Exception:
        return start_str[:10] == date.today().isoformat()



class SyncWorker:
    def __init__(self):
        init_db()
        self.ai = GeminiCoach()

    def sync_user(self, user: Dict[str, Any]):
        user_id = user["id"]
        display_name = user.get("display_name", user_id)
        chat_id = user.get("telegram_chat_id")
        email = user.get("garmin_email", "")
        password = user.get("garmin_password", "")

        logger.info(f"--- Starting sync for athlete: {display_name} ({user_id}) ---")
        upsert_athlete(user_id, display_name, chat_id)

        client = GarminCoachClient(user_id, email, password)
        success, status, _ = client.login()

        if not success:
            logger.warning(f"Could not authenticate athlete {user_id} (Status: {status}). Run `python -m src.cli.login --user {user_id}`")
            return

        today_str = date.today().isoformat()

        # 1. Sync Today's Health Metrics (Sleep, HRV, Body Battery, RHR)
        try:
            logger.info(f"Fetching daily biometrics for {today_str}...")
            daily_metrics = client.get_daily_metrics(today_str)
            upsert_daily_health(user_id, today_str, daily_metrics)
            logger.info(f"Successfully saved daily biometrics for {user_id}.")
        except Exception as e:
            logger.error(f"Error syncing daily metrics for {user_id}: {e}")
            daily_metrics = {}

        # Check if athlete has any recorded activities in DB (to prevent backfill alert storms)
        existing_recorded_acts = get_recent_activities(user_id, limit=1)
        is_first_sync = len(existing_recorded_acts) == 0

        # 2. Sync Recent Activities
        newly_synced_activities = []
        try:
            logger.info(f"Fetching recent activities for {user_id}...")
            activities = client.get_recent_activities(limit=10)
            for act in activities:
                act_id = act.get("activityId")
                existing_insight = get_latest_insight(user_id, "post_activity", str(act_id))
                upsert_activity(user_id, act)

                # Only queue for proactive Telegram alert if:
                # 1. Not an initial backfill sync
                # 2. No insight was already generated
                # 3. The activity actually occurred recently (within the last 6 hours)!
                if not is_first_sync and not existing_insight and is_recent_activity(act, max_hours=6):
                    newly_synced_activities.append(act)

            logger.info(f"Synced {len(activities)} activities for {user_id} ({len(newly_synced_activities)} recent workouts alerting).")
        except Exception as e:
            logger.error(f"Error syncing activities for {user_id}: {e}")

        # 3. Morning Report Trigger
        if user.get("send_morning_report", True) and chat_id:
            morning_report_time = user.get("morning_report_time", "07:00")
            current_time_str = datetime.now().strftime("%H:%M")

            existing_morning = get_latest_insight(user_id, "morning", today_str)
            if not existing_morning and current_time_str >= morning_report_time:
                # Validate that the user actually wore their watch and Garmin captured real sleep/HRV data
                has_sleep = bool(daily_metrics.get("sleep_score") or (daily_metrics.get("sleep_seconds") and daily_metrics.get("sleep_seconds") > 1800))
                has_hrv = bool(daily_metrics.get("hrv_last_night") or daily_metrics.get("hrv_status"))

                if not (has_sleep or has_hrv):
                    logger.info(f"Skipping morning briefing for {display_name}: No sleep or HRV recorded for {today_str} (watch was not worn).")
                else:
                    logger.info(f"Generating morning briefing for {display_name}...")
                    historical = get_recent_daily_health(user_id, days=14)
                    briefing = self.ai.generate_morning_insight(user, daily_metrics, historical)
                    msg = f"🌅 *Good Morning, {display_name}! Here is your Daily Readiness Briefing:*\n\n{briefing}"
                    send_notification(chat_id, msg)
                    logger.info(f"Morning briefing delivered to Telegram chat {chat_id}.")

        # 4. Post-Activity Report Trigger
        if user.get("send_activity_report", True) and chat_id:
            for act in newly_synced_activities:
                act_name = act.get("activityName", "Workout")
                act_sport = act.get("activityType", {}).get("typeKey", "activity")
                logger.info(f"Generating post-workout analysis for activity: {act_name} ({act_sport})...")
                analysis = self.ai.generate_post_activity_insight(user, act, daily_metrics)
                msg = f"🏃‍♂️ *Workout Complete: {act_name} ({act_sport})*\n\n{analysis}"
                send_notification(chat_id, msg)
                logger.info(f"Post-workout analysis delivered to Telegram chat {chat_id}.")

    def run_all(self):
        users = load_users_config()
        if not users:
            logger.warning("No users found in config/users.yaml. Please configure athletes.")
            return

        for u in users:
            try:
                self.sync_user(u)
            except Exception as e:
                logger.error(f"Unhandled error syncing user {u.get('id')}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Garmin AI Coach Ingestion Worker")
    parser.add_argument("--once", action="store_true", help="Run sync once and exit")
    args = parser.parse_args()

    worker = SyncWorker()

    if args.once:
        logger.info("Running single sync cycle...")
        worker.run_all()
        logger.info("Single sync cycle completed.")
    else:
        logger.info(f"Starting continuous sync daemon (interval: {SYNC_INTERVAL_MINUTES} minutes)...")
        while True:
            worker.run_all()
            logger.info(f"Sleeping for {SYNC_INTERVAL_MINUTES} minutes...")
            time.sleep(SYNC_INTERVAL_MINUTES * 60)


if __name__ == "__main__":
    main()
