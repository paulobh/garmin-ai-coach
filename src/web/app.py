"""
Garmin AI Coach - Streamlit Web Dashboard
Multi-athlete biometrics, interactive AI briefings, activity deep dives, and trend visualization.
"""
import sys
from pathlib import Path
from datetime import date, timedelta
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.config import load_users_config, GEMINI_API_KEY, TELEGRAM_BOT_TOKEN
from src.database.db import (
    init_db,
    get_daily_health,
    get_recent_daily_health,
    get_recent_activities,
    get_latest_insight,
)
from src.collectors.sync_worker import SyncWorker
from src.ai.gemini_client import GeminiCoach

st.set_page_config(
    page_title="Garmin AI Coach",
    page_icon="🏃‍♂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database
init_db()


def format_duration(seconds):
    if not seconds:
        return "0m"
    hrs = int(seconds) // 3600
    mins = (int(seconds) % 3600) // 60
    if hrs > 0:
        return f"{hrs}h {mins}m"
    return f"{mins}m"


# ---------------- SIDEBAR ----------------
st.sidebar.title("🏃‍♂️ Garmin AI Coach")
st.sidebar.caption("Intelligent biometric & athletic performance analysis")

users = load_users_config()
if not users:
    st.error("No athletes found! Please configure `config/users.yaml`.")
    st.stop()

# Multi-athlete switcher
athlete_names = [u.get("display_name", u["id"]) for u in users]
selected_name = st.sidebar.selectbox("👤 Select Athlete", athlete_names)
selected_user = next(u for u in users if u.get("display_name", u["id"]) == selected_name)
user_id = selected_user["id"]

st.sidebar.divider()
st.sidebar.markdown(f"**Tracked Sports:**\n" + ", ".join([f"`{s}`" for s in selected_user.get("primary_sports", [])]))

# Manual sync trigger button
if st.sidebar.button("🔄 Sync with Garmin Now", use_container_width=True):
    with st.sidebar.status("Syncing biometrics and activities...", expanded=True) as status:
        try:
            worker = SyncWorker()
            worker.sync_user(selected_user)
            status.update(label="Sync Completed successfully!", state="complete", expanded=False)
            st.rerun()
        except Exception as e:
            status.update(label=f"Sync error: {e}", state="error")

st.sidebar.divider()
st.sidebar.markdown(
    f"**System Status:**\n"
    f"- AI Engine: {'🟢 Active' if GEMINI_API_KEY else '🔴 Key Missing'}\n"
    f"- Telegram: {'🟢 Linked' if selected_user.get('telegram_chat_id') else '⚪ Not configured'}"
)

# ---------------- DATA FETCHING ----------------
today_str = date.today().isoformat()
today_health = get_daily_health(user_id, today_str) or {}
recent_health = get_recent_daily_health(user_id, days=14)
recent_activities = get_recent_activities(user_id, limit=15)
ai_coach = GeminiCoach()

# ---------------- HEADER ----------------
st.title(f"Athlete Dashboard — {selected_name}")

tab1, tab2, tab3, tab4 = st.tabs([
    "🌅 Today's Readiness & Coach",
    "🏃‍♂️ Activities & Deep Dives",
    "📈 14-Day Biometric Trends",
    "💬 Ask Your Coach",
])


# ---------------- TAB 1: READINESS & COACH ----------------
with tab1:
    # KPI Metric Cards
    col1, col2, col3, col4 = st.columns(4)

    sleep_score = today_health.get("sleep_score")
    sleep_val = f"{sleep_score}/100" if sleep_score is not None else "No data"
    col1.metric("Sleep Score", sleep_val, help="Overall sleep quality calculated by Garmin")

    hrv_val = f"{today_health.get('hrv_last_night', '--')} ms"
    hrv_status = today_health.get("hrv_status", "Unknown")
    col2.metric("Overnight HRV", hrv_val, f"Status: {hrv_status}", help="Autonomic nervous system recovery balance")

    bb_wake = today_health.get("body_battery_wake")
    bb_val = f"{bb_wake}/100" if bb_wake is not None else "No data"
    col3.metric("Body Battery (Wake)", bb_val, help="Energy reserve level at morning wake")

    rhr = today_health.get("resting_hr")
    rhr_val = f"{rhr} bpm" if rhr is not None else "No data"
    col4.metric("Resting Heart Rate", rhr_val, help="Basal resting pulse")

    st.divider()

    # AI Morning Briefing Card
    st.subheader("📋 AI Coach Morning Readiness Briefing")

    cached_morning = get_latest_insight(user_id, "morning", today_str)

    c_left, c_right = st.columns([4, 1])
    with c_right:
        regenerate_btn = st.button("✨ Regenerate Insight", use_container_width=True)

    if regenerate_btn:
        with st.spinner("Analyzing recovery biometrics with Gemini..."):
            briefing = ai_coach.generate_morning_insight(selected_user, today_health, recent_health, force_refresh=True)
            st.rerun()
    elif cached_morning:
        st.markdown(cached_morning["text"])
    else:
        if today_health:
            if st.button("Generate Morning Readiness Briefing", type="primary"):
                with st.spinner("Synthesizing sleep and HRV metrics..."):
                    briefing = ai_coach.generate_morning_insight(selected_user, today_health, recent_health)
                    st.rerun()
        else:
            st.info("No daily health data available for today yet. Click 'Sync with Garmin Now' in the sidebar.")

    # Sleep Stages breakdown if data available
    if today_health.get("sleep_seconds"):
        st.divider()
        st.subheader("💤 Sleep Stages Breakdown")
        deep = today_health.get("deep_seconds") or 0
        rem = today_health.get("rem_seconds") or 0
        light = today_health.get("light_seconds") or 0
        awake = today_health.get("awake_seconds") or 0

        sleep_df = pd.DataFrame({
            "Stage": ["Deep Sleep", "REM Sleep", "Light Sleep", "Awake"],
            "Duration (min)": [round(deep/60), round(rem/60), round(light/60), round(awake/60)],
        })
        fig = px.pie(
            sleep_df,
            names="Stage",
            values="Duration (min)",
            color="Stage",
            color_discrete_map={
                "Deep Sleep": "#1E3A8A",
                "REM Sleep": "#3B82F6",
                "Light Sleep": "#93C5FD",
                "Awake": "#F87171"
            },
            hole=0.45,
        )
        fig.update_layout(margin=dict(t=10, b=10, l=10, r=10), height=300)
        st.plotly_chart(fig, use_container_width=True)


# ---------------- TAB 2: ACTIVITIES ----------------
with tab2:
    st.subheader("🏃 Recent Completed Workouts")
    if not recent_activities:
        st.info("No workouts found in database. Hit 'Sync with Garmin Now' to ingest your activities.")
    else:
        activity_options = [
            f"{a.get('start_time', '')[:10]} - {a.get('name', 'Activity')} ({a.get('sport_type')})"
            for a in recent_activities
        ]
        selected_act_idx = st.selectbox("Select Activity to Inspect:", range(len(activity_options)), format_func=lambda i: activity_options[i])
        act = recent_activities[selected_act_idx]

        # Activity summary tiles
        ac1, ac2, ac3, ac4, ac5 = st.columns(5)
        dist_km = round(act.get("distance_meters", 0) / 1000.0, 2)
        dur_str = format_duration(act.get("duration_seconds", 0))

        ac1.metric("Distance", f"{dist_km} km" if dist_km > 0 else "N/A")
        ac2.metric("Duration", dur_str)
        ac3.metric("Avg HR", f"{round(act.get('avg_hr', 0))} bpm" if act.get("avg_hr") else "N/A")
        ac4.metric("Aerobic TE", f"{act.get('aerobic_te', '--')}/5.0")
        ac5.metric("Anaerobic TE", f"{act.get('anaerobic_te', '--')}/5.0")

        # Elevation and sport metrics
        if act.get("elevation_gain_meters"):
            st.caption(f"⛰️ Elevation Gain: **{round(act.get('elevation_gain_meters'))} m**")

        st.divider()
        st.subheader("🔬 AI Post-Workout Breakdown")
        act_id = str(act.get("activity_id"))
        cached_act_insight = get_latest_insight(user_id, "post_activity", act_id)

        if cached_act_insight:
            st.markdown(cached_act_insight["text"])
        else:
            if st.button("Generate Post-Workout Analysis", type="primary"):
                with st.spinner("Analyzing cardiovascular strain and energy systems..."):
                    insight_text = ai_coach.generate_post_activity_insight(selected_user, act, today_health)
                    st.rerun()


# ---------------- TAB 3: TRENDS ----------------
with tab3:
    st.subheader("📈 14-Day Health & Recovery Trends")
    if len(recent_health) < 2:
        st.info("Need at least 2 days of biometrics to plot trends. Keep tracking daily!")
    else:
        df_health = pd.DataFrame(recent_health).sort_values("date")

        # Sleep & HRV chart
        fig_trend = go.Figure()
        fig_trend.add_trace(go.Scatter(
            x=df_health["date"], y=df_health["sleep_score"],
            name="Sleep Score", line=dict(color="#3B82F6", width=3)
        ))
        fig_trend.add_trace(go.Scatter(
            x=df_health["date"], y=df_health["hrv_last_night"],
            name="Overnight HRV (ms)", line=dict(color="#10B981", width=3, dash="dash")
        ))
        fig_trend.update_layout(
            title="Sleep Score vs Overnight HRV (Last 14 Days)",
            xaxis_title="Date",
            yaxis_title="Metric Value",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=380,
            template="plotly_dark",
        )
        st.plotly_chart(fig_trend, use_container_width=True)

        # Resting HR & Stress
        fig_stress = go.Figure()
        fig_stress.add_trace(go.Scatter(
            x=df_health["date"], y=df_health["resting_hr"],
            name="Resting HR (bpm)", line=dict(color="#EF4444", width=2)
        ))
        fig_stress.add_trace(go.Scatter(
            x=df_health["date"], y=df_health["avg_stress"],
            name="Avg Daily Stress", line=dict(color="#F59E0B", width=2)
        ))
        fig_stress.update_layout(
            title="Resting Heart Rate & Daily Stress Levels",
            xaxis_title="Date",
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
            height=320,
            template="plotly_dark",
        )
        st.plotly_chart(fig_stress, use_container_width=True)


# ---------------- TAB 4: ASK COACH ----------------
with tab4:
    st.subheader("💬 Chat with Your AI Performance Coach")
    st.caption("Ask questions about your fatigue, training load, pacing strategy, or next race preparation.")

    if "chat_history" not in st.session_state:
        st.session_state.chat_history = []

    # Display prior conversation turns
    for role, text in st.session_state.chat_history:
        with st.chat_message(role):
            st.markdown(text)

    prompt_input = st.chat_input("Ask a question (e.g., 'Given my HRV this week, should I do intervals today?')")
    if prompt_input:
        st.session_state.chat_history.append(("user", prompt_input))
        with st.chat_message("user"):
            st.markdown(prompt_input)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing your historical training and biometrics..."):
                response = ai_coach.ask_coach(selected_user, prompt_input, recent_health, recent_activities)
                st.markdown(response)
                st.session_state.chat_history.append(("assistant", response))
