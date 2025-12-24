#!/usr/bin/env python3
"""
Test Garmin Login with Telegram MFA
"""
import os
import sys
import time
import shutil
import requests

# Telegram config
TELEGRAM_TOKEN = '8541924986:AAGVulVnP9J30F-ttqespS4q0vsukjH1mTI'
TELEGRAM_CHAT_ID = '135519413'

def send_telegram(message):
    """Send message via Telegram."""
    url = f'https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage'
    data = {'chat_id': TELEGRAM_CHAT_ID, 'text': message, 'parse_mode': 'HTML'}
    try:
        response = requests.post(url, json=data, timeout=10)
        return response.ok
    except:
        return False

def get_telegram_updates(offset=None):
    """Get messages from Telegram."""
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
    """Wait for MFA code via Telegram."""
    print("⏳ Waiting for MFA code via Telegram...")
    send_telegram("🔐 <b>Garmin MFA Required</b>\n\nRispondi con il codice MFA inviato da Garmin.\n\n⏱️ Timeout: 5 minuti")
    
    start_time = time.time()
    
    # Get current update_id to ignore old messages
    updates = get_telegram_updates()
    last_update_id = updates[-1]['update_id'] + 1 if updates else None
    
    while time.time() - start_time < timeout:
        updates = get_telegram_updates(offset=last_update_id)
        
        for update in updates:
            last_update_id = update['update_id'] + 1
            
            if 'message' in update:
                text = update['message'].get('text', '').strip()
                # Check if it's a code (digits, 4-8 chars)
                if text.isdigit() and 4 <= len(text) <= 8:
                    print(f"✅ MFA code received!")
                    send_telegram(f"✅ Codice ricevuto! Procedo...")
                    return text
        
        time.sleep(2)
    
    send_telegram("❌ Timeout! Nessun codice ricevuto.")
    return None

def telegram_mfa_prompt():
    """Custom MFA handler for garth."""
    return wait_for_mfa_code()

def main():
    # Add garmin_analyzer to path for keychain_auth
    sys.path.insert(0, '/Users/marco/.gemini/antigravity/scratch/garmin_analyzer')
    
    import garth
    from keychain_auth import get_credentials
    
    print("=" * 50)
    print("🧪 TEST GARMIN LOGIN CON TELEGRAM MFA")
    print("=" * 50)
    
    # Clear cache
    for p in [os.path.expanduser("~/.garth"), os.path.expanduser("~/.cache/garth")]:
        if os.path.exists(p):
            shutil.rmtree(p)
    
    # Get credentials from keychain
    print("\n🔐 Recupero credenziali...")
    email, password = get_credentials()
    
    if not email or not password:
        print("❌ Credenziali non trovate!")
        return
    
    print(f"✅ Email: {email}")
    
    # Try login
    print("\n🌐 Login a Garmin Connect...")
    send_telegram(f"🔄 <b>Tentativo login Garmin</b>\n\nUser: {email}")
    
    try:
        garth.login(email, password, prompt_mfa=telegram_mfa_prompt)
        print("\n✅ LOGIN RIUSCITO!")
        send_telegram("🎉 <b>Login Garmin riuscito!</b>")
        
        # Test getting activities
        from garminconnect import Garmin
        client = Garmin(email, password)
        client.garth = garth.client
        
        activities = client.get_activities(0, 5)
        print(f"📋 Trovate {len(activities)} attività recenti")
        send_telegram(f"📋 Trovate {len(activities)} attività recenti")
        
    except Exception as e:
        print(f"\n❌ Errore: {e}")
        send_telegram(f"❌ Errore login: {str(e)[:200]}")

if __name__ == "__main__":
    main()
