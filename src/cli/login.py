"""
Garmin AI Coach - CLI Authentication Tool
Use this script to perform interactive first-time login and handle MFA verification codes.
"""
import sys
import argparse
import getpass
import logging
from src.config import load_users_config, get_user_by_id
from src.collectors.garmin_client import GarminCoachClient

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s]: %(message)s")
logger = logging.getLogger("GarminLoginCLI")


def main():
    parser = argparse.ArgumentParser(description="Authenticate athlete account with Garmin Connect (supports 2FA/MFA)")
    parser.add_argument("--user", required=False, help="Athlete ID defined in config/users.yaml (e.g. athlete_1)")
    args = parser.parse_args()

    users = load_users_config()
    if not users:
        print("❌ No athletes found in config/users.yaml! Please create or edit config/users.yaml first.")
        sys.exit(1)

    selected_user = None
    if args.user:
        selected_user = get_user_by_id(args.user)
        if not selected_user:
            print(f"❌ User '{args.user}' not found in config/users.yaml.")
            sys.exit(1)
    else:
        print("\nAvailable athletes in configuration:")
        for idx, u in enumerate(users):
            print(f"  [{idx + 1}] {u.get('display_name')} (id: {u.get('id')}, email: {u.get('garmin_email')})")
        choice = input("\nSelect athlete number to authenticate: ").strip()
        try:
            selected_user = users[int(choice) - 1]
        except (ValueError, IndexError):
            print("❌ Invalid selection.")
            sys.exit(1)

    user_id = selected_user["id"]
    display_name = selected_user.get("display_name", user_id)
    email = selected_user.get("garmin_email")
    password = selected_user.get("garmin_password")

    print(f"\n==================================================")
    print(f"🔐 Authenticating Athlete: {display_name} ({user_id})")
    print(f"==================================================")

    if not email:
        email = input("Enter Garmin Email: ").strip()
    if not password:
        password = getpass.getpass("Enter Garmin Password: ").strip()

    client = GarminCoachClient(user_id=user_id, email=email, password=password)

    # Attempt login with interactive MFA prompt
    print(f"Connecting to Garmin servers...")
    success, status, mfa_context = client.login(prompt_mfa=True)

    if success:
        print(f"\n✅ SUCCESS! Authentication completed.")
        print(f"Tokens stored securely in: {client.tokenstore_path}")
        print("Future background syncs will run automatically without requesting password or MFA.")

        # Test metric retrieval
        try:
            print("\nTesting connection by fetching today's biometrics...")
            metrics = client.get_daily_metrics()
            print(f"📊 Resting Heart Rate: {metrics.get('resting_hr', 'N/A')} bpm")
            print(f"😴 Sleep Score: {metrics.get('sleep_score', 'N/A')}/100")
            print(f"❤️ HRV Status: {metrics.get('hrv_status', 'N/A')}")
            print(f"🔋 Body Battery (Wake): {metrics.get('body_battery_wake', 'N/A')}")
            print("\n🎉 Setup verified successfully for this athlete!\n")
        except Exception as e:
            print(f"⚠️ Authenticated, but test fetch returned: {e}")
    else:
        print(f"\n❌ Login failed with status: {status}")
        sys.exit(1)


if __name__ == "__main__":
    main()
