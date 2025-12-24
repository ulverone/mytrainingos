#!/usr/bin/env python3
"""
Test Download FIT Files with Telegram MFA
"""
import os
import sys
import time
import shutil
import requests
from pathlib import Path

# Telegram config
TELEGRAM_TOKEN = '8541924986:AAGVulVnP9J30F-ttqespS4q0vsukjH1mTI'
TELEGRAM_CHAT_ID = '135519413'

def send_telegram(message):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        requests.post(url, json=data, timeout=10)
    except:
        pass

def get_telegram_updates(offset=None):
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates'
    params = {'timeout': 30}
    if offset:
        params['offset'] = offset
    try:
        response = requests.get(url, params=params, timeout=60)
        if response.ok:
            return response.json().get('result', [])
    except:
        pass
    return []

def wait_for_mfa_code(timeout=300):
    print("⏳ Waiting for MFA code via Telegram...")
    send_telegram("🔐 <b>Garmin MFA Required</b>\n\nRispondi con il codice MFA.\n⏱️ Timeout: 5 minuti")
    
    start_time = time.time()
    updates = get_telegram_updates()
    last_update_id = updates[-1]['update_id'] + 1 if updates else None
    
    while time.time() - start_time < timeout:
        updates = get_telegram_updates(offset=last_update_id)
        for update in updates:
            last_update_id = update['update_id'] + 1
            if 'message' in update:
                text = update['message'].get('text', '').strip()
                if text.isdigit() and 4 <= len(text) <= 8:
                    print(f"✅ MFA code received!")
                    send_telegram(f"✅ Codice ricevuto!")
                    return text
        time.sleep(2)
    
    send_telegram("❌ Timeout!")
    return None

def main():
    sys.path.insert(0, '/Users/marco/.gemini/antigravity/scratch/garmin_analyzer')
    
    import garth
    from garminconnect import Garmin
    from keychain_auth import get_credentials
    
    print("=" * 50)
    print("📥 TEST DOWNLOAD FIT FILES")
    print("=" * 50)
    
    # Clear cache
    for p in [os.path.expanduser("~/.garth"), os.path.expanduser("~/.cache/garth")]:
        if os.path.exists(p):
            shutil.rmtree(p)
    
    email, password = get_credentials()
    print(f"✅ Email: {email}")
    
    # Login
    print("\n🌐 Login...")
    send_telegram(f"🔄 Login Garmin...")
    garth.login(email, password, prompt_mfa=wait_for_mfa_code)
    print("✅ Login OK!")
    
    # Create client
    client = Garmin(email, password)
    client.garth = garth.client
    
    # Get activities
    print("\n📋 Recupero lista attività...")
    activities = client.get_activities(0, 10)
    print(f"   Trovate {len(activities)} attività")
    
    # Download directory
    download_dir = Path('/Users/marco/.gemini/antigravity/scratch/mytrainingos/data/fit_files')
    download_dir.mkdir(parents=True, exist_ok=True)
    
    downloaded = 0
    for act in activities[:3]:  # Solo ultime 3 per test
        activity_id = act.get('activityId')
        activity_name = act.get('activityName', 'Unknown')
        
        zip_path = download_dir / f"{activity_id}.zip"
        if zip_path.exists():
            print(f"   ⏭️ {activity_id} già scaricato")
            continue
        
        print(f"   📥 Scarico {activity_id} ({activity_name})...")
        try:
            zip_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)
            if zip_data:
                with open(zip_path, 'wb') as f:
                    f.write(zip_data)
                downloaded += 1
                print(f"      ✅ Salvato ({len(zip_data)} bytes)")
        except Exception as e:
            print(f"      ❌ Errore: {e}")
    
    print(f"\n{'='*50}")
    print(f"✅ Scaricati {downloaded} nuovi file FIT")
    print(f"📁 Directory: {download_dir}")
    
    # List files
    print(f"\n📂 File nella directory:")
    for f in download_dir.iterdir():
        print(f"   - {f.name} ({f.stat().st_size} bytes)")
    
    send_telegram(f"✅ Scaricati {downloaded} nuovi file FIT!")

if __name__ == "__main__":
    main()
