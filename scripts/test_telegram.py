#!/usr/bin/env python3
"""Test Telegram Bot"""
import requests

TOKEN = '8541924986:AAGVulVnP9J30F-ttqespS4q0vsukjH1mTI'
CHAT_ID = '135519413'

# Send test message
url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
data = {
    'chat_id': CHAT_ID,
    'text': '🧪 Test MyTrainingOS Bot!\n\nSe ricevi questo messaggio, il bot funziona! ✅\n\nRispondi con un numero (es: 123456) per testare la ricezione MFA.',
    'parse_mode': 'HTML'
}

response = requests.post(url, json=data, timeout=10)
if response.ok:
    print('✅ Messaggio inviato su Telegram!')
else:
    print(f'❌ Errore: {response.text}')
