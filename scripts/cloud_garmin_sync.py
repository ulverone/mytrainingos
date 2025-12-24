#!/usr/bin/env python3
"""
Cloud Garmin Sync with Telegram MFA
For use in GitHub Actions - sends MFA prompt via Telegram
"""

import os
import sys
import time
import json
import requests
from pathlib import Path
from datetime import datetime

# Telegram Config (from environment/secrets)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Garmin Config
GARMIN_EMAIL = os.environ.get('GARMIN_EMAIL')
GARMIN_PASSWORD = os.environ.get('GARMIN_PASSWORD')


def send_telegram(message):
    """Send a message via Telegram bot."""
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.ok
    except Exception as e:
        print(f"Telegram error: {e}")
        return False


def get_telegram_updates(offset=None):
    """Get recent messages from Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    params = {"timeout": 30}
    if offset:
        params["offset"] = offset
    
    try:
        response = requests.get(url, params=params, timeout=60)
        if response.ok:
            return response.json().get("result", [])
    except Exception as e:
        print(f"Error getting updates: {e}")
    return []


def wait_for_mfa_code(timeout=300):
    """
    Wait for MFA code via Telegram message.
    Polls for messages for up to `timeout` seconds.
    """
    print("⏳ Waiting for MFA code via Telegram...")
    send_telegram("🔐 <b>Garmin MFA Required</b>\n\nPer favore rispondi con il codice MFA inviato da Garmin.\n\n⏱️ Timeout: 5 minuti")
    
    start_time = time.time()
    last_update_id = None
    
    # Get current update_id to ignore old messages
    updates = get_telegram_updates()
    if updates:
        last_update_id = updates[-1]["update_id"] + 1
    
    while time.time() - start_time < timeout:
        updates = get_telegram_updates(offset=last_update_id)
        
        for update in updates:
            last_update_id = update["update_id"] + 1
            
            if "message" in update:
                text = update["message"].get("text", "").strip()
                # Check if it looks like an MFA code (usually 6 digits)
                if text.isdigit() and 4 <= len(text) <= 8:
                    print(f"✅ MFA code received: {text[:2]}****")
                    send_telegram(f"✅ Codice ricevuto! Procedo con il login...")
                    return text
        
        time.sleep(2)
    
    send_telegram("❌ Timeout! Nessun codice MFA ricevuto.")
    return None


def telegram_mfa_prompt():
    """
    Custom MFA handler for garth library.
    Called when Garmin requests MFA.
    """
    return wait_for_mfa_code()


def sync_garmin():
    """Main sync function."""
    import garth
    from garminconnect import Garmin
    
    print("🔄 Starting Garmin Sync...")
    print(f"📧 Email: {GARMIN_EMAIL}")
    
    # Clear any cached sessions
    garth_dir = os.path.expanduser("~/.garth")
    if os.path.exists(garth_dir):
        import shutil
        shutil.rmtree(garth_dir)
    
    try:
        # Try to login with custom MFA handler
        print("🔐 Logging in to Garmin Connect...")
        garth.login(GARMIN_EMAIL, GARMIN_PASSWORD, prompt_mfa=telegram_mfa_prompt)
        print("✅ Login successful!")
        
        # Save session for future use
        garth.save("~/.garth")
        
        # Create Garmin client
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.garth = garth.client
        
        # Get recent activities
        print("📋 Fetching activities...")
        activities = client.get_activities(0, 20)
        print(f"   Found {len(activities)} recent activities")
        
        # Download new activities
        data_dir = Path("data/activities")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded = 0
        for act in activities:
            activity_id = act.get("activityId")
            if not activity_id:
                continue
            
            fit_path = data_dir / f"{activity_id}.zip"
            if fit_path.exists():
                continue
            
            print(f"   📥 Downloading {activity_id}...")
            try:
                zip_data = client.download_activity(
                    activity_id, 
                    dl_fmt=client.ActivityDownloadFormat.ORIGINAL
                )
                if zip_data:
                    with open(fit_path, "wb") as f:
                        f.write(zip_data)
                    downloaded += 1
            except Exception as e:
                print(f"   ⚠️ Error: {e}")
        
        print(f"\n✅ Sync complete! Downloaded {downloaded} new activities.")
        send_telegram(f"✅ <b>Garmin Sync Complete!</b>\n\n📥 {downloaded} nuove attività scaricate")
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Sync failed: {error_msg}")
        send_telegram(f"❌ <b>Garmin Sync Failed</b>\n\n{error_msg}")
        return False


if __name__ == "__main__":
    if not all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, GARMIN_EMAIL, GARMIN_PASSWORD]):
        print("❌ Missing environment variables!")
        print("Required: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, GARMIN_EMAIL, GARMIN_PASSWORD")
        sys.exit(1)
    
    success = sync_garmin()
    sys.exit(0 if success else 1)
