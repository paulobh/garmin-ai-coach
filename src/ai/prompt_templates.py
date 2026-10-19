"""
Garmin AI Coach - Prompt Engineering & Templates
Tailored for endurance, trail, racket sports, and strength training.
"""
from typing import Dict, List, Any


SYSTEM_PROMPT = """You are an elite Sports Physiologist and Adaptive Performance Coach.
Your mission is to analyze Garmin biometrics (Sleep stages, HRV status, Body Battery, Resting Heart Rate, and Workout data) to provide actionable, science-backed guidance.

Guiding Principles:
1. Be concise, sharp, and motivating — no generic fluff or filler.
2. Direct Correlation: Always connect the biometrics (e.g., REM sleep, HRV drop, training effect) to real physiological consequences (e.g., central nervous system fatigue, glycogen depletion, aerobic efficiency).
3. Sport-Specific Awareness:
   - Running & Cycling: Heart rate zones (Zone 2 aerobic vs Zone 4/5 threshold), aerobic decoupling, cadence, aerobic/anaerobic Training Effect.
   - Trail Running / Hiking: Elevation gain (D+), eccentric muscular fatigue on descents, pacing on gradients.
   - Tennis / Pickleball: Intermittent high-intensity sprints, rotational power, rapid direction changes, neuromuscular load.
   - Strength Training: Central Nervous System (CNS) load, rest between heavy compound sets, muscular hypertrophy vs fatigue.
4. Output cleanly in Markdown format with clear headings and bullet points.
5. Respect the requested language (e.g., pt-BR or en).
"""


def format_seconds(seconds: Any) -> str:
    if not seconds:
        return "N/A"
    try:
        hrs = int(seconds) // 3600
        mins = (int(seconds) % 3600) // 60
        return f"{hrs}h {mins}m"
    except Exception:
        return str(seconds)


def build_morning_prompt(athlete_profile: Dict[str, Any], today_health: Dict[str, Any], historical: List[Dict[str, Any]]) -> str:
    lang = athlete_profile.get("preferences", {}).get("language", "pt-BR")
    sports = ", ".join(athlete_profile.get("primary_sports", ["running", "cycling"]))
    name = athlete_profile.get("display_name", "Athlete")

    # Calculate 7-day averages if available
    avg_sleep_score = None
    if historical:
        valid_scores = [h["sleep_score"] for h in historical if h.get("sleep_score")]
        if valid_scores:
            avg_sleep_score = round(sum(valid_scores) / len(valid_scores), 1)

    prompt = f"""
Language requested: {lang}
Athlete: {name}
Primary Sports: {sports}

TODAY'S MORNING BIOMETRICS:
- Sleep Score: {today_health.get('sleep_score', 'N/A')}/100 (7-Day Average: {avg_sleep_score or 'N/A'})
- Total Sleep Time: {format_seconds(today_health.get('sleep_seconds'))}
  * Deep Sleep: {format_seconds(today_health.get('deep_seconds'))}
  * REM Sleep: {format_seconds(today_health.get('rem_seconds'))}
  * Light Sleep: {format_seconds(today_health.get('light_seconds'))}
  * Awake Time: {format_seconds(today_health.get('awake_seconds'))}
- Overnight HRV: {today_health.get('hrv_last_night', 'N/A')} ms (Status: {today_health.get('hrv_status', 'Unknown')}, 7-Day Baseline: {today_health.get('hrv_weekly_avg', 'N/A')} ms)
- Body Battery at Wake: {today_health.get('body_battery_wake', 'N/A')}/100
- Resting Heart Rate (RHR): {today_health.get('resting_hr', 'N/A')} bpm
- Stress Level (yesterday avg): {today_health.get('avg_stress', 'N/A')}/100
- Training Readiness: {today_health.get('training_readiness', 'N/A')}/100

TASK:
Provide a daily morning readiness assessment with:
1. 🚦 **Readiness Verdict**: [High Readiness / Moderate / Caution - Active Recovery Needed]
2. 🔬 **Physiological Breakdown**: 2-3 sentences explaining what the sleep stages + HRV balance indicate about their autonomic nervous system (sympathetic vs parasympathetic tone).
3. 🎯 **Training Recommendation**: Specific advice for today based on their sports ({sports}). If green, what intensity is ideal? If yellow/red, how should they modify their session?
4. ⚡ **Actionable Daily Recovery Tip**: One practical tip for nutrition, hydration, or stress control today.
"""
    return prompt.strip()


def build_activity_prompt(athlete_profile: Dict[str, Any], activity: Dict[str, Any], morning_health: Dict[str, Any]) -> str:
    lang = athlete_profile.get("preferences", {}).get("language", "pt-BR")
    name = athlete_profile.get("display_name", "Athlete")

    dist_km = round(activity.get("distance_meters", 0) / 1000.0, 2) if activity.get("distance_meters") else 0
    duration_str = format_seconds(activity.get("duration_seconds", 0))

    prompt = f"""
Language requested: {lang}
Athlete: {name}

COMPLETED WORKOUT DETAILS:
- Sport: {activity.get('sport_type', 'Workout')} ({activity.get('name', 'Activity')})
- Duration: {duration_str}
- Distance: {dist_km} km
- Average HR: {activity.get('avg_hr', 'N/A')} bpm (Max HR: {activity.get('max_hr', 'N/A')} bpm)
- Aerobic Training Effect (TE): {activity.get('aerobic_te', 'N/A')}/5.0
- Anaerobic Training Effect (TE): {activity.get('anaerobic_te', 'N/A')}/5.0
- Elevation Gain: {activity.get('elevation_gain_meters', 'N/A')} m
- Avg Cadence / Power: {activity.get('avg_cadence', 'N/A')} spm / {activity.get('avg_power', 'N/A')} W
- Calories: {activity.get('calories', 'N/A')} kcal

CONTEXT - MORNING STATE BEFORE THIS WORKOUT:
- Sleep Score: {morning_health.get('sleep_score', 'N/A')}/100
- Overnight HRV Status: {morning_health.get('hrv_status', 'Unknown')}
- Body Battery at Wake: {morning_health.get('body_battery_wake', 'N/A')}/100

TASK:
Provide a post-workout analysis with:
1. ⚡ **Session Impact**: Physiological interpretation of the workout intensity, considering how well-recovered the athlete entered the session.
2. 🎯 **Systems Stimulated**: Highlight the primary energy systems challenged (e.g. Mitochondrial base, Lactate threshold, Neuromuscular speed, Eccentric muscular stress on trails).
3. ⏱️ **Recovery & Nutrition Protocol**: Estimated recovery window before the next hard effort and post-workout nutritional priority (electrolytes, carbs, protein).
"""
    return prompt.strip()


def build_chat_prompt(athlete_profile: Dict[str, Any], user_question: str, recent_health: List[Dict[str, Any]], recent_activities: List[Dict[str, Any]]) -> str:
    lang = athlete_profile.get("preferences", {}).get("language", "pt-BR")
    name = athlete_profile.get("display_name", "Athlete")
    sports = ", ".join(athlete_profile.get("primary_sports", []))

    # Summarize last 5 activities
    act_summary = []
    for a in recent_activities[:5]:
        d = round(a.get("distance_meters", 0) / 1000.0, 1)
        act_summary.append(f"- {a.get('start_time', '')[:10]}: {a.get('sport_type')} '{a.get('name')}', {d}km, avg HR {a.get('avg_hr')} bpm, TE {a.get('aerobic_te')}/{a.get('anaerobic_te')}")
    act_str = "\n".join(act_summary) if act_summary else "No recent workouts recorded."

    # Summarize last 3 days of health
    health_summary = []
    for h in recent_health[:3]:
        health_summary.append(f"- {h.get('date')}: Sleep Score {h.get('sleep_score')}, HRV {h.get('hrv_last_night')}ms ({h.get('hrv_status')}), Body Battery Wake {h.get('body_battery_wake')}")
    health_str = "\n".join(health_summary) if health_summary else "No recent daily health data."

    prompt = f"""
Language requested: {lang}
Athlete: {name}
Primary Sports: {sports}

ATHLETE'S RECENT DATA:
Recent Sleep & HRV:
{health_str}

Recent Workouts:
{act_str}

USER QUESTION:
"{user_question}"

Answer as the athlete's personal coach with specific references to their real data where applicable.
"""
    return prompt.strip()
