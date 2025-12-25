#!/usr/bin/env python3
"""
Cloud Garmin Sync with Automatic Email MFA
Reads MFA codes automatically from Gmail via IMAP - no manual intervention needed!
"""

import os
import sys
import time
import json
import re
import imaplib
import email
from email.header import decode_header
import requests
from pathlib import Path
from datetime import datetime, timedelta

# Email Config (for reading MFA codes)
EMAIL_ADDRESS = os.environ.get('MFA_EMAIL_ADDRESS')  # Gmail address
EMAIL_PASSWORD = os.environ.get('MFA_EMAIL_PASSWORD')  # Gmail App Password
IMAP_SERVER = os.environ.get('IMAP_SERVER', 'imap.gmail.com')

# Telegram Config (for notifications only)
TELEGRAM_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID')

# Garmin Config
GARMIN_EMAIL = os.environ.get('GARMIN_EMAIL')
GARMIN_PASSWORD = os.environ.get('GARMIN_PASSWORD')


def send_telegram(message):
    """Send a notification via Telegram bot."""
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


def read_mfa_from_email(timeout=180):
    """
    Read the MFA code from Gmail via IMAP.
    Looks for recent emails from Garmin containing a passcode.
    """
    print("📧 Connecting to email to read MFA code...")
    
    if not EMAIL_ADDRESS or not EMAIL_PASSWORD:
        print("❌ Email credentials not configured!")
        return None
    
    try:
        # Connect to Gmail IMAP
        mail = imaplib.IMAP4_SSL(IMAP_SERVER)
        mail.login(EMAIL_ADDRESS, EMAIL_PASSWORD)
        mail.select('INBOX')
        
        start_time = time.time()
        check_interval = 10  # Check every 10 seconds
        
        print(f"⏳ Waiting for MFA email (timeout: {timeout}s)...")
        send_telegram("📧 <b>Garmin Sync Started</b>\n\nWaiting for MFA email from Garmin...")
        
        # Calculate cutoff time (only look at emails from last 5 minutes)
        cutoff_time = datetime.now() - timedelta(minutes=5)
        
        while time.time() - start_time < timeout:
            # Search for emails from Garmin
            search_criteria = '(FROM "noreply@garmin.com" SUBJECT "passcode")'
            
            try:
                status, messages = mail.search(None, search_criteria)
                if status != 'OK':
                    # Try alternative search
                    status, messages = mail.search(None, 'FROM', '"garmin"')
            except:
                status, messages = mail.search(None, 'FROM', '"garmin"')
            
            if status == 'OK' and messages[0]:
                email_ids = messages[0].split()
                
                # Check most recent emails first
                for email_id in reversed(email_ids[-5:]):
                    try:
                        status, msg_data = mail.fetch(email_id, '(RFC822)')
                        if status != 'OK':
                            continue
                        
                        msg = email.message_from_bytes(msg_data[0][1])
                        
                        # Check email date
                        date_str = msg.get('Date', '')
                        
                        # Get subject
                        subject = msg.get('Subject', '')
                        if subject:
                            decoded = decode_header(subject)[0]
                            if isinstance(decoded[0], bytes):
                                subject = decoded[0].decode(decoded[1] or 'utf-8')
                            else:
                                subject = decoded[0]
                        
                        # Check if it's a passcode email
                        if 'passcode' not in subject.lower() and 'security' not in subject.lower() and 'code' not in subject.lower():
                            continue
                        
                        # Get email body
                        body = ""
                        if msg.is_multipart():
                            for part in msg.walk():
                                if part.get_content_type() == "text/plain":
                                    try:
                                        body = part.get_payload(decode=True).decode()
                                        break
                                    except:
                                        continue
                                elif part.get_content_type() == "text/html":
                                    try:
                                        body = part.get_payload(decode=True).decode()
                                    except:
                                        continue
                        else:
                            try:
                                body = msg.get_payload(decode=True).decode()
                            except:
                                body = str(msg.get_payload())
                        
                        # Extract 6-digit code from body
                        code_match = re.search(r'\b(\d{6})\b', body)
                        if code_match:
                            code = code_match.group(1)
                            print(f"✅ Found MFA code: {code[:2]}****")
                            
                            # Mark email as read
                            mail.store(email_id, '+FLAGS', '\\Seen')
                            
                            # Delete or archive the email to avoid reuse
                            mail.store(email_id, '+FLAGS', '\\Deleted')
                            mail.expunge()
                            
                            mail.logout()
                            send_telegram(f"✅ MFA code found automatically! Proceeding with sync...")
                            return code
                    
                    except Exception as e:
                        print(f"   Error reading email: {e}")
                        continue
            
            # Wait before next check
            time.sleep(check_interval)
            remaining = int(timeout - (time.time() - start_time))
            if remaining % 30 == 0:
                print(f"   Still waiting... {remaining}s remaining")
        
        mail.logout()
        print("❌ Timeout: No MFA email found")
        send_telegram("❌ <b>MFA Timeout</b>\n\nNo passcode email received from Garmin within timeout.")
        return None
        
    except Exception as e:
        print(f"❌ Email error: {e}")
        send_telegram(f"❌ <b>Email Error</b>\n\n{str(e)}")
        return None


def email_mfa_prompt():
    """
    Custom MFA handler for garth library.
    Called when Garmin requests MFA - reads code from email automatically.
    """
    return read_mfa_from_email()


def sync_garmin():
    """Main sync function with automatic email MFA."""
    import garth
    from garminconnect import Garmin
    from datetime import timedelta
    
    # Configuration
    HISTORICAL_MONTHS = int(os.environ.get('HISTORICAL_MONTHS', '12'))
    
    print("🔄 Starting Garmin Sync (Automatic Email MFA)...")
    print(f"📧 MFA Email: {EMAIL_ADDRESS}")
    print(f"🏃 Garmin: {GARMIN_EMAIL}")
    
    # Clear any cached sessions
    garth_dir = os.path.expanduser("~/.garth")
    if os.path.exists(garth_dir):
        import shutil
        shutil.rmtree(garth_dir)
    
    try:
        # Login with automatic email MFA
        print("🔐 Logging in to Garmin Connect...")
        garth.login(GARMIN_EMAIL, GARMIN_PASSWORD, prompt_mfa=email_mfa_prompt)
        print("✅ Login successful!")
        
        # Save session for future use
        garth.save("~/.garth")
        
        # Create Garmin client
        client = Garmin(GARMIN_EMAIL, GARMIN_PASSWORD)
        client.garth = garth.client
        
        # Setup data directory
        data_dir = Path("data/activities")
        data_dir.mkdir(parents=True, exist_ok=True)
        
        # Check workouts.json for already processed activity IDs
        # This persists across runs since workouts.json IS committed to the repo
        workouts_file = Path("data/workouts.json")
        processed_ids = set()
        
        if workouts_file.exists():
            try:
                with open(workouts_file, 'r') as f:
                    workouts_data = json.load(f)
                    for activity in workouts_data.get('activities', []):
                        if activity.get('id'):
                            processed_ids.add(str(activity['id']))
                print(f"📋 Found {len(processed_ids)} already processed activities in workouts.json")
            except Exception as e:
                print(f"⚠️ Could not read workouts.json: {e}")
        
        # Determine if this is first run (no processed activities)
        is_first_run = len(processed_ids) < 10
        
        if is_first_run:
            print(f"\n📆 HISTORICAL SYNC: Downloading last {HISTORICAL_MONTHS} months...")
            send_telegram(f"📆 <b>Sync Storico</b>\n\nScaricando {HISTORICAL_MONTHS} mesi di attività...")
            
            end_date = datetime.now()
            start_date = end_date - timedelta(days=HISTORICAL_MONTHS * 30)
            
            all_activities = []
            batch_size = 100
            start_idx = 0
            
            while True:
                print(f"   Fetching batch {start_idx//batch_size + 1}...")
                batch = client.get_activities(start_idx, batch_size)
                if not batch:
                    break
                
                all_activities.extend(batch)
                
                oldest = batch[-1]
                oldest_date_str = oldest.get("startTimeLocal", "")
                if oldest_date_str:
                    oldest_date = datetime.fromisoformat(oldest_date_str.replace("Z", ""))
                    if oldest_date < start_date:
                        print(f"   Reached {oldest_date.strftime('%Y-%m-%d')} - stopping")
                        break
                
                start_idx += batch_size
                time.sleep(0.5)
            
            activities = [a for a in all_activities if a.get("startTimeLocal")]
            print(f"📋 Found {len(activities)} activities in Garmin")
        else:
            print("📋 Daily sync: Fetching recent activities...")
            send_telegram("📋 <b>Daily Sync</b>\n\nChecking for new activities...")
            activities = client.get_activities(0, 30)
            print(f"   Found {len(activities)} recent activities")
        
        # Download only activities NOT already processed
        downloaded = 0
        skipped = 0
        errors = 0
        
        for i, act in enumerate(activities):
            activity_id = str(act.get("activityId"))
            if not activity_id:
                continue
            
            # Skip if already processed (in workouts.json)
            if activity_id in processed_ids:
                skipped += 1
                continue
            
            fit_path = data_dir / f"{activity_id}.zip"
            
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
                time.sleep(0.3)
            except Exception as e:
                print(f"   ⚠️ Error: {e}")
                errors += 1
        
        # Summary
        total_files = len(list(data_dir.glob("*.zip")))
        summary = f"""✅ <b>Garmin Sync Complete!</b>

📥 Downloaded: {downloaded} new activities
⏭️ Skipped: {skipped} (already present)
📁 Total in archive: {total_files} activities

🤖 <i>Fully automatic - no manual MFA needed!</i>"""
        
        if errors > 0:
            summary += f"\n⚠️ Errors: {errors}"
        
        print(f"\n{summary.replace('<b>', '').replace('</b>', '').replace('<i>', '').replace('</i>', '')}")
        send_telegram(summary)
        return True
        
    except Exception as e:
        error_msg = str(e)
        print(f"❌ Sync failed: {error_msg}")
        send_telegram(f"❌ <b>Garmin Sync Failed</b>\n\n{error_msg}")
        return False


if __name__ == "__main__":
    required = ['MFA_EMAIL_ADDRESS', 'MFA_EMAIL_PASSWORD', 'GARMIN_EMAIL', 'GARMIN_PASSWORD']
    missing = [v for v in required if not os.environ.get(v)]
    
    if missing:
        print(f"❌ Missing environment variables: {', '.join(missing)}")
        sys.exit(1)
    
    success = sync_garmin()
    sys.exit(0 if success else 1)
