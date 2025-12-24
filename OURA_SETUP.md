# MyTrainingOS - Oura Ring Integration

## Setup Oura OAuth2

### Passo 1: Registra l'applicazione Oura

1. Vai su **<https://cloud.ouraring.com/oauth/applications>**
2. Clicca su **"New Application"**
3. Compila:
   - **Application Name**: `MyTrainingOS`
   - **Redirect URI**: `http://localhost:8888/callback`
   - **Description**: Personal training app
4. Salva e copia:
   - `Client ID`
   - `Client Secret`

### Passo 2: Configura le credenziali

Dopo aver creato l'app Oura, esegui:

```bash
cd /Users/marco/.gemini/antigravity/scratch/mytrainingos
python3 oura_sync.py --setup
```

Ti chiederà Client ID e Client Secret, poi aprirà il browser per autorizzare l'app.

### Passo 3: Sincronizza i dati

```bash
python3 oura_sync.py
```

I dati verranno salvati in `data/oura.json` e caricati automaticamente in MyTrainingOS.

## Dati disponibili

| Metrica | Descrizione |
|---------|-------------|
| Sleep Score | Qualità del sonno (0-100) |
| Readiness Score | Prontezza fisica (0-100) |
| HRV | Variabilità cardiaca (ms) |
| Resting HR | Frequenza cardiaca a riposo |
| Body Temperature | Deviazione temperatura corporea |
| Activity Score | Punteggio attività giornaliera |

## Correlazione con PMC

- **TSB alto + Readiness alto** = Pronto per gara
- **TSB basso + Readiness basso** = Necessita recupero
- **HRV in calo** = Possibile sovrallenamento
