# Customer Twin — Plan de Desarrollo

## Información del equipo

- **Tamaño del equipo:** 4 personas
- **Duración estimada:** ~24h (formato hackathon)
- **Stack global:** Python (pandas, scipy, numpy, FastAPI), React + Chart.js, ElevenLabs API
- **Repositorio sugerido:** estructura de monorepo con carpetas `data/`, `etl/`, `models/`, `api/`, `frontend/`

---

## Estructura del repositorio

```
customer-twin/
├── data/                          # Datos crudos y procesados (gitignore para crudos)
│   ├── raw/                       # Datasets.xlsx original
│   └── processed/                 # Outputs intermedios (parquet)
├── etl/                           # Persona 1
│   ├── pipeline.py
│   ├── mappings.py
│   └── validators.py
├── models/                        # Persona 2
│   ├── twin_commodity.py
│   ├── twin_technical.py
│   ├── signal_detector.py
│   └── narrative.py
├── api/                           # Persona 3
│   ├── main.py                    # FastAPI app
│   ├── bandit.py
│   ├── scoring.py
│   └── voice.py                   # ElevenLabs integration
├── frontend/                      # Persona 4
│   ├── src/
│   │   ├── App.jsx
│   │   ├── components/
│   │   └── api/
│   └── package.json
├── shared/
│   └── schemas.py                 # Contratos de datos compartidos (Pydantic)
└── README.md
```

---

## Contratos de datos compartidos

**Crítico:** definir esto en la primera hora colectivamente. Cada persona implementa contra estos contratos con mocks hasta que la integración sea posible.

### Schema 1: `client_family_week` (output de ETL → input de modelos)

```python
# Definido en shared/schemas.py
class ClientFamilyWeek(BaseModel):
    id_cliente: int
    categoria_h: str          # 'Categoria C1' | 'Categoria C2' | 'Categoria T1'
    bloque: str               # 'Commodities' | 'Productos Técnicos'
    semana: date              # Lunes de la semana ISO
    unidades_netas: float     # Suma de unidades, devoluciones restadas
    valor_neto: float
    is_campaign: bool         # True si la semana cae en ventana de campaña
    n_facturas: int
    provincia: str
```

### Schema 2: `signal` (output de modelos → input de bandit/API)

```python
class Signal(BaseModel):
    id_cliente: int
    categoria_h: str
    tipo: Literal[
        'FUGA_PARCIAL_COMMODITY',
        'DEMANDA_NO_CAPTURADA',
        'DETERIORO_SOSTENIDO_TECNICO',
        'PAUSA_SOSPECHOSA',
        'CAMPAIGN_NO_RESPONSE',
        'SEÑAL_CRUZADA_NEGATIVA'
    ]
    semanas_fuera_banda: int
    captura_actual: float | None      # Solo para commodities
    captura_historica: float | None
    dnc_estimada: float | None
    expected_value: float
    observed_value: float
    confidence_band: tuple[float, float]
    indice_madurez: Literal['Alto', 'Medio', 'Bajo']
    score_urgencia: float
    narrativa: str
    timestamp: datetime
```

### Schema 3: `bandit_recommendation` (output del bandit → frontend)

```python
class BanditRecommendation(BaseModel):
    signal_id: str
    action_probabilities: dict[str, float]  # {'visita': 0.73, 'llamada': 0.18, ...}
    recommended_action: str
    confidence: float                       # 0-1, alto = bandit ya tiene señal clara
```

### Mapping de familias (crítico — definir en hora 1)

```python
# Análisis confirmado sobre los datos:
# El nivel correcto de agregación es Categoria_H, no Familia_H.
# El potencial está dado por (cliente, Familia, Categoria Productos).

CATEGORIA_TO_BLOQUE = {
    'Categoria C1': 'Commodities',      # Anestesia
    'Categoria C2': 'Commodities',      # Biomateriales (parcial) + Bioseguridad
    'Categoria T1': 'Productos Técnicos' # Biomateriales (parcial)
}

# El cruce de potencial se hace por (id_cliente, Categoria Productos)
# El cruce de ventas se hace por (id_cliente, Categoria_H del producto)
```

---

## División de tareas

### Persona 1 — Data Engineer (ETL)

**Responsabilidad:** convertir los cinco datasets crudos en una serie temporal limpia y consultable. Es la base sobre la que trabajan todos los demás.

#### Tarea 1.1 — Carga y normalización de IDs
- Leer las cinco hojas de `Datasets.xlsx` con `pd.read_excel`.
- Normalizar `Id. Cliente` y `Id.Cliente` a string (hay IDs cortos como `14052` y largos como `1000100724` mezclados). Validar con `assert df['id_cliente'].dtype == 'object'`.
- Validar integridad referencial: clientes en `Ventas` sin entrada en `Clientes` → flag `cliente_huerfano=True` (no excluir, registrar).
- **Tiempo estimado:** 1h

#### Tarea 1.2 — Limpieza de devoluciones
- Filas con `Unidades < 0` son devoluciones. Estrategia: matchear con la factura original por `Num.Fact` y restar del agregado del período correspondiente.
- Implementación pragmática para hackathon: agrupar por `(id_cliente, id_producto, mes_aprox)` y sumar netos. Las devoluciones reducen el agregado, no se tratan independientemente.
- **Tiempo estimado:** 30min

#### Tarea 1.3 — Mapping a `Categoria_H`
- Join `Ventas` ← `Productos` por `Id.Prod` para obtener `Bloque analítico` y `Categoria_H`.
- Validar cobertura: ¿todos los SKUs vendidos están en el maestro de productos?
- **Tiempo estimado:** 30min

#### Tarea 1.4 — Agregación semanal y máscara de campañas
- Agregar a `(id_cliente, categoria_h, semana_lunes)` con suma de `unidades` y `valor`.
- Crear flag `is_campaign` haciendo lookup contra el dataset `Campañas`. Una semana se marca como campaña si **cualquier día** de la semana cae dentro de una ventana.
- **Tiempo estimado:** 1h

#### Tarea 1.5 — Cálculo de SoW y `potencial_fiable`
- Para cada `(id_cliente, categoria_h)`, calcular SoW histórico anualizado.
- `potencial_fiable = True` si `venta_anualizada <= 1.2 * potencial_declarado`.
- Output final: parquet `data/processed/client_category_week.parquet` con el schema `ClientFamilyWeek` + columnas adicionales `sow_historico`, `potencial`, `potencial_fiable`.
- **Tiempo estimado:** 1h

#### Tarea 1.6 — Validators y tests sanity
- Función `validate_pipeline(df)` que comprueba: no hay semanas duplicadas, fechas dentro del rango 2021-2025, todas las categorías están en el mapping, sumas coherentes.
- **Tiempo estimado:** 30min

**Entrega final de P1:** `data/processed/client_category_week.parquet` + función `load_client_history(id_cliente, categoria_h) -> pd.DataFrame` que retorna la serie temporal de ese par.

---

### Persona 2 — ML / Modelos estadísticos

**Responsabilidad:** implementar los dos motores de twin, el detector de señales y el generador de narrativa.

#### Tarea 2.1 — Twin de Commodities (Poisson-Gamma)

```python
# models/twin_commodity.py
from scipy.stats import nbinom, gamma

class CommodityTwin:
    def __init__(self, alpha_prior=1.0, beta_prior=1.0):
        self.alpha_prior = alpha_prior
        self.beta_prior = beta_prior

    def fit(self, weekly_units: np.ndarray, exclude_campaigns: np.ndarray):
        """
        weekly_units: array de unidades por semana
        exclude_campaigns: array booleano, True = excluir semana del fit
        """
        clean = weekly_units[~exclude_campaigns]
        self.alpha_post = self.alpha_prior + clean.sum()
        self.beta_post = self.beta_prior + len(clean)
        # Tasa esperada
        self.lambda_hat = self.alpha_post / self.beta_post

    def predict_distribution(self):
        """Retorna distribución predictiva Binomial Negativa."""
        n = self.alpha_post
        p = self.beta_post / (self.beta_post + 1)
        return nbinom(n, p)

    def confidence_band(self, alpha=0.05):
        dist = self.predict_distribution()
        return dist.ppf(alpha/2), dist.ppf(1 - alpha/2)

    def divergence_score(self, observed):
        """Cuántas desviaciones está la observación respecto al esperado."""
        dist = self.predict_distribution()
        return (observed - dist.mean()) / dist.std()
```

**Parámetros ajustables expuestos:** `alpha_prior`, `beta_prior` (permiten configurar el twin sin reentrenar). Para clientes nuevos, se inicializan con la media poblacional de la familia (computada por P1).

**Tiempo estimado:** 2h

#### Tarea 2.2 — Twin de Productos Técnicos (IPT log-normal)

```python
# models/twin_technical.py
from scipy.stats import lognorm, weibull_min
import numpy as np

class TechnicalTwin:
    def __init__(self, distribution='lognormal'):
        self.distribution = distribution

    def fit(self, purchase_dates: list[date]):
        """Calcula IPTs en días entre compras consecutivas."""
        if len(purchase_dates) < 4:
            self.distribution = 'weibull'  # más robusto con pocos datos

        ipts = np.diff([d.toordinal() for d in sorted(purchase_dates)])
        log_ipts = np.log(ipts)

        if self.distribution == 'lognormal':
            self.mu = log_ipts.mean()
            self.sigma = log_ipts.std()
        else:
            # Weibull MLE
            self.shape, _, self.scale = weibull_min.fit(ipts, floc=0)

        self.ipts = ipts
        self.last_purchase = max(purchase_dates)

    def expected_next_purchase_days(self):
        if self.distribution == 'lognormal':
            return np.exp(self.mu + self.sigma**2 / 2)
        return self.scale * np.math.gamma(1 + 1/self.shape)

    def confidence_band_days(self):
        if self.distribution == 'lognormal':
            return np.exp(self.mu - 1.96*self.sigma), np.exp(self.mu + 1.96*self.sigma)
        return weibull_min.ppf([0.05, 0.95], self.shape, scale=self.scale)

    def is_deterioration(self, today: date, recent_ipts: np.ndarray):
        """
        Tres condiciones simultáneas:
        1. Silencio actual > P90 IPT histórico
        2. Pendiente positiva en últimas 3-4 IPTs (alargamiento)
        3. (handled outside) sin campaña activa
        """
        silence = (today - self.last_purchase).days
        p90 = self.confidence_band_days()[1]
        slope = np.polyfit(range(len(recent_ipts)), recent_ipts, 1)[0]
        return silence > p90 and slope > 0
```

**Parámetros ajustables:** `distribution`, umbral de percentil para alerta (P90 por defecto), ventana de IPTs para cálculo de pendiente.

**Tiempo estimado:** 2h

#### Tarea 2.3 — Detector de Señales y Scoring

```python
# models/signal_detector.py
def compute_indice_madurez(history: pd.DataFrame) -> str:
    n_purchases = (history['unidades_netas'] > 0).sum()
    n_months = (history['semana'].max() - history['semana'].min()).days / 30
    if n_months > 18 and n_purchases > 12: return 'Alto'
    if n_months > 6 and n_purchases > 4: return 'Medio'
    return 'Bajo'

def detect_signals(history, twin, potencial, sow_historico) -> list[Signal]:
    """Lógica de activación según taxonomía."""
    # FUGA_PARCIAL_COMMODITY
    # DEMANDA_NO_CAPTURADA
    # DETERIORO_SOSTENIDO_TECNICO
    # PAUSA_SOSPECHOSA
    # CAMPAIGN_NO_RESPONSE
    # SEÑAL_CRUZADA_NEGATIVA  (requiere agregación a nivel cliente)
    pass

def score_urgencia(signal: Signal, w1=0.5, w2=0.3, w3=0.2) -> float:
    impacto = signal.dnc_estimada * precio_medio  # normalizado [0,1]
    persistencia = min(signal.semanas_fuera_banda / 8, 1.0)
    madurez_factor = {'Alto': 1.0, 'Medio': 0.7, 'Bajo': 0.3}[signal.indice_madurez]
    return w1*impacto + w2*persistencia + w3*madurez_factor
```

**Tiempo estimado:** 2.5h

#### Tarea 2.4 — Generador de narrativa causal

Plantillas parametrizadas, una por tipo de señal. **No usa LLM** — es texto determinista construido con f-strings sobre las variables del twin. Esto garantiza trazabilidad y velocidad.

```python
# models/narrative.py
TEMPLATES = {
    'FUGA_PARCIAL_COMMODITY': (
        "Compró {observed:.0f} u. de {categoria} las últimas {weeks} semanas "
        "(esperado: {expected:.0f} ± {band:.0f}). Potencial declarado {potencial:.0f} u./mes, "
        "captura histórica {sow:.0%}. {campaign_clause}. {cross_clause}. "
        "Probabilidad alta de fuga parcial. {recommendation}."
    ),
    # ... resto de tipos
}

def generate_narrative(signal: Signal, context: dict) -> str:
    return TEMPLATES[signal.tipo].format(**context)
```

**Tiempo estimado:** 1h

**Entrega final de P2:** función `run_detection(df_clientes) -> list[Signal]` que toma el output de P1 y produce la lista de señales con narrativa.

---

### Persona 3 — Bandit + Backend API

**Responsabilidad:** implementar el Contextual MAB, el endpoint de scoring de urgencia, la integración con ElevenLabs y la API REST que sirve datos al frontend.

#### Tarea 3.1 — Contextual Multi-Armed Bandit

```python
# api/bandit.py
import numpy as np

class ContextualBandit:
    """
    Thompson Sampling con segmentación por contexto discretizado.
    Cada (segment, action) mantiene una distribución Beta(α, β).
    """

    ACTIONS = ['visita', 'llamada', 'email', 'muestra', 'monitorizar']

    def __init__(self):
        # Estructura: {segment_key: {action: (alpha, beta)}}
        self.posteriors = {}

    def _segment(self, context: dict) -> str:
        """Discretiza el contexto en un bucket."""
        # Ejemplo: 'FUGA_PARCIAL_COMMODITY|Alto|magnitud_alta'
        magnitud = 'alta' if context['divergencia'] > 1.5 else 'media' if context['divergencia'] > 0.7 else 'baja'
        return f"{context['tipo_senal']}|{context['indice_madurez']}|{magnitud}"

    def recommend(self, context: dict) -> dict[str, float]:
        seg = self._segment(context)
        if seg not in self.posteriors:
            self.posteriors[seg] = {a: (1, 1) for a in self.ACTIONS}

        # Thompson Sampling: muestra de cada Beta y normaliza para mostrar probabilidades
        samples = {a: np.random.beta(*self.posteriors[seg][a]) for a in self.ACTIONS}
        total = sum(samples.values())
        return {a: s/total for a, s in samples.items()}

    def update(self, context: dict, action: str, reward: int):
        seg = self._segment(context)
        a, b = self.posteriors[seg][action]
        self.posteriors[seg][action] = (a + reward, b + (1 - reward))
```

**Cold start:** priors uniformes `Beta(1, 1)`. Para la demo, pre-poblar con ~50 interacciones simuladas que muestren convergencia hacia patrones razonables (visita → mejor para fuga severa, email → mejor para pausa leve).

**Tiempo estimado:** 2h

#### Tarea 3.2 — API REST con FastAPI

```python
# api/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"])

@app.get("/api/signals")
def list_signals(
    tipo: str | None = None,
    bloque: str | None = None,
    limit: int = 50
) -> list[Signal]:
    """Lista de señales activas, ordenadas por score_urgencia descendente."""
    signals = load_signals_from_storage()
    if tipo: signals = [s for s in signals if s.tipo == tipo]
    if bloque: signals = [s for s in signals if s.bloque == bloque]
    return sorted(signals, key=lambda s: -s.score_urgencia)[:limit]

@app.get("/api/signals/{signal_id}/detail")
def signal_detail(signal_id: str):
    """Detalle completo: signal + serie temporal para gráfico + bandit recommendation."""
    return {
        "signal": load_signal(signal_id),
        "history": load_history_for_chart(signal_id),  # últimas 12 semanas
        "bandit": bandit.recommend(build_context(signal_id))
    }

@app.post("/api/signals/{signal_id}/feedback")
def submit_feedback(signal_id: str, action: str, outcome: str):
    """outcome: 'acted' | 'false_alarm' | 'priority_up'."""
    reward = 1 if outcome == 'acted' else 0  # se ajustará con compra real posterior
    bandit.update(build_context(signal_id), action, reward)
    return {"status": "ok"}

@app.post("/api/signals/{signal_id}/voice_briefing")
def voice_briefing(signal_id: str):
    """Genera audio MP3 con ElevenLabs a partir de la narrativa."""
    return {"audio_url": elevenlabs_synthesize(signal.narrativa)}
```

**Tiempo estimado:** 2h

#### Tarea 3.3 — Integración ElevenLabs

```python
# api/voice.py
import requests

def elevenlabs_synthesize(text: str, voice_id: str = "21m00Tcm4TlvDq8ikWAM") -> str:
    """Llama a la API de ElevenLabs y retorna URL del audio generado."""
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    response = requests.post(url, json={
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75}
    }, headers={"xi-api-key": ELEVENLABS_API_KEY})
    # Guardar audio y retornar URL local
    audio_path = f"/tmp/briefing_{uuid4()}.mp3"
    with open(audio_path, 'wb') as f: f.write(response.content)
    return audio_path
```

**Tiempo estimado:** 1h

#### Tarea 3.4 — Detector de señales geográficas sistémicas

Endpoint adicional `/api/territorial_alerts` que detecta cuando ≥ N clientes de la misma provincia generan FUGA_PARCIAL en la misma categoría en un período de 4 semanas. Output sirve para el mapa de calor (si da tiempo).

**Tiempo estimado:** 1h

**Entrega final de P3:** API corriendo en `localhost:8000` con endpoints documentados en `/docs` (FastAPI lo genera automáticamente).

---

### Persona 4 — Frontend / Dashboard

**Responsabilidad:** implementar el dashboard React siguiendo el mockup ya validado, conectarlo a la API de P3.

#### Tarea 4.1 — Setup del proyecto

- `npx create-vite frontend --template react`
- Dependencias: `chart.js`, `react-chartjs-2`, `axios`, opcionalmente `tailwindcss` o CSS modules.
- Configurar proxy a `localhost:8000` para evitar CORS en dev.
- **Tiempo estimado:** 30min

#### Tarea 4.2 — Layout principal

Estructura idéntica al mockup ya construido:
- `<TopBar />` — logo, indicador "en vivo", semana actual
- `<Sidebar />` — navegación por tipo de señal con contadores
- `<AlertList />` — lista central de señales priorizadas
- `<DetailPanel />` — panel lateral con KPIs, gráfico, narrativa, bandit, acciones

```jsx
// src/App.jsx
function App() {
  const [signals, setSignals] = useState([]);
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    axios.get('/api/signals').then(r => setSignals(r.data));
  }, []);

  return (
    <div className="root">
      <TopBar />
      <Sidebar signals={signals} />
      <AlertList signals={signals} selected={selected} onSelect={setSelected} />
      <DetailPanel signalId={selected} />
    </div>
  );
}
```

**Tiempo estimado:** 1h

#### Tarea 4.3 — Componente `<DetailPanel />`

- Carga `/api/signals/{id}/detail` cuando cambia la selección.
- Renderiza con Chart.js el gráfico de evolución con bandas de confianza:
  - Línea sólida = observado (rojo si fuera de banda, azul si dentro)
  - Líneas punteadas verdes = banda de confianza [P5, P95]
- Renderiza barras de probabilidad del bandit con animación de transición.
- Botones de feedback que llaman a `POST /api/signals/{id}/feedback`.

**Tiempo estimado:** 2.5h

#### Tarea 4.4 — Briefing de voz

Botón "Briefing de voz" que llama al endpoint, recibe URL del audio y lo reproduce en un `<audio>` element. Mostrar waveform animado durante la reproducción (opcional pero alto impacto visual).

**Tiempo estimado:** 1h

#### Tarea 4.5 — Polish y demo flow

- Animaciones de transición al seleccionar alerta.
- Estados de loading mientras se cargan los datos.
- Manejo de errores básico (si la API falla, mostrar mensaje, no pantalla blanca).
- Datos de prueba realistas pre-cargados para que la demo se vea poblada desde el primer click.
- **Tiempo estimado:** 1.5h

**Entrega final de P4:** dashboard accesible en `localhost:5173` totalmente funcional contra la API.

---

## Timeline coordinado

| Hora | P1 (ETL) | P2 (Modelos) | P3 (Bandit/API) | P4 (Frontend) |
|------|----------|--------------|-----------------|---------------|
| 0–2  | Carga + IDs + mapping | Esqueleto de twins con datos sintéticos | Esqueleto API + endpoints mockeados | Setup + layout |
| 2–6  | Limpieza + agregación + máscaras | Twin Commodity + Técnico funcionales | Bandit Thompson Sampling | AlertList + DetailPanel |
| 6–10 | SoW + potencial fiable + parquet final | Detector de señales + narrativa | Integración con outputs de P2 | Chart.js + barras bandit |
| 10–14| **Integración con P2** | **Validación contra datos reales de P1** | Endpoints definitivos | Conexión API real |
| 14–18| Soporte + ajustes | Pulido de narrativa | ElevenLabs + alertas territoriales | Briefing de voz + polish |
| 18–22| Demo support | Demo support | Pre-poblado de bandit | Datos demo + ensayo |
| 22–24| Buffer | Buffer | Buffer | Buffer |

**Hito crítico — hora 12:** primer end-to-end funcional. Si para esta hora no hay un flujo completo `Excel → API → Frontend`, hay que recortar alcance.

---

## Estrategia anti-bloqueo

Mientras P1 termina el ETL, los demás trabajan con **datos mock**:

- P2 usa series sintéticas generadas con `np.random.poisson(lam=10, size=104)` para validar los modelos.
- P3 usa una lista hardcodeada de 5 `Signal` ejemplo para construir la API.
- P4 usa un `mockSignals.json` con la misma estructura que devuelve la API.

En la hora 10–12 se hace el **swap**: cada componente apunta al de upstream real en lugar del mock. Si los contratos se respetaron, la integración es trivial.

---

## Criterios de éxito del MVP

Para considerar la demo lista:

1. ✅ Lista de al menos 10 señales reales generadas desde los datos de Inibsa (no sintéticos).
2. ✅ Al menos 3 tipos diferentes de señal aparecen en la lista (`FUGA_PARCIAL_COMMODITY`, `DETERIORO_SOSTENIDO_TECNICO`, `DEMANDA_NO_CAPTURADA`).
3. ✅ Click en una alerta abre el panel lateral con gráfico de bandas de confianza dibujado correctamente.
4. ✅ La narrativa causal aparece coherente con los números mostrados.
5. ✅ Las barras del bandit cambian al hacer click en distintos clientes (segmentación funciona).
6. ✅ Botón de briefing de voz reproduce audio en español con la narrativa.
7. ✅ Botones de feedback registran la interacción y actualizan el bandit (visible en una segunda alerta del mismo segmento).

---

## Funcionalidades opcionales (si sobra tiempo)

Por orden de impacto/esfuerzo:

1. **Mapa territorial:** componente con mapa de España y puntos de calor por provincia. Alta visibilidad en demo.
2. **Comparador antes/después del bandit:** slider que muestra cómo evolucionan las probabilidades de Thompson Sampling con cada feedback. Excelente para explicar el aprendizaje al jurado.
3. **Filtros avanzados** en el sidebar: por provincia, por madurez del twin, por tipo de cliente.
4. **Export a CSV** de la lista de alertas para integración con CRM (responde directamente al brief).

---

## Riesgos y mitigaciones

| Riesgo | Probabilidad | Mitigación |
|--------|--------------|-----------|
| Mapping subfamilia↔familia incorrecto | Alta | Definir en hora 1 colectivamente, documentar en `etl/mappings.py` |
| Modelos generan demasiados FP | Media | Índice de Madurez bloquea alertas de twins inmaduros desde el inicio |
| Integración API↔Frontend falla por CORS | Alta | Configurar proxy en Vite desde el setup, no dejarlo para el final |
| ElevenLabs API rate limit | Media | Cachear audios generados, no regenerar el mismo briefing dos veces |
| Bandit no converge con datos simulados | Baja | Pre-poblar con 50 interacciones realistas para que la demo muestre patrones |
| Demo se cae en vivo | Media | Grabar un screencast de respaldo en hora 22 |
