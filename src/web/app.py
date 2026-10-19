"""
Garmin AI Coach - Streamlit Web Dashboard
Multi-athlete biometrics, interactive AI briefings, activity deep dives, trend visualization,
and comprehensive athlete configuration management.
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

from src.config import (
    load_users_config,
    upsert_user_config,
    delete_user_config,
    TOKENS_DIR,
    GEMINI_API_KEY,
    TELEGRAM_BOT_TOKEN,
)
from src.database.db import (
    init_db,
    get_daily_health,
    get_recent_daily_health,
    get_recent_activities,
    get_latest_insight,
)
from src.collectors.sync_worker import SyncWorker
from src.collectors.garmin_client import GarminCoachClient
from src.ai.gemini_client import GeminiCoach

st.set_page_config(
    page_title="Garmin AI Coach",
    page_icon="🏃‍♂️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Initialize database
init_db()

ALL_SPORTS = [
    "running",
    "cycling",
    "trail_running",
    "tennis",
    "pickleball",
    "strength_training",
    "swimming",
    "walking",
    "hiking",
    "rowing",
    "yoga",
    "pilates",
    "hiit",
]


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

app_mode = st.sidebar.radio(
    "Navigation Mode",
    ["📊 Athlete Dashboard", "⚙️ Manage Athletes"],
    label_visibility="collapsed",
)

users = load_users_config()

# =========================================================================
# VIEW 1: MANAGE ATHLETES (ADD / EDIT / 2FA AUTH)
# =========================================================================
if app_mode == "⚙️ Manage Athletes":
    st.title("⚙️ Athlete & Account Management")
    st.caption("Configure multi-athlete profiles, credentials, Telegram alerts, and test 2FA connections.")

    m_tab1, m_tab2, m_tab3, m_tab4 = st.tabs([
        "✏️ Edit Athletes",
        "➕ Add New Athlete",
        "🔐 Test Connection & 2FA",
        "📖 API Keys & Telegram Guide",
    ])

    # ---------------- TAB 1: EDIT ATHLETE ----------------
    with m_tab1:
        if not users:
            st.info("No athletes configured yet. Use the 'Add New Athlete' tab to create your first profile.")
        else:
            athlete_names = [u.get("display_name", u["id"]) for u in users]
            selected_edit_name = st.selectbox("Select Athlete to Edit:", athlete_names, key="edit_selector")
            athlete = next(u for u in users if u.get("display_name", u["id"]) == selected_edit_name)

            with st.form("edit_athlete_form"):
                st.subheader(f"Editing: {athlete.get('display_name')}")

                col_a, col_b = st.columns(2)
                with col_a:
                    new_display_name = st.text_input("Display Name", value=athlete.get("display_name", ""))
                    garmin_email = st.text_input("Garmin Email", value=athlete.get("garmin_email", ""))
                    garmin_password = st.text_input(
                        "Garmin Password",
                        value="",
                        type="password",
                        help="Leave blank to keep your currently saved password.",
                    )
                    telegram_chat_id = st.text_input(
                        "Telegram Chat ID",
                        value=str(athlete.get("telegram_chat_id", "") or ""),
                        help="Numerical ID from @userinfobot on Telegram for private alerts.",
                    )

                with col_b:
                    morning_time = st.text_input(
                        "Morning Report Time (24h)",
                        value=athlete.get("morning_report_time", "07:00"),
                        help="Time in HH:MM format when morning briefing should be sent.",
                    )
                    send_morning = st.checkbox("Send Morning Readiness Report", value=athlete.get("send_morning_report", True))
                    send_activity = st.checkbox("Send Post-Workout Analysis", value=athlete.get("send_activity_report", True))
                    lang = st.selectbox(
                        "Coach Language",
                        ["pt-BR", "en"],
                        index=0 if athlete.get("preferences", {}).get("language", "pt-BR") == "pt-BR" else 1,
                    )
                    style = st.selectbox(
                        "Coaching Style",
                        ["balanced", "analytical", "encouraging", "strict"],
                        index=["balanced", "analytical", "encouraging", "strict"].index(
                            athlete.get("preferences", {}).get("coaching_style", "balanced")
                        ),
                    )

                current_sports = athlete.get("primary_sports", ["running"])
                selected_sports = st.multiselect(
                    "Primary Sports & Disciplines",
                    options=ALL_SPORTS,
                    default=[s for s in current_sports if s in ALL_SPORTS],
                )

                submit_edit = st.form_submit_button("💾 Save Changes", type="primary")

                if submit_edit:
                    try:
                        chat_id_val = int(telegram_chat_id) if telegram_chat_id.strip() else None
                    except ValueError:
                        st.error("Telegram Chat ID must be a number.")
                        st.stop()

                    updated_user = {
                        "id": athlete["id"],
                        "display_name": new_display_name.strip() or athlete["id"],
                        "garmin_email": garmin_email.strip(),
                        "garmin_password": garmin_password.strip() if garmin_password.strip() else athlete.get("garmin_password", ""),
                        "telegram_chat_id": chat_id_val,
                        "morning_report_time": morning_time.strip(),
                        "send_morning_report": send_morning,
                        "send_activity_report": send_activity,
                        "primary_sports": selected_sports,
                        "preferences": {
                            "language": lang,
                            "coaching_style": style,
                            "unit_system": athlete.get("preferences", {}).get("unit_system", "metric"),
                        },
                    }

                    if upsert_user_config(updated_user):
                        st.success(f"Profile for '{new_display_name}' updated successfully in config/users.yaml!")
                        st.rerun()
                    else:
                        st.error("Failed to save changes to config/users.yaml.")

            # Danger zone: delete athlete
            st.divider()
            with st.expander("🗑️ Danger Zone: Remove Athlete"):
                st.warning(f"This will remove '{athlete.get('display_name')}' from configuration.")
                if st.button("Confirm Delete Athlete", type="secondary"):
                    if delete_user_config(athlete["id"]):
                        st.success(f"Athlete '{athlete.get('display_name')}' removed.")
                        st.rerun()

    # ---------------- TAB 2: ADD NEW ATHLETE ----------------
    with m_tab2:
        st.subheader("➕ Register a New Athlete Profile")
        with st.form("add_athlete_form"):
            col_1, col_2 = st.columns(2)
            with col_1:
                new_id = st.text_input("Athlete Slug ID (unique, lowercase)", placeholder="e.g. partner, runner2")
                new_name = st.text_input("Display Name", placeholder="e.g. Maria, John")
                new_email = st.text_input("Garmin Connect Email", placeholder="user@example.com")
                new_pwd = st.text_input("Garmin Password", type="password")
                new_chat = st.text_input("Telegram Chat ID (optional)", placeholder="e.g. 123456789")

            with col_2:
                new_morning = st.text_input("Morning Report Time", value="07:30")
                new_send_m = st.checkbox("Send Morning Readiness Report", value=True)
                new_send_a = st.checkbox("Send Post-Workout Analysis", value=True)
                new_lang = st.selectbox("Coach Language", ["pt-BR", "en"], index=0)
                new_style = st.selectbox("Coaching Style", ["balanced", "analytical", "encouraging", "strict"], index=0)

            new_sports = st.multiselect(
                "Primary Sports",
                options=ALL_SPORTS,
                default=["running", "strength_training"],
            )

            submit_add = st.form_submit_button("➕ Create Athlete Profile", type="primary")

            if submit_add:
                clean_id = new_id.strip().lower().replace(" ", "_")
                if not clean_id:
                    st.error("Please provide a valid unique Athlete Slug ID.")
                elif any(u.get("id") == clean_id for u in users):
                    st.error(f"Athlete ID '{clean_id}' already exists. Choose a different ID.")
                else:
                    try:
                        chat_val = int(new_chat) if new_chat.strip() else None
                    except ValueError:
                        st.error("Telegram Chat ID must be a number.")
                        st.stop()

                    new_user_dict = {
                        "id": clean_id,
                        "display_name": new_name.strip() or clean_id,
                        "garmin_email": new_email.strip(),
                        "garmin_password": new_pwd.strip(),
                        "telegram_chat_id": chat_val,
                        "morning_report_time": new_morning.strip(),
                        "send_morning_report": new_send_m,
                        "send_activity_report": new_send_a,
                        "primary_sports": new_sports,
                        "preferences": {
                            "language": new_lang,
                            "coaching_style": new_style,
                            "unit_system": "metric",
                        },
                    }

                    if upsert_user_config(new_user_dict):
                        st.success(f"Athlete '{new_name}' created successfully! Authenticate in the 'Test Connection & 2FA' tab.")
                        st.rerun()
                    else:
                        st.error("Error creating athlete profile.")

    # ---------------- TAB 3: TEST CONNECTION & 2FA ----------------
    with m_tab3:
        st.subheader("🔐 Verify Session & Handle 2FA / MFA")
        if not users:
            st.info("No athletes configured.")
        else:
            auth_athlete_names = [u.get("display_name", u["id"]) for u in users]
            auth_selected_name = st.selectbox("Select Athlete to Authenticate:", auth_athlete_names, key="auth_selector")
            auth_athlete = next(u for u in users if u.get("display_name", u["id"]) == auth_selected_name)
            u_id = auth_athlete["id"]

            token_file = TOKENS_DIR / u_id / "tokens.json"
            if token_file.exists():
                st.success(f"✅ Active cached OAuth session found on disk for `{u_id}` (`{token_file.name}`).")
            else:
                st.warning(f"⚪ No cached OAuth tokens found for `{u_id}`. Initial authentication required.")

            if st.button("🚀 Test Connection / Authenticate Now", key="test_auth_btn"):
                with st.spinner(f"Connecting to Garmin for {auth_athlete.get('display_name')}..."):
                    client = GarminCoachClient(
                        user_id=u_id,
                        email=auth_athlete.get("garmin_email", ""),
                        password=auth_athlete.get("garmin_password", ""),
                    )
                    success, status, mfa_context = client.login(prompt_mfa=False)

                    if success:
                        st.success("🎉 Successfully authenticated with Garmin Connect! Session tokens cached.")
                        try:
                            stats = client.get_daily_metrics()
                            st.json({
                                "Resting Heart Rate": stats.get("resting_hr"),
                                "Sleep Score": stats.get("sleep_score"),
                                "HRV Status": stats.get("hrv_status"),
                                "Body Battery (Wake)": stats.get("body_battery_wake"),
                            })
                        except Exception as e:
                            st.caption(f"Connected, but metric sample returned: {e}")
                    elif status == "needs_mfa":
                        st.session_state["mfa_in_progress"] = True
                        st.session_state["mfa_client"] = client
                        st.session_state["mfa_context"] = mfa_context
                        st.warning("⚠️ Garmin requires Multi-Factor Authentication (2FA). Enter the code below:")
                    else:
                        st.error(f"❌ Authentication failed: {status}. Check your email and password in 'Edit Athletes'.")

            # In-flight MFA input
            if st.session_state.get("mfa_in_progress") and st.session_state.get("mfa_client"):
                st.divider()
                st.subheader("🔑 Enter Garmin Verification Code")
                mfa_input = st.text_input("Enter 6-digit MFA Code (received via Email or SMS):", key="mfa_code_input")
                if st.button("Submit Verification Code", type="primary"):
                    if not mfa_input.strip():
                        st.error("Please enter the code.")
                    else:
                        with st.spinner("Verifying code with Garmin..."):
                            cli: GarminCoachClient = st.session_state["mfa_client"]
                            ctx = st.session_state["mfa_context"]
                            success, err = cli.resume_mfa(cli.client, ctx, mfa_input.strip())
                            if success:
                                st.success("🎉 Verification code accepted! OAuth tokens cached indefinitely.")
                                del st.session_state["mfa_in_progress"]
                                del st.session_state["mfa_client"]
                                del st.session_state["mfa_context"]
                                st.rerun()
                            else:
                                st.error(f"Verification failed: {err}")

    # ---------------- TAB 4: API KEYS & TELEGRAM GUIDE ----------------
    with m_tab4:
        st.subheader("📖 Configuration & API Keys Reference")

        with st.expander("🤖 1. Setting up Telegram Bot & Chat ID", expanded=True):
            st.markdown("""
            **Why Telegram?** Receive your **morning readiness briefings** at 7 AM and **post-workout recovery analysis** right after finishing a run or ride.

            1. **Create Bot Token:**
               - Open Telegram and message **[@BotFather](https://t.me/BotFather)**.
               - Send `/newbot`, give it a name and a username ending in `bot`.
               - Copy the API Token and place it in `.env`:
                 ```dotenv
                 TELEGRAM_BOT_TOKEN=123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ
                 ```
            2. **Get Your Personal Chat ID:**
               - Message **[@userinfobot](https://t.me/userinfobot)** on Telegram and press **Start**.
               - Copy the numerical ID (e.g. `8145384177`).
               - Paste it into the athlete's profile in the **✏️ Edit Athletes** tab above.
            3. **Start Conversation:**
               - Open your newly created bot in Telegram and send `/start` so it has permission to message you.
            """)

        with st.expander("🌟 2. Google Gemini API Key (Recommended & Free)", expanded=True):
            st.markdown("""
            **Why Gemini?** Generous free tier (up to 15 requests/min), sub-second inference speeds, and huge context windows.

            1. Visit **[Google AI Studio](https://aistudio.google.com/)**.
            2. Sign in with any Google account.
            3. Click **"Get API key"** in the sidebar $\\rightarrow$ **"Create API key in new project"**.
            4. Copy your key (`AIzaSy...`) and add it to `.env`:
               ```dotenv
               AI_PROVIDER=gemini
               GEMINI_API_KEY=AIzaSyD...your_key_here
               GEMINI_MODEL=gemini-2.5-flash
               ```
            """)

        with st.expander("⚡ 3. Alternative AI Providers (OpenAI, Groq, Ollama, OpenRouter)"):
            st.markdown("""
            You can also use other AI engines by setting `AI_PROVIDER=openai` in `.env`:

            * **OpenAI (ChatGPT):**
              ```dotenv
              AI_PROVIDER=openai
              OPENAI_API_KEY=sk-...your_key
              OPENAI_BASE_URL=https://api.openai.com/v1
              OPENAI_MODEL=gpt-4o-mini
              ```

            * **Groq Cloud (Free & Ultra Fast):**
              * Get a key at [Groq Console](https://console.groq.com/keys)
              ```dotenv
              AI_PROVIDER=openai
              OPENAI_API_KEY=gsk_...your_groq_key
              OPENAI_BASE_URL=https://api.groq.com/openai/v1
              OPENAI_MODEL=llama-3.3-70b-versatile
              ```

            * **Local Ollama (100% Offline & Private):**
              * Run `ollama run llama3.1` locally
              ```dotenv
              AI_PROVIDER=openai
              OPENAI_API_KEY=ollama
              OPENAI_BASE_URL=http://localhost:11434/v1
              OPENAI_MODEL=llama3.1
              ```
            """)



# =========================================================================
# VIEW 2: ATHLETE DASHBOARD
# =========================================================================
else:
    if not users:
        st.error("No athletes found! Please switch to '⚙️ Manage Athletes' in the sidebar to add a profile.")
        st.stop()

    # Multi-athlete switcher
    athlete_names = [u.get("display_name", u["id"]) for u in users]
    selected_name = st.sidebar.selectbox("👤 Active Athlete", athlete_names)
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
