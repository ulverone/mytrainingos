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
        
        # FIRST: Delete ALL old Garmin MFA emails to avoid picking up old codes
        print("🧹 Cleaning old Garmin MFA emails...")
        try:
            status, messages = mail.search(None, '(FROM "garmin")')
            if status == 'OK' and messages[0]:
                old_ids = messages[0].split()
                for eid in old_ids:
                    mail.store(eid, '+FLAGS', '\\Deleted')
                mail.expunge()
                print(f"   Deleted {len(old_ids)} old Garmin emails")
        except Exception as e:
            print(f"   Could not clean old emails: {e}")
        
        start_time = time.time()
        check_interval = 10  # Check every 10 seconds
        
        print(f"⏳ Waiting for NEW MFA email (timeout: {timeout}s)...")
        send_telegram("📧 <b>Garmin Sync Started</b>\n\nWaiting for NEW MFA email from Garmin...")
        
        while time.time() - start_time < timeout:
            # Search for UNSEEN emails from Garmin (correct sender!)
            # Note: Garmin uses alerts@account.garmin.com and Italian subject "Passcode di sicurezza"
            search_strategies = [
                '(UNSEEN FROM "alerts@account.garmin.com")',  # New unread from Garmin
                '(FROM "alerts@account.garmin.com")',          # All from Garmin alerts
                '(UNSEEN FROM "garmin")',                      # Any new from Garmin
                '(FROM "garmin" SUBJECT "sicurezza")',         # Italian subject
                '(FROM "garmin" SUBJECT "passcode")',          # English subject
                '(FROM "garmin")',                             # Fallback: any from Garmin
            ]
            
            email_ids = []
            for criteria in search_strategies:
                try:
                    status, messages = mail.search(None, criteria)
                    if status == 'OK' and messages[0]:
                        email_ids = messages[0].split()
                        print(f"   Found {len(email_ids)} emails with: {criteria}")
                        break
                except Exception as e:
                    print(f"   Search failed for {criteria}: {e}")
                    continue
            
            if email_ids:
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
                        
                        # Check if it's a passcode email (supports Italian and English)
                        if 'passcode' not in subject.lower() and 'sicurezza' not in subject.lower() and 'security' not in subject.lower() and 'code' not in subject.lower():
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
                        # Clean HTML entities and tags for better extraction
                        clean_body = re.sub(r'<[^>]+>', ' ', body)  # Remove HTML tags
                        clean_body = re.sub(r'&nbsp;', ' ', clean_body)  # Replace nbsp
                        clean_body = re.sub(r'&#\d+;', '', clean_body)  # Remove HTML entities
                        clean_body = re.sub(r'\s+', ' ', clean_body)  # Normalize whitespace
                        
                        # Debug: show snippet of body
                        print(f"   Email snippet: ...{clean_body[200:350]}..." if len(clean_body) > 350 else f"   Email: {clean_body}")
                        
                        # Try multiple patterns to find the 6-digit code
                        code = None
                        patterns = [
                            r'codice di sicurezza[^\d]*(\d{6})',  # Italian: after "codice di sicurezza"
                            r'passcode[^\d]*(\d{6})',              # After "passcode"  
                            r'code[^\d]*(\d{6})',                  # After "code"
                            r'\b(\d{6})\b',                        # Any standalone 6-digit number
                        ]
                        
                        for pattern in patterns:
                            match = re.search(pattern, clean_body, re.IGNORECASE)
                            if match:
                                code = match.group(1)
                                print(f"   Matched with pattern: {pattern}")
                                break
                        
                        if code:
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


def sync_garmin():
    """Main sync function with automatic email MFA."""
    import garth
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
        # Login with automatic email MFA using return_on_mfa approach
        # Per garth docs: login() returns ("needs_mfa", state) if MFA required, or (oauth1, oauth2) if not
        print("🔐 Logging in to Garmin Connect...")
        result1, result2 = garth.login(GARMIN_EMAIL, GARMIN_PASSWORD, return_on_mfa=True)
        
        if result1 == "needs_mfa":
            # MFA is required - Garmin has now SENT the email
            print("📧 MFA required - waiting for email from Garmin...")
            
            # Step 2: Read the MFA code from email (now that it was sent)
            mfa_code = read_mfa_from_email(timeout=180)
            
            if not mfa_code:
                raise Exception("Failed to get MFA code from email")
            
            # Step 3: Resume login with the state from login() AND the MFA code
            print(f"🔑 Submitting MFA code...")
            garth.resume_login(result2, mfa_code)
            print("✅ Login successful with MFA!")
        else:
            # Login succeeded without MFA - result1, result2 are oauth1, oauth2 tokens
            print("✅ Login successful (no MFA required)!")
        
        # Skip session save - not needed in ephemeral GitHub Actions environment
        # and garth.save() causes "Object of type Client is not JSON serializable" error
        
        # Use garth directly for API calls (no need for Garmin wrapper which causes serialization issues)
        print("📡 Fetching activities from Garmin Connect...")
        
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
            
            # Fetch multiple pages of activities
            all_activities = []
            start_idx = 0
            batch_size = 100
            max_days_back = HISTORICAL_MONTHS * 30
            
            while True:
                print(f"   Fetching batch {start_idx//batch_size + 1}...")
                # Use garth.connectapi directly
                activities_response = garth.connectapi(
                    f"/activitylist-service/activities/search/activities",
                    params={"start": start_idx, "limit": batch_size}
                )
                if not activities_response:
                    break
                
                all_activities.extend(activities_response)
                
                # Check if we've gone back far enough
                if activities_response:
                    oldest = activities_response[-1]
                    oldest_date_str = oldest.get("startTimeLocal", "")
                    if oldest_date_str:
                        oldest_date = datetime.fromisoformat(oldest_date_str.replace("Z", ""))
                        days_back = (datetime.now() - oldest_date).days
                        if days_back >= max_days_back:
                            print(f"   Reached {oldest_date.strftime('%Y-%m-%d')} ({days_back} days back) - stopping")
                            break
                
                start_idx += batch_size
                time.sleep(0.5)
            
            activities = all_activities
            print(f"📋 Found {len(activities)} activities in Garmin")
        else:
            print("📋 Daily sync: Fetching recent activities...")
            send_telegram("📋 <b>Daily Sync</b>\n\nChecking for new activities...")
            # Fetch recent activities
            activities = garth.connectapi(
                "/activitylist-service/activities/search/activities",
                params={"start": 0, "limit": 30}
            ) or []
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
                # Download using garth - direct URL to get original FIT file
                download_url = f"/download-service/files/activity/{activity_id}"
                response = garth.client.get("connectapi", download_url)
                if response and response.status_code == 200:
                    zip_data = response.content
                    with open(fit_path, "wb") as f:
                        f.write(zip_data)
                    downloaded += 1
                else:
                    print(f"   ⚠️ Download returned status {response.status_code if response else 'None'}")
                    errors += 1
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
