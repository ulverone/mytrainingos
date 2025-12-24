"""
MyTrainingOS - TrainingPeaks-like Dashboard
Versione semplificata e funzionante
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import datetime, timedelta
from pathlib import Path

st.set_page_config(layout="wide", page_title="MyTrainingOS", page_icon="🏃")

# ============================================================================
# FUNZIONI
# ============================================================================

def load_excel_data(file_path):
    """Carica il file Excel, ritorna dati deduplucati e dati lap grezzi"""
    df_raw = pd.read_excel(file_path)
    # Deduplica: una riga per activity (per calcoli PMC)
    df = df_raw.groupby('ActivityID').first().reset_index()
    return df, df_raw

def calculate_sport_tss(row, ftp, lthr):
    """Calcola TSS sport-specific"""
    duration_h = row['Attivita_Durata Totale (sec)'] / 3600 if pd.notna(row['Attivita_Durata Totale (sec)']) else 0
    sport = str(row['Attivita_Tipo Sport']).lower() if pd.notna(row['Attivita_Tipo Sport']) else ''
    
    # CYCLING con potenza
    if 'cycl' in sport:
        np_val = row['Attivita_Potenza Normalizzata (W)']
        if pd.notna(np_val) and np_val > 0 and ftp > 0:
            intensity_factor = np_val / ftp
            return (row['Attivita_Durata Totale (sec)'] * np_val * intensity_factor) / (ftp * 36)
    
    # RUNNING: rTSS quadratico
    if 'run' in sport:
        hr = row['Attivita_FC Media (bpm)']
        if pd.notna(hr) and hr > 0 and lthr > 0:
            return duration_h * ((hr / lthr) ** 2) * 100
        return duration_h * 70
    
    # SWIMMING: sTSS cubico
    if 'swim' in sport:
        hr = row['Attivita_FC Media (bpm)']
        if pd.notna(hr) and hr > 0 and lthr > 0:
            return duration_h * ((hr / lthr) ** 3) * 100
        return duration_h * 50
    
    # ALTRI sport: HR generico
    hr = row['Attivita_FC Media (bpm)']
    if pd.notna(hr) and hr > 0 and lthr > 0:
        return duration_h * ((hr / lthr) ** 2) * 100
    
    return duration_h * 60

def calculate_pmc(daily_tss_series):
    """Calcola CTL, ATL, TSB da serie giornaliera"""
    ctl = daily_tss_series.ewm(span=42, adjust=False).mean()
    atl = daily_tss_series.ewm(span=7, adjust=False).mean()
    tsb = ctl - atl
    return ctl, atl, tsb

# ============================================================================
# SIDEBAR
# ============================================================================

with st.sidebar:
    st.title("⚙️ Configurazione")
    
    ftp = st.number_input("🚴 FTP (W)", 50, 500, 250, 5)
    lthr = st.number_input("❤️ LTHR (bpm)", 100, 220, 160, 1)
    age = st.number_input("👤 Età", 18, 100, 30, 1)
    
    st.divider()
    uploaded_file = st.file_uploader("📁 Carica file", type=['xlsx', 'xls'])

# ============================================================================
# MAIN
# ============================================================================

st.markdown("# 🏃 MyTrainingOS")
st.markdown("### Performance Management Dashboard")

# Trova file
script_dir = Path(__file__).parent.resolve()
file_path = None

if uploaded_file:
    file_path = uploaded_file
else:
    # Cerca nella directory dello script
    local_file = script_dir / 'Storico_Allenamenti_Garmin.xlsx'
    if local_file.exists():
        file_path = str(local_file)
    else:
        st.error(f"❌ File non trovato in: {script_dir}")

if not file_path:
    st.warning("⚠️ Carica un file Excel dalla sidebar")
    st.stop()

# Carica dati
with st.spinner("Caricamento..."):
    df, df_raw = load_excel_data(file_path)
    
    # Calcola TSS
    df['TSS'] = df.apply(lambda row: calculate_sport_tss(row, ftp, lthr), axis=1)
    
    # Prepara date
    df['Date'] = pd.to_datetime(df['Attivita_Data Inizio'])
    df = df.dropna(subset=['Date'])
    df = df.sort_values('Date')
    
    # Normalizza date a mezzanotte per aggregazione giornaliera
    df['Date'] = df['Date'].dt.normalize()
    
    # Aggrega TSS giornaliero
    daily_tss = df.groupby('Date')['TSS'].sum().reset_index()
    
    # Crea range continuo
    date_range = pd.date_range(start=df['Date'].min(), end=datetime.now(), freq='D')
    pmc_df = pd.DataFrame({'Date': date_range})
    
    # Merge con merge (non con index)
    pmc_df = pmc_df.merge(daily_tss, on='Date', how='left')
    pmc_df['TSS'] = pmc_df['TSS'].fillna(0)
    
    # Calcola PMC
    pmc_df['CTL'], pmc_df['ATL'], pmc_df['TSB'] = calculate_pmc(pmc_df['TSS'])

# KPI
st.subheader("📊 Metriche Correnti")
latest = pmc_df.iloc[-1]
week_ago = pmc_df.iloc[-8] if len(pmc_df) > 7 else latest

col1, col2, col3, col4 = st.columns(4)
col1.metric("💪 CTL", f"{latest['CTL']:.1f}")
col2.metric("😴 ATL", f"{latest['ATL']:.1f}")
col3.metric("⚡ TSB", f"{latest['TSB']:.1f}")
col4.metric("📈 Ramp", f"{(latest['CTL'] - week_ago['CTL']):+.1f}")

# Filtro date
st.divider()
c1, c2 = st.columns(2)
start_date = c1.date_input("Data Inizio", datetime.now() - timedelta(days=90))
end_date = c2.date_input("Data Fine", datetime.now())

# Filtra
mask = (pmc_df['Date'] >= pd.Timestamp(start_date)) & (pmc_df['Date'] <= pd.Timestamp(end_date))
plot_df = pmc_df[mask]

# Grafico
st.subheader("📈 Performance Management Chart")

fig = go.Figure()

# TSB area
fig.add_trace(go.Scatter(
    x=plot_df['Date'], y=plot_df['TSB'],
    fill='tozeroy', name='TSB (Form)',
    line=dict(color='rgba(158,158,158,0.5)', width=1),
    fillcolor='rgba(158,158,158,0.2)'
))

# CTL
fig.add_trace(go.Scatter(
    x=plot_df['Date'], y=plot_df['CTL'],
    name='CTL (Fitness)', line=dict(color='#1E88E5', width=3)
))

# ATL
fig.add_trace(go.Scatter(
    x=plot_df['Date'], y=plot_df['ATL'],
    name='ATL (Fatigue)', line=dict(color='#E91E63', width=3)
))

# TSS bars
fig.add_trace(go.Bar(
    x=plot_df['Date'], y=plot_df['TSS'],
    name='TSS Giornaliero', marker=dict(color='rgba(100,181,246,0.5)'),
    yaxis='y2'
))

fig.update_layout(
    title="Andamento Performance Management",
    xaxis=dict(title="Data"),
    yaxis=dict(title="CTL / ATL / TSB", side='left'),
    yaxis2=dict(title="TSS", side='right', overlaying='y'),
    hovermode='x unified',
    template='plotly_white',
    height=600,
    legend=dict(orientation="h", y=1.02, x=1, xanchor="right")
)

st.plotly_chart(fig, use_container_width=True)

# AI Prompt
st.divider()
st.subheader("🤖 AI Coach Analysis Export")

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
    workout_line = f"- {row['Date'].strftime('%Y-%m-%d')}: {row['Attivita_Tipo Sport'].capitalize()} ({indoor}) - {dur_min}min, {dist_km:.1f}km - {row['TSS']:.0f} {tss_name}"
    details = [x for x in [speed_str, fc_str, pwr_str] if x]
    if details:
        workout_line += f"\n  Medie: {', '.join(details)}"
    
    # DETTAGLIO LAP
    laps = df_raw[df_raw['ActivityID'] == activity_id].sort_values('Numero Lap')
    if len(laps) > 1:  # Solo se ci sono più lap
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
        
        # Mostra tutti i lap
        workout_line += f"\n  Lap ({len(lap_details)}): " + " | ".join(lap_details)
    
    workouts.append(workout_line)

prompt = f"""Sono un atleta di {age} anni.

LEGENDA TSS:
- TSS = Training Stress Score (ciclismo con potenza)
- rTSS = Running Training Stress Score (corsa basato su FC)
- sTSS = Swimming Training Stress Score (nuoto basato su FC)

MIO PIANO SETTIMANALE TIPICO:
- Lunedì: Mattina nuoto tecnica
- Martedì: Mattina bici VO2max, Pausa pranzo palestra parte superiore
- Mercoledì: Mattina ripetute corsa soglia, Pausa pranzo nuoto velocità
- Giovedì: Mattina forza bici, Pausa pranzo palestra parte inferiore
- Venerdì: Mattina corsa zona 2, Pausa pranzo nuoto pull + palette
- Sabato: Mattina lungo bici
- Domenica: Mattina lungo corsa

METRICHE PMC ATTUALI:
- CTL (Chronic Training Load / Fitness): {latest['CTL']:.1f}
- ATL (Acute Training Load / Fatigue): {latest['ATL']:.1f}
- TSB (Training Stress Balance / Form): {latest['TSB']:.1f}
- Ramp Rate (Δ CTL/settimana): {(latest['CTL'] - week_ago['CTL']):+.1f}

CARICO ULTIMA SETTIMANA:
- TSS Totale: {weekly_tss:.0f}
- Numero allenamenti: {len(last_week)}

DETTAGLIO ALLENAMENTI ULTIMI 7 GIORNI:
{chr(10).join(workouts) if workouts else "Nessun allenamento"}

INTERPRETAZIONE METRICHE:
- TSB > +5: Buona forma, pronto per gare/sforzi intensi
- TSB -10 a +5: Stato di allenamento normale
- TSB < -10: Affaticamento accumulato, considera recupero
- Ramp Rate ideale: 3-8 CTL/settimana
- Ramp Rate > 10: Rischio sovrallenamento

RICHIESTA:
Analizza la mia condizione attuale basandoti sui dati PMC e sugli allenamenti specifici (tipologia, intensità, volume). 
Confronta gli allenamenti fatti con il mio piano tipico e suggerisci:
1. Se devo modificare il piano questa settimana in base alla mia forma (TSB)
2. Intensità e volume consigliati per ogni sessione
3. Range di TSS/rTSS/sTSS target per ogni sessione
4. Se c'è bisogno di più recupero o posso caricare di più"""

st.code(prompt, language=None)

# Riepilogo
st.divider()
st.subheader("📊 Riepilogo")
c1, c2, c3 = st.columns(3)
c1.metric("Allenamenti", len(df))
c2.metric("Ore Totali", f"{df['Attivita_Durata Totale (sec)'].sum()/3600:.0f}h")
c3.metric("TSS Totale", f"{df['TSS'].sum():.0f}")

with st.expander("📋 Ultimi 10 Allenamenti"):
    recent = df.tail(10)[['Date', 'Attivita_Tipo Sport', 'TSS']].copy()
    recent['Date'] = recent['Date'].dt.strftime('%Y-%m-%d')
    recent['TSS'] = recent['TSS'].apply(lambda x: f"{x:.0f}")
    recent.columns = ['Data', 'Sport', 'TSS']
    st.dataframe(recent.iloc[::-1], use_container_width=True, hide_index=True)
