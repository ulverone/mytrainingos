#!/usr/bin/env python3
"""
Oura Ring OAuth2 Sync for MyTrainingOS
Syncs sleep, readiness, activity and HRV data from Oura Ring
"""

import os
import sys
import json
import webbrowser
from datetime import datetime, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlencode, parse_qs, urlparse
import ssl

# Try to import requests, install if not available
try:
    import requests
except ImportError:
    print("Installing requests library...")
    os.system(f"{sys.executable} -m pip install requests")
    import requests

# Configuration
CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'data', 'oura_config.json')
DATA_FILE = os.path.join(os.path.dirname(__file__), 'data', 'oura.json')
REDIRECT_URI = 'http://localhost:8888/callback'
OURA_AUTH_URL = 'https://cloud.ouraring.com/oauth/authorize'
OURA_TOKEN_URL = 'https://api.ouraring.com/oauth/token'
OURA_API_BASE = 'https://api.ouraring.com/v2/usercollection'

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """Handle OAuth2 callback"""
    auth_code = None
    
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/callback':
            params = parse_qs(parsed.query)
            if 'code' in params:
                OAuthCallbackHandler.auth_code = params['code'][0]
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'''
                    <html><body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1>Autorizzazione completata!</h1>
                    <p>Puoi chiudere questa finestra e tornare al terminale.</p>
                    </body></html>
                ''')
            else:
                self.send_response(400)
                self.end_headers()
                self.wfile.write(b'Authorization failed')
        else:
            self.send_response(404)
            self.end_headers()
    
    def log_message(self, format, *args):
        pass  # Suppress logging

class OuraSync:
    def __init__(self):
        self.config = self.load_config()
    
    def load_config(self):
        """Load OAuth configuration"""
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r') as f:
                return json.load(f)
        return {}
    
    def save_config(self):
        """Save OAuth configuration"""
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(self.config, f, indent=2)
    
    def setup(self):
        """Interactive OAuth2 setup"""
        print("\n🔗 Configurazione Oura OAuth2\n")
        
        # Check if credentials already exist in config
        if self.config.get('client_id') and self.config.get('client_secret'):
            client_id = self.config['client_id']
            client_secret = self.config['client_secret']
            print(f"✅ Credenziali trovate nel file di configurazione")
            print(f"   Client ID: {client_id[:20]}...")
        else:
            print("Prima di procedere, assicurati di aver creato un'app su:")
            print("https://cloud.ouraring.com/oauth/applications\n")
            print("Redirect URI da usare: http://localhost:8888/callback\n")
            
            client_id = input("Client ID: ").strip()
            client_secret = input("Client Secret: ").strip()
            
            if not client_id or not client_secret:
                print("❌ Client ID e Client Secret sono richiesti")
                return False
            
            self.config['client_id'] = client_id
            self.config['client_secret'] = client_secret
        
        # Get authorization code
        auth_url = f"{OURA_AUTH_URL}?" + urlencode({
            'response_type': 'code',
            'client_id': client_id,
            'redirect_uri': REDIRECT_URI,
            'scope': 'daily heartrate personal session tag workout spo2',
            'state': 'mytrainingos'
        })
        
        print(f"\n📱 Aprendo il browser per l'autorizzazione...")
        webbrowser.open(auth_url)
        
        # Start callback server
        print("⏳ In attesa del callback OAuth...")
        server = HTTPServer(('localhost', 8888), OAuthCallbackHandler)
        server.handle_request()
        
        if not OAuthCallbackHandler.auth_code:
            print("❌ Autorizzazione fallita")
            return False
        
        # Exchange code for tokens
        print("🔄 Scambio codice per token...")
        response = requests.post(OURA_TOKEN_URL, data={
            'grant_type': 'authorization_code',
            'code': OAuthCallbackHandler.auth_code,
            'redirect_uri': REDIRECT_URI,
            'client_id': client_id,
            'client_secret': client_secret
        })
        
        if response.status_code != 200:
            print(f"❌ Errore token: {response.text}")
            return False
        
        tokens = response.json()
        self.config['access_token'] = tokens['access_token']
        self.config['refresh_token'] = tokens['refresh_token']
        self.config['expires_at'] = datetime.now().timestamp() + tokens.get('expires_in', 86400)
        
        self.save_config()
        print("\n✅ Configurazione completata!")
        return True
    
    def refresh_token(self):
        """Refresh access token if expired"""
        if not self.config.get('refresh_token'):
            return False
        
        if datetime.now().timestamp() < self.config.get('expires_at', 0) - 300:
            return True  # Token still valid
        
        print("🔄 Rinnovo token...")
        response = requests.post(OURA_TOKEN_URL, data={
            'grant_type': 'refresh_token',
            'refresh_token': self.config['refresh_token'],
            'client_id': self.config['client_id'],
            'client_secret': self.config['client_secret']
        })
        
        if response.status_code != 200:
            print(f"❌ Errore refresh: {response.text}")
            return False
        
        tokens = response.json()
        self.config['access_token'] = tokens['access_token']
        self.config['refresh_token'] = tokens.get('refresh_token', self.config['refresh_token'])
        self.config['expires_at'] = datetime.now().timestamp() + tokens.get('expires_in', 86400)
        self.save_config()
        return True
    
    def get_headers(self):
        """Get API headers with access token"""
        return {'Authorization': f"Bearer {self.config['access_token']}"}
    
    def fetch_data(self, endpoint, start_date, end_date):
        """Fetch data from Oura API"""
        url = f"{OURA_API_BASE}/{endpoint}"
        params = {'start_date': start_date, 'end_date': end_date}
        response = requests.get(url, headers=self.get_headers(), params=params)
        
        if response.status_code == 200:
            return response.json().get('data', [])
        else:
            print(f"⚠️ Errore fetching {endpoint}: {response.status_code}")
            return []
    
    def sync(self, days=42):
        """Sync Oura data for the last N days"""
        if not self.config.get('access_token'):
            print("❌ Non configurato. Esegui: python3 oura_sync.py --setup")
            return False
        
        if not self.refresh_token():
            print("❌ Token scaduto. Esegui: python3 oura_sync.py --setup")
            return False
        
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        print(f"📥 Sincronizzazione dati Oura ({start_date} → {end_date})...")
        
        data = {
            'syncDate': datetime.now().isoformat(),
            'startDate': start_date,
            'endDate': end_date,
            'sleep': [],
            'readiness': [],
            'activity': [],
            'heartrate': [],
            'daily': []
        }
        
        # Fetch all data types
        print("  📊 Sleep...")
        data['sleep'] = self.fetch_data('daily_sleep', start_date, end_date)
        
        # Also fetch detailed sleep for HRV values
        print("  📊 Sleep (dettagli HRV)...")
        detailed_sleep = self.fetch_data('sleep', start_date, end_date)
        # Index by date for easy lookup
        sleep_hrv = {}
        for s in detailed_sleep:
            day = s.get('day')
            if day and s.get('average_hrv'):
                # Take the most recent sleep session per day
                if day not in sleep_hrv or s.get('bedtime_end', '') > sleep_hrv[day].get('bedtime_end', ''):
                    sleep_hrv[day] = s
        
        print("  ⚡ Readiness...")
        data['readiness'] = self.fetch_data('daily_readiness', start_date, end_date)
        
        print("  🚶 Activity...")
        data['activity'] = self.fetch_data('daily_activity', start_date, end_date)
        
        print("  ❤️ Heart Rate...")
        data['heartrate'] = self.fetch_data('heartrate', start_date, end_date)
        
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
                # Get actual HRV from detailed sleep data
                if date in sleep_hrv:
                    daily_data[date]['hrv'] = sleep_hrv[date].get('average_hrv')
                    daily_data[date]['lowestHR'] = sleep_hrv[date].get('lowest_heart_rate')
        
        for readiness in data['readiness']:
            date = readiness.get('day')
            if date:
                if date not in daily_data:
                    daily_data[date] = {'date': date}
                daily_data[date]['readinessScore'] = readiness.get('score')
                # Only use hrv_balance as fallback if no average_hrv available
                if 'hrv' not in daily_data[date]:
                    daily_data[date]['hrv'] = readiness.get('contributors', {}).get('hrv_balance')
                    daily_data[date]['hrvIsBalance'] = True  # Mark as balance score, not ms
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
        
        # Convert to list and sort
        data['daily'] = sorted(daily_data.values(), key=lambda x: x['date'], reverse=True)
        
        # Save to file
        os.makedirs(os.path.dirname(DATA_FILE), exist_ok=True)
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"\n✅ Sincronizzati {len(data['daily'])} giorni di dati Oura")
        print(f"   File salvato: {DATA_FILE}")
        
        # Print latest data
        if data['daily']:
            latest = data['daily'][0]
            print(f"\n📊 Ultimo dato ({latest['date']}):")
            if 'sleepScore' in latest:
                print(f"   🛏️ Sleep Score: {latest.get('sleepScore', 'N/A')}")
            if 'readinessScore' in latest:
                print(f"   ⚡ Readiness: {latest.get('readinessScore', 'N/A')}")
            if 'activityScore' in latest:
                print(f"   🚶 Activity: {latest.get('activityScore', 'N/A')}")
        
        return True

def main():
    sync = OuraSync()
    
    if '--setup' in sys.argv:
        sync.setup()
    else:
        sync.sync()

if __name__ == '__main__':
    main()
