"""
MyTrainingOS - AI Coach Prompt Generator
App Python semplificata per generare prompt di analisi allenamenti
Con integrazione Garmin Connect
"""

import pandas as pd
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
from datetime import datetime, timedelta
from pathlib import Path
import pyperclip
import sys
import threading

# Integrazione Garmin API
GARMIN_MODULE_PATH = '/Users/marco/.gemini/antigravity/scratch/garmin_analyzer'
sys.path.insert(0, GARMIN_MODULE_PATH)
try:
    from garmin_api import download_and_process, get_activities_dataframe, get_default_excel_path
    GARMIN_AVAILABLE = True
except ImportError:
    GARMIN_AVAILABLE = False

# ============================================================================
# CONFIGURAZIONE DEFAULT (Marco)
# ============================================================================
DEFAULT_AGE = 47
DEFAULT_FTP_BIKE = 300        # Watt - Functional Threshold Power bici (Z4: 259-301W)
DEFAULT_FTP_RUN = 256         # sec/km (4:16/km) - Functional Threshold Pace corsa
DEFAULT_FTP_SWIM = 105        # sec/100m (1:45/100m) - Functional Threshold Pace nuoto
DEFAULT_LTHR = 165            # bpm - per fallback hrTSS

# Zone di allenamento (Marco)
ZONES_BIKE = """Zone Bici (Potenza prioritaria):
- Z1 Recupero: < 158 W, < 125 bpm
- Z2 Fondo Lento: 159-215 W, 126-138 bpm
- Z3 Tempo: 216-258 W, 139-146 bpm
- Z4 Soglia (FTP 300W): 259-301 W, 147-155 bpm
- Z5 VO2max: > 302 W, > 156 bpm"""

ZONES_RUN = """Zone Corsa (Passo prioritario):
- Z1 Recupero: > 5:30/km, < 134 bpm
- Z2 Fondo Lento: 4:52-5:30/km, 134-142 bpm
- Z3 Tempo: 4:31-4:49/km, 143-150 bpm
- Z4 Soglia (4:16/km): 4:13-4:29/km, 151-158 bpm
- Z5 VO2max: < 4:12/km, > 159 bpm"""

# ============================================================================
# FUNZIONI
# ============================================================================

def load_excel_data(file_path):
    """Carica il file Excel, ritorna dati deduplucati e dati lap grezzi"""
    df_raw = pd.read_excel(file_path)
    df = df_raw.groupby('ActivityID').first().reset_index()
    return df, df_raw

def calculate_sport_tss(row, ftp_bike, ftp_run, ftp_swim, lthr):
    """
    Calcola TSS sport-specific secondo formule TrainingPeaks:
    - TSS (ciclismo): (sec × NP × IF) / (FTP × 3600) × 100
    - rTSS (corsa): (sec × NGP × IF) / (FTPace × 3600) × 100, dove IF = NGP/FTPace
    - sTSS (nuoto): IF³ × hours × 100, dove IF = NSS/FTPswim
    """
    duration_sec = row.get('Attivita_Durata Totale (sec)', 0) or 0
    duration_h = duration_sec / 3600 if duration_sec > 0 else 0
    sport = str(row.get('Attivita_Tipo Sport', '')).lower()
    
    # ========== CYCLING con potenza ==========
    if 'cycl' in sport:
        np_val = row.get('Attivita_Potenza Normalizzata (W)', 0) or 0
        if np_val > 0 and ftp_bike > 0:
            intensity_factor = np_val / ftp_bike
            # TSS = (sec × NP × IF) / (FTP × 3600) × 100
            return (duration_sec * np_val * intensity_factor) / (ftp_bike * 3600) * 100
    
    # ========== RUNNING con pace ==========
    if 'run' in sport:
        vel_ms = row.get('Attivita_Velocità Media (m/s)', 0) or 0
        dist_km = row.get('Attivita_Distanza (km)', 0) or 0
        
        if vel_ms > 0 and dist_km > 0 and ftp_run > 0:
            # Pace attuale in sec/km
            pace_sec_km = 1000 / vel_ms
            # NGP ≈ pace (senza correzione dislivello per semplicità)
            ngp = pace_sec_km
            # Intensity Factor = FTP_pace / pace_attuale (nota: più veloce = pace più basso = IF più alto)
            # TrainingPeaks usa: IF = NGP / FTP dove NGP è in min/km
            # Più veloce = IF più alto, quindi IF = FTP_pace / pace_attuale
            intensity_factor = ftp_run / ngp
            # rTSS formula
            return (duration_sec * intensity_factor * intensity_factor) / 3600 * 100
        
        # Fallback hrTSS se non c'è pace
        hr = row.get('Attivita_FC Media (bpm)', 0) or 0
        if hr > 0 and lthr > 0:
            hr_ratio = hr / lthr
            return duration_h * (hr_ratio ** 2) * 100
        return duration_h * 70  # Stima generica
    
    # ========== SWIMMING con pace ==========
    if 'swim' in sport:
        vel_ms = row.get('Attivita_Velocità Media (m/s)', 0) or 0
        dist_km = row.get('Attivita_Distanza (km)', 0) or 0
        
        if vel_ms > 0 and dist_km > 0 and ftp_swim > 0:
            # Pace attuale in sec/100m
            pace_sec_100m = 100 / vel_ms
            # NSS = Normalized Swim Speed (usiamo pace medio)
            nss = pace_sec_100m
            # IF = FTP_pace / pace_attuale
            intensity_factor = ftp_swim / nss
            # sTSS = IF³ × hours × 100
            return (intensity_factor ** 3) * duration_h * 100
        
        # Fallback hrTSS
        hr = row.get('Attivita_FC Media (bpm)', 0) or 0
        if hr > 0 and lthr > 0:
            hr_ratio = hr / lthr
            return duration_h * (hr_ratio ** 3) * 100
        return duration_h * 50  # Stima generica nuoto
    
    # ========== ALTRI SPORT (hrTSS) ==========
    hr = row.get('Attivita_FC Media (bpm)', 0) or 0
    if hr > 0 and lthr > 0:
        hr_ratio = hr / lthr
        return duration_h * (hr_ratio ** 2) * 100
    
    return duration_h * 60  # Fallback generico

def generate_prompt(df, df_raw, age, ftp_bike, ftp_run, ftp_swim, lthr):
    """Genera il prompt per l'AI Coach"""
    
    # Prepara date
    df['Date'] = pd.to_datetime(df['Attivita_Data Inizio'])
    df = df.dropna(subset=['Date'])
    df = df.sort_values('Date')
    df['Date'] = df['Date'].dt.normalize()
    
    # Usa TSS nativo Garmin se disponibile, altrimenti calcola
    def get_tss(row):
        # Prima prova TSS nativo da Garmin
        native_tss = row.get('Attivita_TSS', None)
        if pd.notna(native_tss) and native_tss > 0:
            return native_tss
        # Altrimenti calcola
        return calculate_sport_tss(row, ftp_bike, ftp_run, ftp_swim, lthr)
    
    df['TSS'] = df.apply(get_tss, axis=1)
    
    # Calcola PMC (CTL, ATL, TSB) - formula TrainingPeaks
    # CTL = CTL_ieri + (TSS_oggi - CTL_ieri) / 42
    # ATL = ATL_ieri + (TSS_oggi - ATL_ieri) / 7
    import numpy as np
    date_range = pd.date_range(start=df['Date'].min(), end=datetime.now(), freq='D')
    pmc_df = pd.DataFrame({'Date': date_range})
    
    # Aggrega TSS giornaliero
    daily_tss = df.groupby('Date')['TSS'].sum().reset_index()
    pmc_df = pmc_df.merge(daily_tss, on='Date', how='left')
    pmc_df['TSS'] = pmc_df['TSS'].fillna(0)
    
    # Calcola CTL e ATL con formula TrainingPeaks (decay esponenziale)
    # decay_CTL = 1 - 1/42 = ~0.976, decay_ATL = 1 - 1/7 = ~0.857
    ctl_values = []
    atl_values = []
    ctl = 0
    atl = 0
    
    for tss in pmc_df['TSS']:
        ctl = ctl + (tss - ctl) / 42.0
        atl = atl + (tss - atl) / 7.0
        ctl_values.append(ctl)
        atl_values.append(atl)
    
    pmc_df['CTL'] = ctl_values
    pmc_df['ATL'] = atl_values
    pmc_df['TSB'] = pmc_df['CTL'] - pmc_df['ATL']
    
    # Valori attuali
    latest = pmc_df.iloc[-1]
    week_ago = pmc_df.iloc[-8] if len(pmc_df) > 7 else latest
    ramp_rate = latest['CTL'] - week_ago['CTL']
    
    # Ultimi 7 giorni
    last_week = df[df['Date'] >= datetime.now() - timedelta(days=7)]
    weekly_tss = last_week['TSS'].sum()
    
    # Genera descrizione dettagliata degli allenamenti
    workouts = []
    for _, row in last_week.iterrows():
        activity_id = row['ActivityID']
        sport = str(row['Attivita_Tipo Sport']).lower() if pd.notna(row['Attivita_Tipo Sport']) else 'unknown'
        sub_sport = str(row.get('Attivita_Sub Sport', '')).lower() if pd.notna(row.get('Attivita_Sub Sport', '')) else ''
        
        # Nome TSS sport-specific
        if 'swim' in sport:
            tss_name = 'sTSS'
        elif 'run' in sport:
            tss_name = 'rTSS'
        else:
            tss_name = 'TSS'
        
        # Indoor/Outdoor
        indoor = 'Indoor' if 'indoor' in sub_sport or 'virtual' in sub_sport or 'treadmill' in sub_sport else 'Outdoor'
        
        # Durata totale
        dur_sec = row.get('Attivita_Durata Totale (sec)', 0) or 0
        dur_min = int(dur_sec / 60)
        
        # Distanza totale
        dist_km = row.get('Attivita_Distanza (km)', 0) or 0
        
        # Velocità/Passo media
        vel_ms = row.get('Attivita_Velocità Media (m/s)', 0) or 0
        if vel_ms > 0 and dist_km > 0:
            if 'run' in sport or 'walk' in sport:
                pace_sec_per_km = 1000 / vel_ms
                pace_min = int(pace_sec_per_km / 60)
                pace_sec = int(pace_sec_per_km % 60)
                speed_str = f"Passo medio {pace_min}:{pace_sec:02d}/km"
            elif 'swim' in sport:
                pace_sec_per_100m = 100 / vel_ms
                pace_min = int(pace_sec_per_100m / 60)
                pace_sec = int(pace_sec_per_100m % 60)
                speed_str = f"Passo medio {pace_min}:{pace_sec:02d}/100m"
            else:
                speed_kmh = vel_ms * 3.6
                speed_str = f"Vel. media {speed_kmh:.1f} km/h"
        else:
            speed_str = ""
        
        # FC Media
        fc = row.get('Attivita_FC Media (bpm)', 0) or 0
        fc_str = f"FC media {int(fc)} bpm" if fc > 0 else ""
        
        # Potenza (solo ciclismo)
        pwr = row.get('Attivita_Potenza Normalizzata (W)', 0) or 0
        pwr_str = f"NP {int(pwr)}W" if pwr > 0 and 'cycl' in sport else ""
        
        # Riga principale workout
        sport_name = row['Attivita_Tipo Sport'].capitalize() if pd.notna(row['Attivita_Tipo Sport']) else 'Unknown'
        workout_line = f"- {row['Date'].strftime('%Y-%m-%d')}: {sport_name} ({indoor}) - {dur_min}min, {dist_km:.1f}km - {row['TSS']:.0f} {tss_name}"
        details = [x for x in [speed_str, fc_str, pwr_str] if x]
        if details:
            workout_line += f"\n  Medie: {', '.join(details)}"
        
        # DETTAGLIO LAP
        laps = df_raw[df_raw['ActivityID'] == activity_id].sort_values('Numero Lap')
        if len(laps) > 1:
            lap_details = []
            for lap_idx, lap in laps.iterrows():
                lap_num = int(lap.get('Numero Lap', 0))
                lap_dur = lap.get('Durata Lap (sec)', 0) or 0
                lap_dist_m = lap.get('Distanza Lap (m)', 0) or 0
                lap_vel = lap.get('Velocità Media Lap (m/s)', 0) or 0
                lap_fc = lap.get('FC Media Lap (bpm)', 0) or 0
                lap_pwr = lap.get('Potenza Media Lap (W)', 0) or 0
                
                # Formatta durata lap
                lap_dur_min = int(lap_dur / 60)
                lap_dur_sec = int(lap_dur % 60)
                dur_fmt = f"{lap_dur_min}:{lap_dur_sec:02d}"
                
                # Formatta passo/velocità lap
                if lap_vel > 0 and lap_dist_m > 0:
                    if 'run' in sport or 'walk' in sport:
                        pace_sec_km = 1000 / lap_vel
                        pace_m = int(pace_sec_km / 60)
                        pace_s = int(pace_sec_km % 60)
                        pace_fmt = f"{pace_m}:{pace_s:02d}/km"
                    elif 'swim' in sport:
                        pace_sec_100 = 100 / lap_vel
                        pace_m = int(pace_sec_100 / 60)
                        pace_s = int(pace_sec_100 % 60)
                        pace_fmt = f"{pace_m}:{pace_s:02d}/100m"
                    else:
                        pace_fmt = f"{lap_vel * 3.6:.1f}km/h"
                else:
                    pace_fmt = ""
                
                # Componi stringa lap
                lap_info = f"Lap{lap_num}: {dur_fmt}"
                if lap_dist_m > 0:
                    lap_info += f", {lap_dist_m:.0f}m"
                if pace_fmt:
                    lap_info += f", {pace_fmt}"
                if lap_fc > 0:
                    lap_info += f", FC{int(lap_fc)}"
                if lap_pwr > 0 and 'cycl' in sport:
                    lap_info += f", {int(lap_pwr)}W"
                
                lap_details.append(lap_info)
            
            workout_line += f"\n  Lap ({len(lap_details)}): " + " | ".join(lap_details)
        
        workouts.append(workout_line)
    
    # Genera prompt
    prompt = f"""Sono un atleta di {age} anni.

LEGENDA TSS:
- TSS = Training Stress Score (ciclismo con potenza, IF = NP/FTP)
- rTSS = Running Training Stress Score (corsa basato su passo, IF = FTPace/pace)
- sTSS = Swimming Training Stress Score (nuoto basato su passo, IF³ × ore × 100)

{ZONES_BIKE}

{ZONES_RUN}

MIO PIANO SETTIMANALE TIPICO:
- Lunedì: Mattina nuoto tecnica
- Martedì: Mattina bici VO2max, Pausa pranzo palestra parte superiore
- Mercoledì: Mattina ripetute corsa soglia, Pausa pranzo nuoto velocità
- Giovedì: Mattina forza bici, Pausa pranzo palestra parte inferiore
- Venerdì: Mattina corsa zona 2, Pausa pranzo nuoto pull + palette
- Sabato: Mattina lungo bici
- Domenica: Mattina lungo corsa

CARICO ULTIMA SETTIMANA:
- TSS Totale: {weekly_tss:.0f}
- Numero allenamenti: {len(last_week)}

METRICHE PMC (Performance Management Chart):
- CTL (Chronic Training Load / Fitness): {latest['CTL']:.1f}
- ATL (Acute Training Load / Fatigue): {latest['ATL']:.1f}
- TSB (Training Stress Balance / Form): {latest['TSB']:.1f}
- Ramp Rate (Δ CTL/settimana): {ramp_rate:+.1f}

INTERPRETAZIONE PMC:
- TSB > +5: Buona forma, pronto per gare/sforzi intensi
- TSB -10 a +5: Stato di allenamento normale
- TSB < -10: Affaticamento accumulato, considera recupero
- Ramp Rate ideale: 3-8 CTL/settimana
- Ramp Rate > 10: Rischio sovrallenamento

DETTAGLIO ALLENAMENTI ULTIMI 7 GIORNI:
{chr(10).join(workouts) if workouts else "Nessun allenamento"}

RICHIESTA:
Analizza la mia condizione attuale basandoti sui dati PMC e sugli allenamenti specifici (tipologia, intensità, volume). 
Confronta gli allenamenti fatti con il mio piano tipico e suggerisci:
1. Se devo modificare il piano questa settimana in base al mio TSB
2. Intensità e volume consigliati per ogni sessione (indicando le zone)
3. Range di TSS/rTSS/sTSS target per ogni sessione
4. Se c'è bisogno di più recupero o posso caricare di più"""
    
    return prompt

# ============================================================================
# GUI
# ============================================================================

class TrainingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("MyTrainingOS - AI Coach Prompt Generator")
        self.root.geometry("900x700")
        
        self.df = None
        self.df_raw = None
        
        self.setup_ui()
        self.auto_load_file()
    
    def setup_ui(self):
        # Frame parametri
        param_frame = ttk.LabelFrame(self.root, text="Parametri Atleta", padding=10)
        param_frame.pack(fill='x', padx=10, pady=5)
        
        # Riga 1: Età e LTHR
        ttk.Label(param_frame, text="Età:").grid(row=0, column=0, padx=5, sticky='e')
        self.age_var = tk.IntVar(value=DEFAULT_AGE)
        ttk.Entry(param_frame, textvariable=self.age_var, width=8).grid(row=0, column=1, padx=5)
        
        ttk.Label(param_frame, text="LTHR (bpm):").grid(row=0, column=2, padx=5, sticky='e')
        self.lthr_var = tk.IntVar(value=DEFAULT_LTHR)
        ttk.Entry(param_frame, textvariable=self.lthr_var, width=8).grid(row=0, column=3, padx=5)
        
        # Riga 2: FTP per sport
        ttk.Label(param_frame, text="🚴 FTP Bici (W):").grid(row=1, column=0, padx=5, sticky='e')
        self.ftp_bike_var = tk.IntVar(value=DEFAULT_FTP_BIKE)
        ttk.Entry(param_frame, textvariable=self.ftp_bike_var, width=8).grid(row=1, column=1, padx=5)
        
        ttk.Label(param_frame, text="🏃 FTP Corsa (sec/km):").grid(row=1, column=2, padx=5, sticky='e')
        self.ftp_run_var = tk.IntVar(value=DEFAULT_FTP_RUN)
        ttk.Entry(param_frame, textvariable=self.ftp_run_var, width=8).grid(row=1, column=3, padx=5)
        
        ttk.Label(param_frame, text="🏊 FTP Nuoto (sec/100m):").grid(row=1, column=4, padx=5, sticky='e')
        self.ftp_swim_var = tk.IntVar(value=DEFAULT_FTP_SWIM)
        ttk.Entry(param_frame, textvariable=self.ftp_swim_var, width=8).grid(row=1, column=5, padx=5)
        
        # Frame file
        file_frame = ttk.LabelFrame(self.root, text="File Dati / Garmin Connect", padding=10)
        file_frame.pack(fill='x', padx=10, pady=5)
        
        self.file_label = ttk.Label(file_frame, text="Nessun file caricato")
        self.file_label.pack(side='left', padx=5)
        
        ttk.Button(file_frame, text="📁 Carica File", command=self.load_file).pack(side='right', padx=5)
        
        # Bottone Sincronizza Garmin
        if GARMIN_AVAILABLE:
            self.sync_btn = ttk.Button(file_frame, text="🔄 Sincronizza Garmin", command=self.sync_garmin)
            self.sync_btn.pack(side='right', padx=5)
        
        # Bottoni azione
        action_frame = ttk.Frame(self.root, padding=10)
        action_frame.pack(fill='x', padx=10)
        
        ttk.Button(action_frame, text="🔄 Genera Prompt", command=self.generate).pack(side='left', padx=5)
        ttk.Button(action_frame, text="📋 Copia negli Appunti", command=self.copy_to_clipboard).pack(side='left', padx=5)
        
        # Area testo
        self.prompt_text = scrolledtext.ScrolledText(self.root, wrap=tk.WORD, font=('Menlo', 11))
        self.prompt_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Status bar
        self.status_var = tk.StringVar(value="Pronto")
        ttk.Label(self.root, textvariable=self.status_var, relief='sunken').pack(fill='x', side='bottom')
    
    def auto_load_file(self):
        """Cerca automaticamente il file Excel"""
        possible_files = [
            Path(__file__).parent / 'Storico_Allenamenti_Garmin.xlsx',
            Path('/Users/marco/.gemini/antigravity/scratch/garmin_analyzer/Storico_Allenamenti_Garmin.xlsx'),
            Path('/Users/marco/.gemini/antigravity/scratch/Storico_Allenamenti_Garmin.xlsx'),
            Path('/Users/marco/.gemini/antigravity/scratch/mytrainingos/Storico_Allenamenti_Garmin.xlsx'),
        ]
        
        # Se Garmin API disponibile, usa il suo path default
        if GARMIN_AVAILABLE:
            possible_files.insert(0, Path(get_default_excel_path()))
        
        for f in possible_files:
            if f.exists():
                self.load_excel(str(f))
                break
    
    def sync_garmin(self):
        """Sincronizza con Garmin Connect - versione semplificata"""
        if not GARMIN_AVAILABLE:
            messagebox.showerror("Errore", "Modulo Garmin non disponibile")
            return
        
        # Chiedi prima se serve il codice 2FA
        from tkinter import simpledialog
        
        use_2fa = messagebox.askyesno(
            "Autenticazione Garmin",
            "Hai ricevuto un codice di verifica via email da Garmin?"
        )
        
        mfa_code = None
        if use_2fa:
            mfa_code = simpledialog.askstring(
                "Codice Verifica",
                "Inserisci il codice di verifica ricevuto via email:",
                parent=self.root
            )
            if not mfa_code:
                self.status_var.set("❌ Sync annullata")
                return
        
        self.status_var.set("🔄 Sincronizzazione Garmin in corso...")
        self.sync_btn.config(state='disabled')
        self.root.update()
        
        def do_sync():
            try:
                import garth
                import shutil
                import os
                
                # Clear cache
                for p in [os.path.expanduser("~/.garth"), 
                          os.path.expanduser("~/.cache/garth")]:
                    if os.path.exists(p):
                        shutil.rmtree(p)
                
                # Get credentials from keychain
                sys.path.insert(0, GARMIN_MODULE_PATH)
                from keychain_auth import get_credentials
                email, password = get_credentials()
                
                if not email or not password:
                    self.root.after(0, lambda: self._sync_error("Credenziali non trovate in Keychain"))
                    return
                
                # Login (with optional MFA)
                if mfa_code:
                    garth.login(email, password, prompt_mfa=lambda: mfa_code)
                else:
                    garth.login(email, password)
                
                # Download activities
                result = download_and_process()
                self.root.after(0, lambda: self._sync_complete(result))
                
            except Exception as e:
                self.root.after(0, lambda: self._sync_error(str(e)))
        
        thread = threading.Thread(target=do_sync, daemon=True)
        thread.start()
    
    def _sync_complete(self, result):
        """Callback quando sync completata"""
        self.sync_btn.config(state='normal')
        
        if result['success']:
            self.status_var.set(f"✅ Sincronizzato! Nuove: {result['new_activities']}, Lap: {result['total_laps']}")
            # Carica i nuovi dati
            self.load_excel(result['excel_path'])
        else:
            messagebox.showerror("Errore Sync", f"Sincronizzazione fallita:\n{result.get('error', 'Errore sconosciuto')}")
            self.status_var.set("❌ Sync fallita")
    
    def _sync_error(self, error):
        """Callback per errori sync"""
        self.sync_btn.config(state='normal')
        messagebox.showerror("Errore", f"Errore sincronizzazione:\n{error}")
        self.status_var.set("❌ Errore sync")
    
    def load_file(self):
        """Apri dialogo per selezionare file"""
        file_path = filedialog.askopenfilename(
            filetypes=[("Excel files", "*.xlsx *.xls"), ("All files", "*.*")]
        )
        if file_path:
            self.load_excel(file_path)
    
    def load_excel(self, file_path):
        """Carica il file Excel"""
        try:
            self.status_var.set("Caricamento...")
            self.root.update()
            
            self.df, self.df_raw = load_excel_data(file_path)
            self.file_label.config(text=f"✅ {Path(file_path).name} ({len(self.df)} attività)")
            self.status_var.set(f"Caricato: {len(self.df)} attività")
            
            # Genera automaticamente
            self.generate()
            
        except Exception as e:
            messagebox.showerror("Errore", f"Impossibile caricare il file:\n{e}")
            self.status_var.set("Errore caricamento")
    
    def generate(self):
        """Genera il prompt"""
        if self.df is None:
            messagebox.showwarning("Attenzione", "Carica prima un file Excel")
            return
        
        try:
            self.status_var.set("Generazione prompt...")
            self.root.update()
            
            prompt = generate_prompt(
                self.df.copy(), 
                self.df_raw, 
                self.age_var.get(), 
                self.ftp_bike_var.get(),
                self.ftp_run_var.get(),
                self.ftp_swim_var.get(),
                self.lthr_var.get()
            )
            
            self.prompt_text.delete('1.0', tk.END)
            self.prompt_text.insert('1.0', prompt)
            
            self.status_var.set("Prompt generato! Pronto per copia.")
            
        except Exception as e:
            messagebox.showerror("Errore", f"Errore generazione prompt:\n{e}")
            self.status_var.set("Errore generazione")
    
    def copy_to_clipboard(self):
        """Copia il prompt negli appunti"""
        prompt = self.prompt_text.get('1.0', tk.END).strip()
        if prompt:
            try:
                pyperclip.copy(prompt)
                self.status_var.set("✅ Copiato negli appunti!")
            except:
                # Fallback per macOS
                self.root.clipboard_clear()
                self.root.clipboard_append(prompt)
                self.status_var.set("✅ Copiato negli appunti!")

# ============================================================================
# MAIN
# ============================================================================

if __name__ == "__main__":
    root = tk.Tk()
    app = TrainingApp(root)
    root.mainloop()
