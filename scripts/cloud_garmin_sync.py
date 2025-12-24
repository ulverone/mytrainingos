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
    """Main sync function with historical data support."""
    import garth
    from garminconnect import Garmin
    from datetime import timedelta
    
    # Configuration
    HISTORICAL_MONTHS = int(os.environ.get('HISTORICAL_MONTHS', '12'))
    
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
        
        # Setup data directory
        data_dir = Path("data/activities")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Check if we need historical sync
        existing_files = list(data_dir.glob("*.zip"))
        is_first_run = len(existing_files) < 10
        
        if is_first_run:
            print(f"\n📆 HISTORICAL SYNC: Downloading last {HISTORICAL_MONTHS} months...")
            send_telegram(f"📆 <b>Sync Storico Attivato</b>\n\nScaricando tutte le attività degli ultimi {HISTORICAL_MONTHS} mesi...\n\n⏱️ Questo potrebbe richiedere alcuni minuti.")
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=HISTORICAL_MONTHS * 30)
            
            # Fetch ALL activities in batches
            all_activities = []
            batch_size = 100
            start_idx = 0
            
            while True:
                print(f"   Fetching batch {start_idx//batch_size + 1}...")
                batch = client.get_activities(start_idx, batch_size)
                if not batch:
                    break
                
                all_activities.extend(batch)
                
                # Check if oldest activity is older than our target
                oldest = batch[-1]
                oldest_date_str = oldest.get("startTimeLocal", "")
                if oldest_date_str:
                    oldest_date = datetime.fromisoformat(oldest_date_str.replace("Z", ""))
                    if oldest_date < start_date:
                        print(f"   Reached {oldest_date.strftime('%Y-%m-%d')} - stopping")
                        break
                
                start_idx += batch_size
                time.sleep(0.5)  # Rate limiting
            
            # Filter to only activities within date range
            activities = []
            for act in all_activities:
                date_str = act.get("startTimeLocal", "")
                if date_str:
                    try:
                        act_date = datetime.fromisoformat(date_str.replace("Z", ""))
                        if act_date >= start_date:
                            activities.append(act)
                    except:
                        activities.append(act)
                else:
                    activities.append(act)
            
            print(f"📋 Found {len(activities)} activities in last {HISTORICAL_MONTHS} months")
        else:
            # Normal daily sync - just get recent
            print("📋 Daily sync: Fetching recent activities...")
            activities = client.get_activities(0, 30)
            print(f"   Found {len(activities)} recent activities")
        
        # Download activities
        downloaded = 0
        skipped = 0
        errors = 0
        
        for i, act in enumerate(activities):
            activity_id = act.get("activityId")
            if not activity_id:
                continue
            
            fit_path = data_dir / f"{activity_id}.zip"
            if fit_path.exists():
                skipped += 1
                continue
            
            activity_name = act.get("activityName", "Unknown")[:30]
            print(f"   📥 [{i+1}/{len(activities)}] {activity_name}...")
            
            try:
                zip_data = client.download_activity(
                    activity_id, 
                    dl_fmt=client.ActivityDownloadFormat.ORIGINAL
                )
                if zip_data:
                    with open(fit_path, "wb") as f:
                        f.write(zip_data)
                    downloaded += 1
                time.sleep(0.3)  # Rate limiting
            except Exception as e:
                print(f"   ⚠️ Error: {e}")
                errors += 1
        
        # Summary
        total_files = len(list(data_dir.glob("*.zip")))
        summary = f"""✅ <b>Garmin Sync Complete!</b>

📥 Scaricate: {downloaded} nuove attività
⏭️ Saltate: {skipped} (già presenti)
📁 Totale in archivio: {total_files} attività"""
        
        if errors > 0:
            summary += f"\n⚠️ Errori: {errors}"
        
        print(f"\n{summary.replace('<b>', '').replace('</b>', '')}")
        send_telegram(summary)
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
