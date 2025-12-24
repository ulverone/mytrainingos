#!/usr/bin/env python3
"""
Garmin Sync Script - Versione Semplificata
Sincronizza le attività da Garmin Connect direttamente.
"""

import os
import sys
import shutil
import pandas as pd
from pathlib import Path
from datetime import datetime

# Paths
GARMIN_MODULE = '/Users/marco/.gemini/antigravity/scratch/garmin_analyzer'
EXCEL_PATH = Path(GARMIN_MODULE) / 'Storico_Allenamenti_Garmin.xlsx'
DOWNLOAD_DIR = Path(GARMIN_MODULE) / 'downloaded_activities'

sys.path.insert(0, GARMIN_MODULE)

def main():
    print("=" * 50)
    print("🔄 GARMIN SYNC - Versione Semplificata")
    print("=" * 50)
    
    try:
        import garth
        from garminconnect import Garmin
        from keychain_auth import get_credentials
        from enhanced_parser import parse_activity_file
        from auth_log import ActivityLog
        
        # Clear garth cache per nuovo login
        print("\n📁 Pulizia cache...")
        for p in [os.path.expanduser("~/.garth"), 
                  os.path.expanduser("~/.cache/garth")]:
            if os.path.exists(p):
                shutil.rmtree(p)
        
        # Get credentials
        print("🔐 Recupero credenziali da Keychain...")
        email, password = get_credentials()
        
        if not email or not password:
            print("❌ Credenziali non trovate!")
            return
        
        print(f"✅ Credenziali per: {email}")
        
        # Login con garth
        print("\n🌐 Connessione a Garmin Connect...")
        garth.login(email, password)
        print("✅ Login riuscito!")
        
        # Crea client Garmin usando sessione garth
        client = Garmin(email, password)
        client.garth = garth.client
        
        # Scarica lista attività
        print("\n📋 Recupero lista attività...")
        activities = client.get_activities(0, 50)  # Ultime 50
        print(f"   Trovate {len(activities)} attività recenti")
        
        # Verifica database log
        log_db = ActivityLog(str(Path(GARMIN_MODULE) / "garmin_log.db"))
        
        # Conta nuove attività
        new_count = 0
        new_laps = []
        
        DOWNLOAD_DIR.mkdir(exist_ok=True)
        
        for act in activities:
            activity_id = act.get('activityId')
            if not activity_id:
                continue
                
            # Già scaricata?
            if log_db.is_processed(activity_id):
                continue
            
            new_count += 1
            print(f"\n📥 Scarico attività {activity_id}...")
            
            try:
                # Download ZIP
                zip_data = client.download_activity(activity_id, dl_fmt=client.ActivityDownloadFormat.ORIGINAL)
                
                if zip_data:
                    zip_path = DOWNLOAD_DIR / f"{activity_id}.zip"
                    with open(zip_path, 'wb') as f:
                        f.write(zip_data)
                    
                    # Log download
                    log_db.mark_processed(activity_id)
                    
                    # Parse
                    summary, laps = parse_activity_file(str(zip_path), activity_id)
                    
                    if summary and laps:
                        for lap in laps:
                            for k, v in summary.items():
                                if k != "ActivityID":
                                    lap[f"Attivita_{k}"] = v
                            new_laps.append(lap)
                        
                        log_db.mark_parsed(activity_id)
                        print(f"   ✓ {len(laps)} lap")
                        
            except Exception as e:
                print(f"   ⚠ Errore: {e}")
        
        # Aggiorna Excel
        if new_laps:
            print(f"\n📊 Aggiornamento Excel con {len(new_laps)} nuovi lap...")
            
            if EXCEL_PATH.exists():
                existing = pd.read_excel(EXCEL_PATH)
                df = pd.concat([existing, pd.DataFrame(new_laps)], ignore_index=True)
            else:
                df = pd.DataFrame(new_laps)
            
            # Sort e deduplica
            if "Attivita_Data Inizio" in df.columns:
                df["Attivita_Data Inizio"] = pd.to_datetime(df["Attivita_Data Inizio"], errors='coerce')
                df = df.sort_values("Attivita_Data Inizio")
            
            df = df.drop_duplicates(subset=["ActivityID", "Numero Lap"], keep="last")
            df.to_excel(EXCEL_PATH, sheet_name="Storico Allenamenti Completo", index=False)
            
            print(f"✅ Excel aggiornato: {len(df)} lap totali")
        else:
            print(f"\n✅ Nessuna nuova attività da scaricare")
            if EXCEL_PATH.exists():
                df = pd.read_excel(EXCEL_PATH)
                print(f"   File Excel esistente: {len(df)} lap")
        
        print("\n" + "=" * 50)
        print(f"✅ SYNC COMPLETATA! Nuove attività: {new_count}")
        print("=" * 50)
        print(f"\n📄 File: {EXCEL_PATH}")
        print("\n💡 Ora puoi aprire MyTrainingOS!")
            
    except Exception as e:
        print(f"\n❌ Errore: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    main()
