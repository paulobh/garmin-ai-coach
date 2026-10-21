"""
Garmin AI Coach - SQLite Database Layer
"""
import sqlite3
import json
import logging
from typing import Dict, List, Any, Optional
from datetime import datetime, date
from src.config import DB_PATH

logger = logging.getLogger(__name__)


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initializes tables for multi-athlete biometrics and AI insights."""
    with get_connection() as conn:
        cursor = conn.cursor()

        # Athletes table
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS athletes (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                telegram_chat_id INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Daily health metrics (Sleep, HRV, Body Battery, Stress, Readiness)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS daily_health (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                date TEXT NOT NULL,
                sleep_score INTEGER,
                sleep_seconds INTEGER,
                deep_seconds INTEGER,
                rem_seconds INTEGER,
                light_seconds INTEGER,
                awake_seconds INTEGER,
                hrv_status TEXT,
                hrv_weekly_avg REAL,
                hrv_last_night REAL,
                body_battery_wake INTEGER,
                body_battery_max INTEGER,
                body_battery_min INTEGER,
                resting_hr INTEGER,
                avg_stress INTEGER,
                training_readiness INTEGER,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, date)
            )
        """)

        # Activities table (Workouts, Runs, Rides, etc.)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS activities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_id INTEGER NOT NULL UNIQUE,
                user_id TEXT NOT NULL,
                start_time TEXT NOT NULL,
                sport_type TEXT NOT NULL,
                name TEXT NOT NULL,
                duration_seconds REAL,
                distance_meters REAL,
                avg_hr REAL,
                max_hr REAL,
                aerobic_te REAL,
                anaerobic_te REAL,
                elevation_gain_meters REAL,
                avg_cadence REAL,
                avg_power REAL,
                calories REAL,
                raw_json TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # AI Insights log (Morning readiness, post-workout analysis, chat)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS ai_insights (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                insight_type TEXT NOT NULL, -- 'morning', 'post_activity', 'chat'
                ref_id TEXT,               -- date (YYYY-MM-DD) or activity_id
                prompt TEXT,
                text TEXT NOT NULL,
                language TEXT DEFAULT 'pt-BR',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        # Migration to add language column if it doesn't exist
        try:
            cursor.execute("ALTER TABLE ai_insights ADD COLUMN language TEXT DEFAULT 'pt-BR'")
        except sqlite3.OperationalError:
            pass

        conn.commit()
        logger.info(f"Database initialized at {DB_PATH}")


def upsert_athlete(user_id: str, display_name: str, telegram_chat_id: Optional[int] = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO athletes (id, display_name, telegram_chat_id)
            VALUES (?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                display_name = excluded.display_name,
                telegram_chat_id = COALESCE(excluded.telegram_chat_id, athletes.telegram_chat_id)
        """, (user_id, display_name, telegram_chat_id))
        conn.commit()


def upsert_daily_health(user_id: str, target_date: str, metrics: Dict[str, Any], raw_json: Optional[str] = None):
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO daily_health (
                user_id, date, sleep_score, sleep_seconds, deep_seconds,
                rem_seconds, light_seconds, awake_seconds, hrv_status,
                hrv_weekly_avg, hrv_last_night, body_battery_wake,
                body_battery_max, body_battery_min, resting_hr,
                avg_stress, training_readiness, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, date) DO UPDATE SET
                sleep_score = excluded.sleep_score,
                sleep_seconds = excluded.sleep_seconds,
                deep_seconds = excluded.deep_seconds,
                rem_seconds = excluded.rem_seconds,
                light_seconds = excluded.light_seconds,
                awake_seconds = excluded.awake_seconds,
                hrv_status = excluded.hrv_status,
                hrv_weekly_avg = excluded.hrv_weekly_avg,
                hrv_last_night = excluded.hrv_last_night,
                body_battery_wake = excluded.body_battery_wake,
                body_battery_max = excluded.body_battery_max,
                body_battery_min = excluded.body_battery_min,
                resting_hr = excluded.resting_hr,
                avg_stress = excluded.avg_stress,
                training_readiness = excluded.training_readiness,
                raw_json = COALESCE(excluded.raw_json, daily_health.raw_json)
        """, (
            user_id,
            target_date,
            metrics.get("sleep_score"),
            metrics.get("sleep_seconds"),
            metrics.get("deep_seconds"),
            metrics.get("rem_seconds"),
            metrics.get("light_seconds"),
            metrics.get("awake_seconds"),
            metrics.get("hrv_status"),
            metrics.get("hrv_weekly_avg"),
            metrics.get("hrv_last_night"),
            metrics.get("body_battery_wake"),
            metrics.get("body_battery_max"),
            metrics.get("body_battery_min"),
            metrics.get("resting_hr"),
            metrics.get("avg_stress"),
            metrics.get("training_readiness"),
            raw_json
        ))
        conn.commit()


def upsert_activity(user_id: str, activity_data: Dict[str, Any], raw_json: Optional[str] = None):
    activity_id = activity_data.get("activityId") or activity_data.get("activity_id")
    if not activity_id:
        return

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO activities (
                activity_id, user_id, start_time, sport_type, name,
                duration_seconds, distance_meters, avg_hr, max_hr,
                aerobic_te, anaerobic_te, elevation_gain_meters,
                avg_cadence, avg_power, calories, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(activity_id) DO UPDATE SET
                sport_type = excluded.sport_type,
                name = excluded.name,
                duration_seconds = excluded.duration_seconds,
                distance_meters = excluded.distance_meters,
                avg_hr = excluded.avg_hr,
                max_hr = excluded.max_hr,
                aerobic_te = excluded.aerobic_te,
                anaerobic_te = excluded.anaerobic_te,
                elevation_gain_meters = excluded.elevation_gain_meters,
                avg_cadence = excluded.avg_cadence,
                avg_power = excluded.avg_power,
                calories = excluded.calories,
                raw_json = COALESCE(excluded.raw_json, activities.raw_json)
        """, (
            activity_id,
            user_id,
            activity_data.get("startTimeLocal") or activity_data.get("start_time"),
            activity_data.get("activityType", {}).get("typeKey") or activity_data.get("sport_type", "other"),
            activity_data.get("activityName") or activity_data.get("name", "Activity"),
            activity_data.get("duration") or activity_data.get("duration_seconds", 0),
            activity_data.get("distance") or activity_data.get("distance_meters", 0),
            activity_data.get("averageHR") or activity_data.get("avg_hr"),
            activity_data.get("maxHR") or activity_data.get("max_hr"),
            activity_data.get("aerobicTrainingEffect") or activity_data.get("aerobic_te"),
            activity_data.get("anaerobicTrainingEffect") or activity_data.get("anaerobic_te"),
            activity_data.get("elevationGain") or activity_data.get("elevation_gain_meters"),
            activity_data.get("averageRunningCadenceInStepsPerMinute") or activity_data.get("avg_cadence"),
            activity_data.get("avgPower") or activity_data.get("avg_power"),
            activity_data.get("calories"),
            raw_json
        ))
        conn.commit()


def get_daily_health(user_id: str, target_date: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM daily_health WHERE user_id = ? AND date = ?", (user_id, target_date))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_recent_daily_health(user_id: str, days: int = 14) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM daily_health
            WHERE user_id = ?
            ORDER BY date DESC
            LIMIT ?
        """, (user_id, days))
        return [dict(r) for r in cursor.fetchall()]


def get_recent_activities(user_id: str, limit: int = 10) -> List[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM activities
            WHERE user_id = ?
            ORDER BY start_time DESC
            LIMIT ?
        """, (user_id, limit))
        return [dict(r) for r in cursor.fetchall()]


def get_activity_by_id(activity_id: int) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM activities WHERE activity_id = ?", (activity_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def save_insight(user_id: str, insight_type: str, ref_id: str, prompt: str, text: str, language: str = "pt-BR") -> int:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO ai_insights (user_id, insight_type, ref_id, prompt, text, language)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user_id, insight_type, str(ref_id), prompt, text, language))
        conn.commit()
        return cursor.lastrowid


def get_latest_insight(user_id: str, insight_type: str, ref_id: Optional[str] = None, language: Optional[str] = None) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        if language and ref_id:
            cursor.execute("""
                SELECT * FROM ai_insights
                WHERE user_id = ? AND insight_type = ? AND ref_id = ? AND language = ?
                ORDER BY created_at DESC LIMIT 1
            """, (user_id, insight_type, str(ref_id), language))
            row = cursor.fetchone()
            if row:
                return dict(row)

        if ref_id:
            cursor.execute("""
                SELECT * FROM ai_insights
                WHERE user_id = ? AND insight_type = ? AND ref_id = ?
                ORDER BY created_at DESC LIMIT 1
            """, (user_id, insight_type, str(ref_id)))
        else:
            cursor.execute("""
                SELECT * FROM ai_insights
                WHERE user_id = ? AND insight_type = ?
                ORDER BY created_at DESC LIMIT 1
            """, (user_id, insight_type))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_insight_by_language(user_id: str, insight_type: str, ref_id: str, language: str) -> Optional[Dict[str, Any]]:
    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM ai_insights
            WHERE user_id = ? AND insight_type = ? AND ref_id = ? AND language = ?
            ORDER BY created_at DESC LIMIT 1
        """, (user_id, insight_type, str(ref_id), language))
        row = cursor.fetchone()
        return dict(row) if row else None

