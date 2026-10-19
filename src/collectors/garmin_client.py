"""
Garmin AI Coach - Garmin Connect API Client
Handles multi-account authentication, OAuth token caching, MFA, and metric retrieval.
"""
import os
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
from datetime import date, datetime
from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectTooManyRequestsError,
    GarminConnectConnectionError,
)
from src.config import TOKENS_DIR

logger = logging.getLogger(__name__)


class GarminCoachClient:
    """Wrapper around Garmin Connect API for a specific athlete."""

    def __init__(self, user_id: str, email: str = "", password: str = ""):
        self.user_id = user_id
        self.email = email
        self.password = password
        self.tokenstore_dir = TOKENS_DIR / user_id
        self.tokenstore_dir.mkdir(parents=True, exist_ok=True)
        self.tokenstore_path = self.tokenstore_dir / "tokens.json"
        self.client: Optional[Garmin] = None

    def login(self, prompt_mfa: bool = False, mfa_code: Optional[str] = None) -> Tuple[bool, Optional[str], Optional[Any]]:
        """
        Attempts to authenticate using stored tokens, falling back to credentials.
        Returns: (success: bool, status: str, mfa_context: Any)
        """
        # 1. Try loading cached session
        if self.tokenstore_path.exists():
            try:
                logger.info(f"[{self.user_id}] Loading cached Garmin session from {self.tokenstore_path}")
                client = Garmin()
                client.login(str(self.tokenstore_path))
                self.client = client
                logger.info(f"[{self.user_id}] Successfully authenticated via cached session tokens!")
                return True, "authenticated_cached", None
            except Exception as e:
                logger.warning(f"[{self.user_id}] Cached session expired or invalid: {e}. Attempting fresh login.")

        # 2. Fresh login with credentials
        if not self.email or not self.password:
            return False, "missing_credentials", None

        try:
            client = Garmin(email=self.email, password=self.password, return_on_mfa=True)
            auth_response, mfa_context = client.login()

            if auth_response == "needs_mfa":
                if mfa_code:
                    logger.info(f"[{self.user_id}] Resuming login with provided MFA code...")
                    client.resume_login(mfa_context, mfa_code)
                elif prompt_mfa:
                    code = input(f"[{self.user_id}] Enter the Garmin MFA code sent to your email/SMS: ").strip()
                    client.resume_login(mfa_context, code)
                else:
                    logger.warning(f"[{self.user_id}] Account requires MFA verification.")
                    return False, "needs_mfa", mfa_context

            # Save session tokens for future runs
            self._save_session_tokens(client)
            self.client = client
            logger.info(f"[{self.user_id}] Fresh login successful! Session tokens cached.")
            return True, "authenticated_fresh", None

        except GarminConnectTooManyRequestsError as e:
            logger.error(f"[{self.user_id}] Garmin rate limit reached: {e}")
            return False, "rate_limited", None
        except GarminConnectAuthenticationError as e:
            logger.error(f"[{self.user_id}] Authentication failed (check credentials): {e}")
            return False, "auth_error", None
        except Exception as e:
            logger.error(f"[{self.user_id}] Unexpected error during Garmin login: {e}")
            return False, f"error: {str(e)}", None

    def _save_session_tokens(self, client: Garmin):
        """Dumps tokens to disk safely."""
        try:
            if hasattr(client, "client") and hasattr(client.client, "dump"):
                client.client.dump(str(self.tokenstore_path))
            elif hasattr(client, "dump"):
                client.dump(str(self.tokenstore_path))
            logger.info(f"[{self.user_id}] Saved session tokens to {self.tokenstore_path}")
        except Exception as e:
            logger.error(f"[{self.user_id}] Failed to dump session tokens: {e}")

    def is_authenticated(self) -> bool:
        return self.client is not None

    def get_daily_metrics(self, target_date: Optional[str] = None) -> Dict[str, Any]:
        """
        Fetches combined health and wellness metrics for a given date (YYYY-MM-DD).
        """
        if not self.is_authenticated():
            raise RuntimeError(f"Client for {self.user_id} is not authenticated.")

        if not target_date:
            target_date = date.today().isoformat()

        metrics: Dict[str, Any] = {
            "date": target_date,
            "sleep_score": None,
            "sleep_seconds": None,
            "deep_seconds": None,
            "rem_seconds": None,
            "light_seconds": None,
            "awake_seconds": None,
            "hrv_status": "Unknown",
            "hrv_weekly_avg": None,
            "hrv_last_night": None,
            "body_battery_wake": None,
            "body_battery_max": None,
            "body_battery_min": None,
            "resting_hr": None,
            "avg_stress": None,
            "training_readiness": None,
        }

        # 1. Daily User Summary (RHR, Stress, Steps)
        try:
            summary = self.client.get_user_summary(target_date)
            if summary:
                metrics["resting_hr"] = summary.get("restingHeartRate")
                metrics["avg_stress"] = summary.get("averageStressLevel")
                metrics["body_battery_max"] = summary.get("maxStressLevel") # or body battery from summary
        except Exception as e:
            logger.debug(f"[{self.user_id}] User summary unavailable for {target_date}: {e}")

        # 2. Sleep Data
        try:
            sleep_data = self.client.get_sleep_data(target_date)
            daily_sleep = sleep_data.get("dailySleepDTO", {}) if sleep_data else {}
            if daily_sleep:
                metrics["sleep_score"] = daily_sleep.get("sleepScores", {}).get("overall", {}).get("value")
                metrics["sleep_seconds"] = daily_sleep.get("sleepTimeSeconds")
                metrics["deep_seconds"] = daily_sleep.get("deepSleepSeconds")
                metrics["rem_seconds"] = daily_sleep.get("remSleepSeconds")
                metrics["light_seconds"] = daily_sleep.get("lightSleepSeconds")
                metrics["awake_seconds"] = daily_sleep.get("awakeSleepSeconds")
        except Exception as e:
            logger.debug(f"[{self.user_id}] Sleep data unavailable for {target_date}: {e}")

        # 3. HRV Data
        try:
            hrv_data = self.client.get_hrv_data(target_date)
            if hrv_data and "hrvSummary" in hrv_data:
                hrv_summary = hrv_data["hrvSummary"]
                metrics["hrv_status"] = hrv_summary.get("status", "Unknown")
                metrics["hrv_weekly_avg"] = hrv_summary.get("weeklyAvg")
                metrics["hrv_last_night"] = hrv_summary.get("lastNightAvg")
        except Exception as e:
            logger.debug(f"[{self.user_id}] HRV data unavailable for {target_date}: {e}")

        # 4. Body Battery
        try:
            bb_data = self.client.get_body_battery(target_date, target_date)
            if bb_data and isinstance(bb_data, list) and len(bb_data) > 0:
                day_bb = bb_data[0]
                metrics["body_battery_max"] = day_bb.get("charged")
                metrics["body_battery_min"] = day_bb.get("drained")
                # Wake value if body battery timeline has morning reading
                values = day_bb.get("bodyBatteryValuesArray", [])
                if values and len(values) > 0:
                    metrics["body_battery_wake"] = values[0][1]
        except Exception as e:
            logger.debug(f"[{self.user_id}] Body Battery data unavailable for {target_date}: {e}")

        # 5. Training Readiness (if supported by watch)
        try:
            if hasattr(self.client, "get_training_readiness"):
                readiness = self.client.get_training_readiness(target_date)
                if readiness and isinstance(readiness, dict):
                    metrics["training_readiness"] = readiness.get("score")
        except Exception as e:
            logger.debug(f"[{self.user_id}] Training readiness unavailable for {target_date}: {e}")

        return metrics

    def get_recent_activities(self, limit: int = 15) -> List[Dict[str, Any]]:
        """Fetches recent activities from Garmin Connect."""
        if not self.is_authenticated():
            raise RuntimeError(f"Client for {self.user_id} is not authenticated.")

        try:
            activities = self.client.get_activities(0, limit)
            return activities or []
        except Exception as e:
            logger.error(f"[{self.user_id}] Failed to fetch recent activities: {e}")
            return []
