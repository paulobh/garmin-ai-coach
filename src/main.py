"""
Garmin AI Coach - Unified Entrypoint
Runs Streamlit web dashboard, background sync scheduler, and Telegram bot concurrently.
"""
import os
import sys
import threading
import logging
import argparse
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.database.db import init_db
from src.collectors.sync_worker import SyncWorker
from src.bot.telegram_service import start_telegram_polling
from src.config import SYNC_INTERVAL_MINUTES, TELEGRAM_BOT_TOKEN

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("GarminAICoach")


def run_sync_scheduler():
    """Runs the sync cycle in a loop."""
    import time
    logger.info("Initializing Sync Scheduler thread...")
    worker = SyncWorker()
    # Run initial sync on startup
    try:
        logger.info("Executing startup sync...")
        worker.run_all()
    except Exception as e:
        logger.error(f"Startup sync encountered error: {e}")

    while True:
        time.sleep(SYNC_INTERVAL_MINUTES * 60)
        try:
            logger.info("Executing scheduled sync cycle...")
            worker.run_all()
        except Exception as e:
            logger.error(f"Scheduled sync encountered error: {e}")


def run_telegram_bot():
    """Starts Telegram bot polling if token is provided."""
    if not TELEGRAM_BOT_TOKEN:
        logger.info("TELEGRAM_BOT_TOKEN not provided. Telegram bot listener disabled.")
        return
    logger.info("Initializing Telegram bot listener thread...")
    try:
        start_telegram_polling()
    except Exception as e:
        logger.error(f"Telegram bot stopped with error: {e}")


def run_streamlit():
    """Runs the Streamlit dashboard."""
    import subprocess
    port = os.getenv("STREAMLIT_SERVER_PORT", "8502")
    address = os.getenv("STREAMLIT_SERVER_ADDRESS", "0.0.0.0")
    app_path = ROOT_DIR / "src" / "web" / "app.py"

    cmd = [
        sys.executable, "-m", "streamlit", "run",
        str(app_path),
        f"--server.port={port}",
        f"--server.address={address}",
        "--server.headless=true"
    ]
    logger.info(f"Starting Streamlit dashboard on {address}:{port}...")
    subprocess.run(cmd)


def main():
    parser = argparse.ArgumentParser(description="Garmin AI Coach Service Runner")
    parser.add_argument("--mode", choices=["all", "web", "worker", "bot"], default="all",
                        help="Run all services together or a specific component")
    args = parser.parse_args()

    init_db()

    if args.mode == "web":
        run_streamlit()
    elif args.mode == "worker":
        from src.collectors.sync_worker import main as worker_main
        worker_main()
    elif args.mode == "bot":
        start_telegram_polling()
    else:
        # Run unified: worker and bot in daemon threads, Streamlit in main thread
        worker_thread = threading.Thread(target=run_sync_scheduler, daemon=True, name="SyncWorkerThread")
        worker_thread.start()

        bot_thread = threading.Thread(target=run_telegram_bot, daemon=True, name="TelegramBotThread")
        bot_thread.start()

        # Run Streamlit in main thread to keep process alive and handle signals
        run_streamlit()


if __name__ == "__main__":
    main()
