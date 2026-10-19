"""
Garmin AI Coach - Google Gemini Client
Handles LLM calls with resilient model fallback and database persistence.
"""
import logging
from typing import Dict, List, Any, Optional
import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted, GoogleAPIError

from src.config import GEMINI_API_KEY, GEMINI_MODEL
from src.ai.prompt_templates import (
    SYSTEM_PROMPT,
    build_morning_prompt,
    build_activity_prompt,
    build_chat_prompt,
)
from src.database.db import save_insight, get_latest_insight

logger = logging.getLogger(__name__)

# Fallback models in case of rate limit (429) or quota errors
FALLBACK_MODELS = [GEMINI_MODEL, "gemini-2.5-flash", "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
CANDIDATE_MODELS = list(dict.fromkeys(FALLBACK_MODELS))


class GeminiCoach:
    def __init__(self, api_key: str = GEMINI_API_KEY):
        self.api_key = api_key
        if api_key:
            genai.configure(api_key=api_key)
        else:
            logger.warning("GEMINI_API_KEY not configured! AI insights will not generate.")

    def _call_model_with_fallback(self, prompt: str, system_instruction: str = SYSTEM_PROMPT) -> str:
        if not self.api_key:
            return "⚠️ Gemini API Key is missing. Please set GEMINI_API_KEY in your .env file."

        last_error = None
        for model_name in CANDIDATE_MODELS:
            try:
                logger.info(f"Generating insight using model: {model_name}")
                model = genai.GenerativeModel(
                    model_name=model_name,
                    system_instruction=system_instruction
                )
                response = model.generate_content(prompt)
                if response and response.text:
                    return response.text.strip()
            except ResourceExhausted as e:
                logger.warning(f"Rate limit / ResourceExhausted on {model_name}: {e}. Retrying with next model...")
                last_error = e
                continue
            except GoogleAPIError as e:
                logger.warning(f"Google API Error on {model_name}: {e}. Retrying with next model...")
                last_error = e
                continue
            except Exception as e:
                logger.error(f"Error calling {model_name}: {e}")
                last_error = e
                break

        return f"⚠️ Unable to generate AI insight at this time ({last_error}). Please try again later."

    def generate_morning_insight(self, athlete: Dict[str, Any], today_health: Dict[str, Any], historical: List[Dict[str, Any]], force_refresh: bool = False) -> str:
        user_id = athlete["id"]
        today_date = today_health.get("date")

        # Check if already generated today
        if not force_refresh and today_date:
            cached = get_latest_insight(user_id, "morning", today_date)
            if cached:
                logger.info(f"Returning cached morning insight for {user_id} on {today_date}")
                return cached["text"]

        prompt = build_morning_prompt(athlete, today_health, historical)
        text = self._call_model_with_fallback(prompt)

        # Save to database
        if text and not text.startswith("⚠️"):
            save_insight(user_id, "morning", today_date or "today", prompt, text)

        return text

    def generate_post_activity_insight(self, athlete: Dict[str, Any], activity: Dict[str, Any], morning_health: Dict[str, Any], force_refresh: bool = False) -> str:
        user_id = athlete["id"]
        act_id = str(activity.get("activity_id") or activity.get("activityId"))

        if not force_refresh and act_id:
            cached = get_latest_insight(user_id, "post_activity", act_id)
            if cached:
                logger.info(f"Returning cached post-activity insight for {user_id} activity {act_id}")
                return cached["text"]

        prompt = build_activity_prompt(athlete, activity, morning_health)
        text = self._call_model_with_fallback(prompt)

        if text and not text.startswith("⚠️"):
            save_insight(user_id, "post_activity", act_id, prompt, text)

        return text

    def ask_coach(self, athlete: Dict[str, Any], question: str, recent_health: List[Dict[str, Any]], recent_activities: List[Dict[str, Any]]) -> str:
        user_id = athlete["id"]
        prompt = build_chat_prompt(athlete, question, recent_health, recent_activities)
        text = self._call_model_with_fallback(prompt)

        if text and not text.startswith("⚠️"):
            save_insight(user_id, "chat", "chat_query", prompt, text)

        return text
