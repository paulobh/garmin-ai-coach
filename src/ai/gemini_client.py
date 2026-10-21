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
FALLBACK_MODELS = [GEMINI_MODEL, "gemini-3.8-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.1-flash-lite"]
CANDIDATE_MODELS = list(dict.fromkeys(FALLBACK_MODELS))


import requests
from src.config import (
    AI_PROVIDER,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    OPENAI_API_KEY,
    OPENAI_BASE_URL,
    OPENAI_MODEL,
)

class GeminiCoach:
    def __init__(self, api_key: str = GEMINI_API_KEY):
        self.provider = AI_PROVIDER
        self.api_key = api_key
        self.openai_api_key = OPENAI_API_KEY
        self.openai_base_url = OPENAI_BASE_URL
        self.openai_model = OPENAI_MODEL

        if self.provider == "gemini":
            if api_key:
                genai.configure(api_key=api_key)
            else:
                logger.warning("GEMINI_API_KEY not configured! AI insights will not generate.")
        else:
            logger.info(f"Using OpenAI-compatible provider at {self.openai_base_url} with model {self.openai_model}")

    def _call_openai_compatible(self, prompt: str, system_instruction: str = SYSTEM_PROMPT) -> str:
        url = f"{self.openai_base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.openai_api_key:
            headers["Authorization"] = f"Bearer {self.openai_api_key}"

        payload = {
            "model": self.openai_model,
            "messages": [
                {"role": "system", "content": system_instruction},
                {"role": "user", "content": prompt}
            ],
            "temperature": 0.7
        }
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=60)
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"].strip()
        except Exception as e:
            logger.error(f"Error calling OpenAI-compatible provider at {url}: {e}")
            return f"⚠️ Error calling AI provider ({e})."

    def _call_model_with_fallback(self, prompt: str, system_instruction: str = SYSTEM_PROMPT) -> str:
        if self.provider != "gemini":
            return self._call_openai_compatible(prompt, system_instruction)

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
        today_date = today_health.get("date") or "today"
        lang = athlete.get("preferences", {}).get("language", "pt-BR")

        # Check if already generated today in this specific language
        if not force_refresh and today_date:
            cached = get_latest_insight(user_id, "morning", today_date, language=lang)
            if cached:
                logger.info(f"Returning cached morning insight for {user_id} on {today_date} ({lang})")
                return cached["text"]

        prompt = build_morning_prompt(athlete, today_health, historical)
        text = self._call_model_with_fallback(prompt)

        # Save to database
        if text and not text.startswith("⚠️"):
            save_insight(user_id, "morning", today_date, prompt, text, language=lang)

        return text

    def generate_post_activity_insight(self, athlete: Dict[str, Any], activity: Dict[str, Any], morning_health: Dict[str, Any], force_refresh: bool = False) -> str:
        user_id = athlete["id"]
        act_id = str(activity.get("activity_id") or activity.get("activityId"))
        lang = athlete.get("preferences", {}).get("language", "pt-BR")

        if not force_refresh and act_id:
            cached = get_latest_insight(user_id, "post_activity", act_id, language=lang)
            if cached:
                logger.info(f"Returning cached post-activity insight for {user_id} activity {act_id} ({lang})")
                return cached["text"]

        prompt = build_activity_prompt(athlete, activity, morning_health)
        text = self._call_model_with_fallback(prompt)

        if text and not text.startswith("⚠️"):
            save_insight(user_id, "post_activity", act_id, prompt, text, language=lang)

        return text

    def translate_and_save_insight(self, user_id: str, insight_type: str, ref_id: str, source_text: str, target_lang: str) -> str:
        """Translates an existing insight to target_lang and caches it in SQLite."""
        target_name = "English" if str(target_lang).startswith("en") else "Portuguese (pt-BR)"
        prompt = f"""
Translate the following sports physiology and athletic coaching insight into fluent, natural {target_name}.
CRITICAL INSTRUCTIONS:
- Preserve all Markdown formatting (headings, bullet points, numbered lists, bold text).
- Keep all emojis and exact metric values (e.g., HRV in ms, Sleep Score, km, pace, HR bpm, kcal).
- Keep sports science terminology accurate (e.g. Zone 2, Aerobic Decoupling, HRV Balance, Glycogen, Autonomic Nervous System).

TEXT TO TRANSLATE:
{source_text}
"""
        translated = self._call_model_with_fallback(prompt, system_instruction="You are an expert bilingual sports physiologist and translator.")
        if translated and not translated.startswith("⚠️"):
            save_insight(user_id, insight_type, ref_id, f"Auto-translate to {target_lang}", translated, language=target_lang)
        return translated

    def ask_coach(self, athlete: Dict[str, Any], question: str, recent_health: List[Dict[str, Any]], recent_activities: List[Dict[str, Any]]) -> str:
        user_id = athlete["id"]
        lang = athlete.get("preferences", {}).get("language", "pt-BR")
        prompt = build_chat_prompt(athlete, question, recent_health, recent_activities)
        text = self._call_model_with_fallback(prompt)

        if text and not text.startswith("⚠️"):
            save_insight(user_id, "chat", "chat_query", prompt, text, language=lang)

        return text
