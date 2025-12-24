# 🏃 MyTrainingOS

Una dashboard TrainingPeaks-like per analizzare i tuoi allenamenti Garmin con metriche PMC (Performance Management Chart).

## ✨ Caratteristiche

- 📊 **Calcolo TSS Automatico**: Calcola automaticamente il Training Stress Score basato su potenza, frequenza cardiaca o durata
- 📈 **Performance Management Chart**: Visualizza CTL (Fitness), ATL (Fatigue) e TSB (Form)
- 🎯 **Metriche in Tempo Reale**: KPI aggiornati su fitness, fatica e forma attuale
- 🤖 **AI Coach Integration**: Genera prompt per analisi AI personalizzate
- 🎨 **Interfaccia Moderna**: Dashboard interattiva con grafici Plotly
- 🖱️ **Point & Click**: Lancia l'app con un doppio click, niente comandi da terminale!

## 🚀 Setup Iniziale (Una Tantum)

### 1. Installa Python

Se non hai Python installato, scaricalo da [python.org](https://www.python.org/downloads/) (versione 3.8+)

### 2. Installa le Dipendenze

Apri il Terminale nella cartella del progetto e digita:

```bash
pip install -r requirements.txt
```

### 3. Rendi Eseguibile il Launcher (Solo macOS)

**IMPORTANTE**: Questo passaggio va fatto solo la prima volta!

Nel Terminale, digita:

```bash
chmod +x Launch_MyTraining.command
```

✅ Fatto! Non dovrai più usare il Terminale.

## 🎯 Come Usare

### Metodo 1: Launcher (Consigliato)

1. **Doppio click** su `Launch_MyTraining.command`
2. Il browser si aprirà automaticamente con la dashboard
3. Carica il tuo file CSV di Garmin
4. Inizia ad analizzare!

### Metodo 2: Manuale (da Terminale)

```bash
streamlit run app.py
```

## 📁 Preparare i Dati

### Esportare da Garmin Connect

1. Vai su [Garmin Connect](https://connect.garmin.com)
2. Esporta lo storico allenamenti come CSV
3. Salva il file come: `Storico_Allenamenti_Garmin.xlsx - Storico Allenamenti Completo.csv`
4. Metti il file nella stessa cartella di `app.py` (oppure caricalo tramite l'interfaccia)

### Formato Dati Richiesto

Il CSV deve contenere queste colonne (nomi italiani):

- `Attivita_Data Inizio`
- `Attivita_Tipo Sport`
- `Attivita_Durata Totale (sec)`
- `Attivita_Potenza Normalizzata (W)` (opzionale)
- `Attivita_FC Media (bpm)` (opzionale)
- `Attivita_Potenza Media (W)` (opzionale)
- `Attivita_Distanza (km)` (opzionale)

## ⚙️ Configurazione

### FTP (Functional Threshold Power)

Imposta la tua soglia di potenza funzionale per il calcolo accurato del TSS nel ciclismo.

- **Default**: 250W
- **Come trovarla**: Fai un test FTP di 20 minuti (95% della potenza media)

### LTHR (Lactate Threshold Heart Rate)

Imposta la tua soglia lattacida per calcolare il TSS da frequenza cardiaca.

- **Default**: 160 bpm
- **Come trovarla**: Test di 30 minuti a massimo sforzo sostenibile (media ultimi 20 min)

## 📊 Interpretazione Metriche

### CTL (Chronic Training Load / Fitness)

- Misura il tuo allenamento a lungo termine (ultimi 42 giorni)
- **Più alto** = Più in forma
- Aumenta lentamente per evitare infortuni

### ATL (Acute Training Load / Fatigue)

- Misura il carico recente (ultimi 7 giorni)
- **Più alto** = Più affaticato
- Varia settimana per settimana

### TSB (Training Stress Balance / Form)

- **TSB > +5**: Buona forma, pronto per gare/allenamenti intensi
- **TSB tra -10 e +5**: Stato neutro, carico gestibile
- **TSB < -10**: Affaticamento, considera il recupero

### Ramp Rate

- Variazione CTL settimanale
- **Ideale**: 3-8 punti/settimana
- **> 10**: Rischio sovrallenamento

## 🤖 AI Coach

Usa la sezione "AI Analysis Export" per:

1. Copiare il testo generato
2. Incollarlo in ChatGPT, Claude o Gemini
3. Ricevere consigli personalizzati sulla tua pianificazione

## 🛠️ Risoluzione Problemi

### Il file .command non si apre

```bash
chmod +x Launch_MyTraining.command
```

### Errore "Streamlit not found"

```bash
pip install streamlit
```

### Il CSV non viene caricato

- Verifica che il file sia in formato CSV (non Excel)
- Controlla che i nomi delle colonne corrispondano
- Prova a caricare il file tramite l'interfaccia invece di metterlo nella cartella

### Il browser non si apre automaticamente

Vai manualmente su: `http://localhost:8501`

## 📝 Note Tecniche

### Stack Tecnologico

- **Python 3.8+**
- **Streamlit**: Framework web per dashboard
- **Pandas**: Manipolazione dati
- **NumPy**: Calcoli numerici
- **Plotly**: Grafici interattivi

### Calcolo TSS

Il sistema usa una logica a cascata:

1. **Power-based** (cycling con NP): `TSS = (Duration * NP * IF) / (FTP * 36)`
2. **HR-based** (qualsiasi sport con FC): Stima basata su intensità
3. **Duration-based** (fallback): `TSS = Duration_hours * 60`

### PMC Calculations

- **CTL**: EWMA con span=42 giorni
- **ATL**: EWMA con span=7 giorni
- **TSB**: CTL - ATL

## 📄 Licenza

Questo progetto è per uso personale.

## 🙏 Credits

Sviluppato con ❤️ per gli atleti endurance che vogliono migliorare le loro performance.

---

**Happy Training! 🏃‍♂️🚴‍♀️🏊‍♂️**
