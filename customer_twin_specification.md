# Customer Twin — Ficha Técnica

## Descripción del sistema

Sistema de inteligencia comercial que construye un **gemelo digital probabilístico** por cada par `(cliente, familia de producto)`. El twin aprende la distribución esperada de comportamiento de compra de cada cliente y detecta divergencias estadísticamente significativas respecto al patrón observado. Las señales resultantes alimentan un recomendador adaptativo que decide qué acción comercial ejecutar. El output es una lista priorizada de alertas accionables con narrativa causal, consumible desde un dashboard web por el equipo comercial.

---

## Arquitectura general

```
Fuentes de datos
      │
      ▼
┌─────────────────┐
│  Capa 1: ETL    │  Ingesta, limpieza, agregación temporal, enmascaramiento de campañas
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────┐
│  Capa 2: Motor de Gemelos               │
│  ┌──────────────────┐ ┌───────────────┐ │
│  │ Twin Commodities │ │ Twin Técnicos │ │  Modelos estadísticos diferenciados por bloque
│  └──────────────────┘ └───────────────┘ │
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│  Capa 3: Detector de señales            │  Scoring, narrativa causal, taxonomía de alertas
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│  Capa 4: Contextual Multi-Armed Bandit  │  Recomendación adaptativa de acción comercial
└────────────────────┬────────────────────┘
                     │
                     ▼
┌─────────────────────────────────────────┐
│  Capa 5: Dashboard web                  │  Lista priorizada + panel de detalle lateral
└─────────────────────────────────────────┘
```

---

## Componentes

### Capa 1 — ETL y preprocesado

**Función:** unificar las cinco fuentes de datos (`Ventas`, `Productos`, `Clientes`, `Potencial`, `Campañas`) en una serie temporal limpia por `(id_cliente, familia, semana)`.

**Diseño:**
- Resolución de IDs heterogéneos entre `Ventas` y `Clientes` por normalización a string y left-join con el maestro.
- Devoluciones (`Unidades < 0`) tratadas como ajustes sobre el período original, no como observaciones negativas independientes.
- Ventanas de campaña marcadas con flag `is_campaign=True` y excluidas del ajuste paramétrico de los twins. Se conservan para detección de `CAMPAIGN_NO_RESPONSE`.
- Cálculo del share of wallet histórico (`SoW`) y flag `potencial_fiable` (activo cuando venta observada ≤ 120% del potencial declarado).

**Restricciones:**
- Clientes con potencial declarado absurdo (venta > potencial) se excluyen del cálculo de Demanda No Capturada pero no de la detección de deterioro.
- Granularidad temporal mínima: semana. No se admite granularidad diaria por insuficiencia de señal en productos técnicos.

---

### Capa 2 — Motor de Gemelos Probabilísticos

Cada gemelo es un modelo estadístico independiente por `(cliente, familia)`. Los parámetros son ajustables por cliente, lo que permite personalizar el comportamiento del twin sin reentrenar el sistema completo.

#### Twin de Commodities — Modelo Poisson-Gamma

**Función:** modelar la tasa de compra semanal de familias con dinámica recurrente (Familia C1, C2).

**Diseño:**
- Likelihood: `Y_{t} | λ ~ Poisson(λ)`
- Prior conjugado: `λ ~ Gamma(α, β)`
- Posterior analítica: `λ | Y ~ Gamma(α + ΣY_t, β + T)`
- Distribución predictiva: `Binomial Negativa(α + ΣY_t, β/(β+1))`
- Métrica principal: **Demanda No Capturada (DNC)** = `Potencial × SoW_histórico − E[Y_{T+1}]`
- Umbral de activación personalizado por cliente: `percentil_75(residuos_históricos)`

**Parámetros ajustables:** `α` (forma del prior), `β` (escala temporal), ventana de historia usada para el ajuste, umbral de activación.

**Restricciones:** requiere mínimo 8 semanas de observaciones para inicializar el prior con datos propios. Por debajo, se usa la media poblacional de la familia como prior informado.

#### Twin de Productos Técnicos — Modelo de Interpurchase Time

**Función:** modelar el tiempo entre compras consecutivas en familias con dinámica dependiente de casos clínicos (Familia T1, T2).

**Diseño:**
- Variable modelada: `IPT_k = tiempo en días entre compra k-1 y compra k`
- Distribución: `log(IPT) | μ, σ ~ Normal(μ, σ)` (log-normal) para clientes con ≥ 4 eventos; `Weibull(k, λ)` para clientes con menos datos.
- Banda de confianza: `[exp(μ − 1.96σ), exp(μ + 1.96σ)]` → [P5, P95] del siguiente evento esperado.
- Condición de alerta `DETERIORO_SOSTENIDO`: silencio > P90 del IPT histórico **Y** pendiente positiva en las últimas 3–4 observaciones **Y** sin campaña activa.
- Condición de alerta `PAUSA_SOSPECHOSA`: silencio en rango [P75, P90]. No genera acción, solo vigilancia.

**Parámetros ajustables:** umbral de detección (P90 por defecto, configurable), número mínimo de eventos para activar alertas de deterioro, ventana de observaciones para el cálculo de pendiente.

**Restricciones:** una sola pausa nunca activa alerta. El modelo no asume regularidad: la ausencia de compra no es en sí misma una señal.

#### Índice de Madurez del Twin (IM)

Cada twin expone su nivel de incertidumbre mediante un índice que determina la anchura de las bandas y la agresividad del sistema de alertas:

| IM | Criterio | Comportamiento |
|----|----------|---------------|
| Alto | > 18 meses y > 12 compras | Alertas de deterioro habilitadas, bandas estrechas |
| Medio | 6–18 meses o 4–12 compras | Alertas con flag de confianza media |
| Bajo | < 6 meses o < 4 compras | Solo alertas de ausencia total. Sin alertas de deterioro |

---

### Capa 3 — Detector de Señales

**Función:** comparar la distribución predictiva posterior del twin con la observación real, clasificar la señal y generar la narrativa causal.

**Diseño:**

Taxonomía de señales:

| Tipo | Condición |
|------|-----------|
| `FUGA_PARCIAL_COMMODITY` | Captura cae por debajo del P25 histórico ≥ 3 semanas consecutivas |
| `DEMANDA_NO_CAPTURADA` | SoW nunca supera el 50% del potencial en ningún período |
| `DETERIORO_SOSTENIDO_TECNICO` | IPT > P90 Y pendiente creciente en últimas 3–4 observaciones |
| `PAUSA_SOSPECHOSA` | IPT en rango [P75, P90]. Marcador de vigilancia |
| `CAMPAIGN_NO_RESPONSE` | Cliente que respondía históricamente a campañas y no lo hizo en la última |
| `SEÑAL_CRUZADA_NEGATIVA` | Caída simultánea en todas las familias del cliente |

Scoring de urgencia: `U = w1 × ImpactoEconómico + w2 × PersistenciaDivergencia + w3 × MadurezTwin`

Los pesos `w1`, `w2`, `w3` son configurables sin reentrenar.

**Restricciones:** el sistema nunca afirma fuga confirmada. La narrativa usa lenguaje probabilístico explícito. Las alertas sin Índice de Madurez suficiente no se emiten.

---

### Capa 4 — Contextual Multi-Armed Bandit

**Función:** dado un cliente con señal activa, recomendar la acción comercial óptima y aprender de los resultados observados.

**Diseño:**
- Algoritmo: **Thompson Sampling** con distribuciones Beta por `(brazo, segmento de contexto)`.
- Brazos (acciones): visita presencial, llamada directa, email con oferta, envío de muestra, monitorizar.
- Vector de contexto: tipo de señal, familia afectada, magnitud de divergencia, SoW histórico, IM del twin, provincia, recencia de última compra, historial de respuesta a intervenciones previas.
- Recompensa: binaria — el cliente realizó al menos una compra en las 4 semanas posteriores con volumen ≥ P25 histórico.
- Actualización: `α_a += r; β_a += (1 − r)` tras cada observación. Sin reentrenamiento batch.

**Restricciones:** cold start con priors uniformes `Beta(1, 1)`. Las probabilidades del bandit son orientativas hasta acumular un mínimo de 30 interacciones por brazo por segmento de contexto.

---

### Capa 5 — Dashboard Web

**Función:** interfaz de consumo para el equipo comercial. Lista priorizada de señales activas con panel de detalle lateral desplegable al seleccionar una alerta.

**Diseño:**
- Layout: sidebar de navegación + lista central de alertas + panel lateral de detalle.
- Lista ordenada por score de urgencia `U`. Cada fila muestra: cliente, familia, tipo de señal (badge con color semántico), semanas fuera de banda.
- Panel lateral: KPIs del twin (captura actual vs. histórica, DNC, semanas fuera de banda), gráfico de evolución con bandas de confianza, narrativa causal, probabilidades del bandit por acción y botones de feedback.
- Botones de acción: `Voy a actuar` / `Falsa alarma` / `Briefing de voz` / `Prioridad máxima`. Cada interacción actualiza el bandit.
- Tono visual: claro, corporativo, tipografía sans-serif, color semántico restringido a rojo (fuga), ámbar (deterioro técnico) y azul (DNC/oportunidad).

**Restricciones:** interfaz diseñada para pantalla de escritorio (resolución mínima 1280px). Sin navegación entre páginas: toda la interacción ocurre en una sola superficie.

---

## Stack técnico

| Componente | Tecnología |
|-----------|-----------|
| ETL y modelos | Python · pandas · scipy.stats |
| Dashboard | React · Chart.js |
| Voz (briefing) | ElevenLabs API |
| Datos | CSV/XLSX (Inibsa datasets) |

---

## Limitaciones conocidas

- El potencial declarado puede ser inconsistente (valores absurdos o inexistentes). Mitigado con el flag `potencial_fiable`.
- La competencia no es observable directamente. Las señales de fuga son inferencias probabilísticas, nunca certezas.
- El bandit requiere historial de intervenciones para converger. En el MVP opera con priors uniformes y datos simulados.
- El mapeo entre subfamilias de potencial (Anestesia, Biomateriales, Bioseguridad) y familias de producto (C1, C2, T1, T2) debe ser validado con Inibsa antes del despliegue.
