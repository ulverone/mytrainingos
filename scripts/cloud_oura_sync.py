#!/usr/bin/env python3
"""
Cloud Oura Sync for GitHub Actions
Syncs Oura data using OAuth tokens from environment
"""

import os
import json
import requests
from datetime import datetime, timedelta
from pathlib import Path

# Config from environment
OURA_ACCESS_TOKEN = os.environ.get('OURA_ACCESS_TOKEN')
OURA_REFRESH_TOKEN = os.environ.get('OURA_REFRESH_TOKEN')
OURA_CLIENT_ID = os.environ.get('OURA_CLIENT_ID')
OURA_CLIENT_SECRET = os.environ.get('OURA_CLIENT_SECRET')

OURA_API_BASE = 'https://api.ouraring.com/v2/usercollection'
OURA_TOKEN_URL = 'https://api.ouraring.com/oauth/token'

DATA_FILE = Path('data/oura.json')


def refresh_token():
    """Refresh OAuth token if needed."""
    global OURA_ACCESS_TOKEN
    
    response = requests.post(OURA_TOKEN_URL, data={
        'grant_type': 'refresh_token',
        'refresh_token': OURA_REFRESH_TOKEN,
        'client_id': OURA_CLIENT_ID,
        'client_secret': OURA_CLIENT_SECRET
    })
    
    if response.ok:
        tokens = response.json()
        OURA_ACCESS_TOKEN = tokens['access_token']
        print("✅ Token refreshed")
        return True
    else:
        print(f"❌ Token refresh failed: {response.text}")
        return False


def fetch_data(endpoint, start_date, end_date):
    """Fetch data from Oura API."""
    headers = {'Authorization': f'Bearer {OURA_ACCESS_TOKEN}'}
    params = {'start_date': start_date, 'end_date': end_date}
    
    response = requests.get(f"{OURA_API_BASE}/{endpoint}", headers=headers, params=params)
    
    if response.status_code == 401:
        # Token expired, try refresh
        if refresh_token():
            headers = {'Authorization': f'Bearer {OURA_ACCESS_TOKEN}'}
            response = requests.get(f"{OURA_API_BASE}/{endpoint}", headers=headers, params=params)
    
    if response.ok:
        return response.json().get('data', [])
    else:
        print(f"⚠️ Error fetching {endpoint}: {response.status_code}")
        return []


def sync_oura():
    """Main sync function."""
    print("🔄 Starting Oura Sync...")
    
    end_date = datetime.now().strftime('%Y-%m-%d')
    start_date = (datetime.now() - timedelta(days=42)).strftime('%Y-%m-%d')
    
    print(f"📅 Date range: {start_date} → {end_date}")
    
    data = {
        'syncDate': datetime.now().isoformat(),
        'startDate': start_date,
        'endDate': end_date,
        'sleep': [],
        'readiness': [],
        'activity': [],
        'daily': []
    }
    
    # Fetch all data types
    print("  📊 Fetching sleep...")
    data['sleep'] = fetch_data('daily_sleep', start_date, end_date)
    
    print("  📊 Fetching detailed sleep (HRV)...")
    detailed_sleep = fetch_data('sleep', start_date, end_date)
    sleep_hrv = {}
    for s in detailed_sleep:
        day = s.get('day')
        if day and s.get('average_hrv'):
            if day not in sleep_hrv or s.get('bedtime_end', '') > sleep_hrv[day].get('bedtime_end', ''):
                sleep_hrv[day] = s
    
    print("  ⚡ Fetching readiness...")
    data['readiness'] = fetch_data('daily_readiness', start_date, end_date)
    
    print("  🚶 Fetching activity...")
    data['activity'] = fetch_data('daily_activity', start_date, end_date)
    
    # Process into daily summary
    daily_data = {}
    
    for sleep in data['sleep']:
        date = sleep.get('day')
        if date:
            if date not in daily_data:
                daily_data[date] = {'date': date}
            daily_data[date]['sleepScore'] = sleep.get('score')
            daily_data[date]['totalSleep'] = sleep.get('contributors', {}).get('total_sleep')
            daily_data[date]['deepSleep'] = sleep.get('contributors', {}).get('deep_sleep')
            daily_data[date]['efficiency'] = sleep.get('contributors', {}).get('efficiency')
            if date in sleep_hrv:
                daily_data[date]['hrv'] = sleep_hrv[date].get('average_hrv')
                daily_data[date]['lowestHR'] = sleep_hrv[date].get('lowest_heart_rate')
    
    for readiness in data['readiness']:
        date = readiness.get('day')
        if date:
            if date not in daily_data:
                daily_data[date] = {'date': date}
            daily_data[date]['readinessScore'] = readiness.get('score')
            if 'hrv' not in daily_data[date]:
                daily_data[date]['hrv'] = readiness.get('contributors', {}).get('hrv_balance')
                daily_data[date]['hrvIsBalance'] = True
            daily_data[date]['hrvBalance'] = readiness.get('contributors', {}).get('hrv_balance')
            daily_data[date]['recoveryIndex'] = readiness.get('contributors', {}).get('recovery_index')
            daily_data[date]['restingHR'] = readiness.get('contributors', {}).get('resting_heart_rate')
    
    for activity in data['activity']:
        date = activity.get('day')
        if date:
            if date not in daily_data:
                daily_data[date] = {'date': date}
            daily_data[date]['activityScore'] = activity.get('score')
            daily_data[date]['activeCalories'] = activity.get('active_calories')
            daily_data[date]['steps'] = activity.get('steps')
    
    data['daily'] = sorted(daily_data.values(), key=lambda x: x['date'], reverse=True)
    
    # Save
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, 'w') as f:
        json.dump(data, f, indent=2)
    
    print(f"\n✅ Oura sync complete! {len(data['daily'])} days saved.")
    return True


if __name__ == "__main__":
    if not OURA_ACCESS_TOKEN:
        print("❌ Missing OURA_ACCESS_TOKEN")
        exit(1)
    
    sync_oura()
