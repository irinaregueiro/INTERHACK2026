# INTERHACK 2026 - Customer Twin

Benvingut al repositori principal del projecte **Customer Twin** creat per a l'Inibsa Hackathon (Smart Demand Signals). Aquest projecte conté és de caràcter probabilístic per a analitzar i predir el comportament de clients en base a sèries temporals de vendes.

Tota la lògica de l'aplicació, el Backend (FastAPI) i el Frontend (React + Vite) viuen dins del directori `customer-twin/`.

## Com provar el projecte localment

L'aplicació està estructurada per funcionar completament en el teu ordinador de manera senzilla, o bé es pot desplegar amb Docker/Vultr.

### 1. Requisits previs
- **Python 3.10+**
- **Node.js i npm**
- **Dataset Original**: Has de col·locar l'arxiu `Datasets.xlsx` proporcionat per Inibsa a la ruta:
  `customer-twin/data/raw/Datasets.xlsx`

### 2. Procés ETL (Processament de Dades)
Abans d'engegar l'API, cal pre-processar les dades de l'Excel en arxius Parquet més ràpids.
```bash
cd customer-twin
python -m pip install -r requirements.txt
python -m etl.pipeline
```
Això crearà diversos arxius `.parquet` a `data/processed/`. **Aquest pas només s'ha de fer una vegada.**

### 3. Arrencar l'API (Backend)
```bash
cd customer-twin
python -m uvicorn api.main:app --reload --port 8000
```
L'API serà accessible a `http://127.0.0.1:8000`.

*(Opcional: Si vols àudio/briefings per veu, crea un arxiu `.env` dins de `customer-twin/` afegint-hi `ELEVENLABS_API_KEY=el_teu_token`).*

### 4. Arrencar el Dashboard (Frontend)
Obre un altre terminal:
```bash
cd customer-twin/frontend
npm install
npm run dev
```
Ara pots obrir el teu navegador a **[http://127.0.0.1:5173](http://127.0.0.1:5173)** i gaudir de l'aplicació!

## Desplegament
El repositori ja està configurat per ser publicat al núvol (Vultr) mitjançant GitHub Actions. Les accions es llancen de forma automàtica cada vegada que s'envien canvis a la branca `main`.
Pots veure l'arxiu de CI/CD a `.github/workflows/deploy-vultr.yml` i la configuració Dockeritzada dins de `docker-compose.yml`.
