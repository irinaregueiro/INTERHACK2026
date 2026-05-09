# Customer Twin — Smart Demand Signals

Probabilistic digital-twin system for `(cliente, familia de producto)` pairs
on top of an Inibsa-style sales dataset. The twin learns expected purchase
behaviour, detects statistically significant divergences, surfaces a causal
narrative, and routes the alert through a contextual bandit that recommends
the next commercial action.

The output is a single-screen web dashboard with a prioritized list of
actionable alerts, confidence-band charts, and an optional voice briefing.

---

## Architecture

```
Datasets.xlsx
      │
      ▼
┌──────────────┐   ┌──────────────────────┐   ┌──────────────────────┐
│  ETL (1)     │ → │  Twins (2)           │ → │  Signal detector (3) │
│  weekly      │   │  Poisson-Gamma       │   │  6-type taxonomy     │
│  aggregates  │   │  IPT log-normal      │   │  urgency scoring     │
│  campaign    │   │  Weibull fallback    │   │  narrative templates │
│  masking     │   │  maturity index      │   └──────────┬───────────┘
└──────────────┘   └──────────────────────┘              │
                                                         ▼
                                  ┌──────────────────────────────┐
                                  │  Bandit (4) Thompson Sampling│
                                  │  Beta(α, β) per (seg, arm)   │
                                  └──────────────┬───────────────┘
                                                 │
                                                 ▼
                                  ┌──────────────────────────────┐
                                  │  FastAPI + React (5)         │
                                  │  /api/signals, /detail, …    │
                                  │  Chart.js confidence bands   │
                                  └──────────────────────────────┘
```

| Layer | Where it lives |
|-------|----------------|
| ETL | `etl/pipeline.py`, `etl/mappings.py`, `etl/validators.py` |
| Twins | `models/twin_commodity.py`, `models/twin_technical.py` |
| Signal detector + narrative | `models/signal_detector.py`, `models/narrative.py` |
| Bandit + scoring + voice | `api/bandit.py`, `api/scoring.py`, `api/voice.py` |
| API | `api/main.py` |
| Schemas | `shared/schemas.py` |
| Frontend | `frontend/` (Vite + React + Chart.js, plain CSS) |

---

## Setup

### 1. Backend (Python 3.10+)

```bash
cd customer-twin
python -m pip install -r requirements.txt
```

Place the source spreadsheet at `data/raw/Datasets.xlsx` (sheets: `Ventas`,
`Productos`, `Clientes`, `Potencial`, `Campañas`).

### 2. Run the ETL once

```bash
python -m etl.pipeline
# writes data/processed/{client_category_week,sow_potencial,precio_medio_categoria}.parquet
```

### 3. Start the API

```bash
python -m uvicorn api.main:app --reload --port 8000
# OpenAPI docs at http://127.0.0.1:8000/docs
# Health check at  http://127.0.0.1:8000/api/health
```

When `data/processed/client_category_week.parquet` is missing, the API
falls back to a small bundled mock dataset. Responses include
`X-Data-Source: mock` so the dashboard can show a banner.

### 4. Start the frontend

```bash
cd frontend
npm install
npm run dev
# http://127.0.0.1:5173
```

The dev server proxies `/api/*` to `http://127.0.0.1:8000`. Override with
`API_BASE` env var, e.g. `API_BASE=http://other-host:9000 npm run dev`.

If the backend is unreachable the frontend automatically shows bundled mock
signals (`src/api/mockSignals.json`). Real and mock paths use exactly the
same JSON shape.

---

## Environment variables

| Var | Default | Purpose |
|-----|---------|---------|
| `ELEVENLABS_API_KEY` | (unset) | Required to enable the voice briefing endpoint. When missing, `/voice_briefing` returns HTTP 503 `{"error": "voice_disabled"}` and the frontend hides the audio player. |
| `ELEVENLABS_VOICE_ID` | `21m00Tcm4TlvDq8ikWAM` | ElevenLabs voice ID. |
| `CT_MAX_CLIENTS` | `1500` | Cap on number of clients processed at startup. Lower for snappier dev cycles, higher for production runs. |

No secrets are hardcoded anywhere in the codebase.

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| `GET`  | `/api/health` | Status + data source + voice availability |
| `GET`  | `/api/signals?tipo=&bloque=&provincia=&limit=` | Active signals, sorted by urgency desc |
| `GET`  | `/api/signals/counts` | Counts by tipo / bloque / madurez |
| `GET`  | `/api/signals/{id}/detail` | Signal + 16-week chart history + bandit recommendation |
| `POST` | `/api/signals/{id}/feedback` | Body: `{action, outcome}` (`outcome ∈ {acted, false_alarm, priority_up}`) |
| `POST` | `/api/signals/{id}/voice_briefing` | ElevenLabs MP3 (returns 503 if `ELEVENLABS_API_KEY` unset) |
| `GET`  | `/api/audio/{filename}` | Serves cached audio MP3s |
| `GET`  | `/api/territorial_alerts?weeks=&min_count=` | Provinces with ≥N FUGA_PARCIAL alerts (heatmap input) |
| `POST` | `/api/admin/reload` | Re-run detection from disk after re-running ETL |

All `signal_id` values are raw strings of the form
`<id_cliente>|<categoria_h>|<tipo>` and **must** be percent-encoded when
embedded in URL paths. `encodeURIComponent(signal_id)` is sufficient on the
frontend.

---

## Demo flow

1. **Open the dashboard** at `http://127.0.0.1:5173`.
2. The top of the list shows **FUGA_PARCIAL_COMMODITY** alerts (real
   losses) interleaved with **DEMANDA_NO_CAPTURADA** opportunities, sorted
   by urgency.
3. **Click a row** — the right panel loads the signal detail.
4. The chart shows the last 16 weeks of weekly units, the predictive band
   `[P5, P95]`, and the expected line. Out-of-band points are coloured red.
5. The narrative box explains the signal in **probabilistic language**
   ("compatible con", "indicios de", "hipótesis principal"). The system
   never claims fuga or churn as confirmed.
6. The bandit bars show the Thompson-Sampled probability mass per arm. The
   recommended action is highlighted with a star.
7. Click **"Voy a actuar"** to register a positive reward — the bandit
   updates and the bars on the next click reflect the change.
8. Click **"Briefing de voz"** to play an ElevenLabs MP3 of the narrative
   (only if `ELEVENLABS_API_KEY` is set).
9. **Filter** by signal type or bloque from the left sidebar.

---

## Data contracts

The single source of truth is `shared/schemas.py`:

- `ClientFamilyWeek` — output of ETL → input to twins
- `Signal` — output of detector → input to bandit/API
- `BanditRecommendation` — output of bandit → frontend

`id_cliente` is **string** everywhere (raw IDs mix short/long numeric forms
with potential leading zeros). `signal_id` is the deterministic composite
`{id_cliente}|{categoria_h}|{tipo}`.

---

## Modelling notes

- **Commodity twin** (Categoria C1, C2). Likelihood `Poisson(λ)`, prior
  `Gamma(α, β)`, predictive `NegBin(α + ΣY, β/(β+1))`. Cold-start clients
  use a low-precision prior centred on the family-wide mean (computed at
  detection time, not stored).
- **Technical twin** (Categoria T1). `log(IPT) ~ N(μ, σ²)` for ≥4 events,
  `Weibull` MLE otherwise. Deterioration requires silence > P90 **AND**
  positive slope on last 3-4 IPTs **AND** no recent campaign.
- **Maturity index** (Alto/Medio/Bajo) gates which signals fire — Bajo
  blocks deterioration alerts; only "absence" alerts are emitted.
- **Urgency** `U = 0.5·impacto + 0.3·persistencia + 0.2·madurez`, where
  impacto monetizes DNC with `precio_medio` (€/u.) per categoria, computed
  during ETL.
- **Bandit** Beta-Bernoulli Thompson Sampling, segment key
  `<tipo>|<madurez>|<magnitud>`. Pre-seeded with ~50 deterministic
  synthetic interactions so the demo shows non-trivial preferences from
  the first click. Real updates come through `/api/signals/{id}/feedback`.

---

## Known limitations

- **Potencial declarado** is sometimes inconsistent (annualized
  observation > declared potencial). Mitigated with the
  `potencial_fiable` flag (= true iff `annualized_sales ≤ 1.2 × potencial`).
  Clients with `potencial_fiable=False` still receive deterioration alerts
  but are excluded from `DEMANDA_NO_CAPTURADA`.
- **Competition is not observable.** Fuga signals are probabilistic
  inferences, never certainties. The narrative templates and product copy
  reflect this consistently.
- **Bandit cold-start** uses uniform `Beta(1, 1)` priors. Probabilities are
  orientative until ~30 real interactions per `(segmento, arm)` accumulate.
  The demo seeding is a stand-in for that history; real users replace it
  via the feedback endpoint.
- **Mapping (Familia → Categoria)** was confirmed from the dataset itself
  (`Anestesia → C1`, `Bioseguridad → C2`, `Biomateriales → T1`) — an
  earlier mapping that suggested Biomateriales also feeds C2 was not
  observed in the data and is not used.
- **Static historical snapshot.** "Today" defaults to the last semana in
  the dataset + 7 days. Stream/incremental ingestion is out of scope for
  the MVP.
- **Voice briefings are cached on disk** under `data/audio_cache/` keyed by
  `sha1(text|voice_id)`. The cache is not garbage-collected — clear
  manually if you change voice settings.

---

## Repository structure

```
customer-twin/
├── data/
│   ├── raw/Datasets.xlsx       (gitignored)
│   ├── processed/              (parquet outputs, gitignored)
│   └── audio_cache/            (ElevenLabs MP3 cache, gitignored)
├── etl/
│   ├── pipeline.py             python -m etl.pipeline
│   ├── mappings.py             sheet/column constants + thresholds
│   └── validators.py           sanity checks
├── models/
│   ├── twin_commodity.py       Poisson-Gamma → NegBin predictive
│   ├── twin_technical.py       log-normal IPT (Weibull fallback)
│   ├── signal_detector.py      6-signal taxonomy + urgency
│   └── narrative.py            deterministic Spanish templates
├── api/
│   ├── main.py                 FastAPI app
│   ├── bandit.py               Thompson Sampling
│   ├── scoring.py              urgency rescoring helper
│   ├── voice.py                ElevenLabs synth (env-var, cached)
│   └── demo_signals.py         mock fallback set
├── shared/
│   └── schemas.py              ClientFamilyWeek, Signal, BanditRecommendation
├── frontend/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/         TopBar, Sidebar, AlertList, DetailPanel,
│   │   │                       ConfidenceChart, BanditBars
│   │   ├── api/                client + bundled mock signals
│   │   └── styles/globals.css  plain CSS with variables
│   ├── vite.config.js
│   └── package.json
├── requirements.txt
├── .gitignore
└── README.md
```
