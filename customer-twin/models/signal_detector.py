"""Signal detector: turn weekly aggregates + twins into Signal objects.

Implements the six-signal taxonomy from customer_twin_specification.md §3:

  FUGA_PARCIAL_COMMODITY        (commodity capture < P25 ≥3 weeks)
  DEMANDA_NO_CAPTURADA          (SoW never > 0.5)
  DETERIORO_SOSTENIDO_TECNICO   (IPT > P90 AND increasing slope, no campaign)
  PAUSA_SOSPECHOSA              (IPT in [P75, P90])
  CAMPAIGN_NO_RESPONSE          (historic campaign-responder didn't respond)
  SEÑAL_CRUZADA_NEGATIVA        (drop in ≥2 families simultaneously)

The detector never *concludes* fuga — it surfaces probabilistic indicators.
Maturity index (Alto/Medio/Bajo) gates which signals can fire.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Iterable

import numpy as np
import pandas as pd

from etl.mappings import (
    CATEGORIA_TO_BLOQUE,
    CROSS_NEGATIVE_MIN_FAMILIES,
    FUGA_PARCIAL_CONSEC_WEEKS,
    MADUREZ_FACTOR,
    SOW_DNC_THRESHOLD,
    URGENCY_W_IMPACTO,
    URGENCY_W_MADUREZ,
    URGENCY_W_PERSISTENCIA,
)
from etl.territorial import TerritorialMatch, normalize_provincia
from shared.schemas import Signal

from .narrative import generate_narrative
from .twin_commodity import CommodityTwin, fit_population_lambda
from .twin_technical import TechnicalTwin

log = logging.getLogger(__name__)


# --- Maturity index --------------------------------------------------------


def compute_indice_madurez(history: pd.DataFrame) -> str:
    """Alto / Medio / Bajo per spec table.

    Alto:  >18 months of history AND >12 active purchase weeks.
    Medio: >6  months OR        >4  active purchase weeks.
    Bajo:  otherwise.
    """
    if history.empty:
        return "Bajo"
    n_purchases = int((history["unidades_netas"] > 0).sum())
    span_days = (
        pd.to_datetime(history["semana"]).max()
        - pd.to_datetime(history["semana"]).min()
    ).days
    n_months = span_days / 30.0
    if n_months > 18 and n_purchases > 12:
        return "Alto"
    if n_months > 6 and n_purchases > 4:
        return "Medio"
    return "Bajo"


# --- Helpers ---------------------------------------------------------------


def _provincia_for(history: pd.DataFrame) -> str:
    """Raw provincia string as it appears in the dataset (kept for legacy callers)."""
    if history.empty:
        return "Desconocida"
    val = history["provincia"].dropna().iloc[0] if "provincia" in history.columns else None
    return str(val) if val else "Desconocida"


def _territorial_for(history: pd.DataFrame) -> tuple[str, TerritorialMatch]:
    """Resolve the canonical territorial match for a client's history.

    Returns the raw provincia string (preserved for audit) and a
    :class:`TerritorialMatch` with the canonical name, CCAA and coordinates.
    """
    raw = _provincia_for(history)
    match = normalize_provincia(raw)
    return raw, match


def _last_n_observations(history: pd.DataFrame, n: int) -> pd.DataFrame:
    return history.sort_values("semana").tail(n)


def _purchase_dates_from_history(history: pd.DataFrame) -> list[date]:
    """Return list of week-Mondays where at least one unit was bought."""
    h = history[history["unidades_netas"] > 0]
    return sorted(pd.to_datetime(h["semana"]).dt.date.unique().tolist())


def reindex_full_weekly(history: pd.DataFrame, today: date) -> pd.DataFrame:
    """Expand history to a continuous weekly grid, filling missing weeks with zeros.

    The ETL output only contains weeks with invoices; the twins need every
    week of the active observation window — otherwise the predictive mean is
    biased toward "bursty" behaviour and confidence bands collapse.

    Window: from the first observed semana for this (cliente, categoria_h) up
    to the Monday of `today`. Gaps inside become rows with `unidades_netas=0`
    and `is_campaign=False` (campaign masking applied separately by caller).
    """
    if history.empty:
        return history

    history = history.sort_values("semana").reset_index(drop=True)
    start = pd.to_datetime(history["semana"].iloc[0])
    end_monday = pd.to_datetime(today) - pd.to_timedelta(
        pd.to_datetime(today).weekday(), unit="D"
    )
    if end_monday < start:
        end_monday = start
    grid = pd.date_range(start=start, end=end_monday, freq="7D")

    template = history.iloc[0].to_dict()
    base = pd.DataFrame({"semana": grid.date})
    base["id_cliente"] = template["id_cliente"]
    base["categoria_h"] = template["categoria_h"]
    base["bloque"] = template["bloque"]
    base["provincia"] = template["provincia"]
    base["unidades_netas"] = 0.0
    base["valor_neto"] = 0.0
    base["n_facturas"] = 0
    base["is_campaign"] = False

    history_idx = history.copy()
    history_idx["semana"] = pd.to_datetime(history_idx["semana"]).dt.date
    base = base.set_index("semana")
    history_idx = history_idx.set_index("semana")

    base.update(history_idx)
    return base.reset_index()


# --- Per-bloque detection --------------------------------------------------


def _detect_commodity_signals(
    history: pd.DataFrame,
    sow_row: dict,
    population_lambda: float,
    today: date,
) -> list[dict]:
    """Run commodity twin and emit signals.

    Returns a list of dicts ready to wrap into Signal models.
    """
    out: list[dict] = []
    if history.empty:
        return out

    history = history.sort_values("semana").reset_index(drop=True)
    units = history["unidades_netas"].clip(lower=0).to_numpy()
    is_camp = history["is_campaign"].to_numpy()

    twin = CommodityTwin(population_lambda=population_lambda)
    twin.fit(units, exclude_campaigns=is_camp)

    p25 = twin.quantile(0.25)
    band_lo, band_hi = twin.confidence_band(alpha=0.05)
    expected = twin.expected_units()

    # FUGA_PARCIAL_COMMODITY: ≥N consecutive non-campaign weeks below P25.
    below = (units < p25) & ~is_camp
    last_window = below[-FUGA_PARCIAL_CONSEC_WEEKS:]
    consec_below = 0
    for v in below[::-1]:
        if v:
            consec_below += 1
        else:
            break

    observed_recent = float(units[-FUGA_PARCIAL_CONSEC_WEEKS:].sum()) if len(units) else 0.0
    expected_recent = expected * min(len(units), FUGA_PARCIAL_CONSEC_WEEKS)

    if (
        len(last_window) == FUGA_PARCIAL_CONSEC_WEEKS
        and bool(last_window.all())
        and consec_below >= FUGA_PARCIAL_CONSEC_WEEKS
    ):
        # Per-week values throughout: schema/UI stay coherent with the chart.
        recent_mean = float(units[-FUGA_PARCIAL_CONSEC_WEEKS:].mean())
        historic_mean = float(units[~is_camp].mean()) if (~is_camp).any() else float(units.mean())
        out.append({
            "tipo": "FUGA_PARCIAL_COMMODITY",
            "semanas_fuera_banda": int(consec_below),
            "captura_actual": recent_mean,
            "captura_historica": historic_mean,
            "dnc_estimada": _dnc_estimada(sow_row, expected),
            "expected_value": float(expected),
            "observed_value": recent_mean,
            "confidence_band": (float(band_lo), float(band_hi)),
        })

    # DEMANDA_NO_CAPTURADA: SoW never crossed threshold AND potencial declared+fiable.
    sow = sow_row.get("sow_historico")
    if (
        sow is not None
        and not pd.isna(sow)
        and sow_row.get("potencial_fiable", False)
        and sow < SOW_DNC_THRESHOLD
    ):
        # For DNC the "semanas_fuera_banda" represents an ongoing capture gap.
        # Capping at 52 weeks prevents the persistencia term from saturating
        # the urgency score across the full multi-year series.
        out.append({
            "tipo": "DEMANDA_NO_CAPTURADA",
            "semanas_fuera_banda": min(int(history.shape[0]), 52),
            "captura_actual": float(sow),
            "captura_historica": float(sow),
            "dnc_estimada": _dnc_estimada(sow_row, expected),
            "expected_value": float(expected),
            "observed_value": float(units[-1] if len(units) else 0.0),
            "confidence_band": (float(band_lo), float(band_hi)),
        })

    # CAMPAIGN_NO_RESPONSE: client responded historically (campaign mean > non-campaign mean)
    # but the most recent campaign week had units below non-campaign baseline.
    if is_camp.any() and (~is_camp).any():
        camp_mean = float(units[is_camp].mean())
        base_mean = float(units[~is_camp].mean())
        last_campaign_idx = np.where(is_camp)[0]
        if len(last_campaign_idx):
            last_idx = int(last_campaign_idx[-1])
            last_camp_units = float(units[last_idx])
            if camp_mean > base_mean * 1.10 and last_camp_units < base_mean:
                out.append({
                    "tipo": "CAMPAIGN_NO_RESPONSE",
                    "semanas_fuera_banda": 1,
                    "captura_actual": last_camp_units,
                    "captura_historica": camp_mean,
                    "dnc_estimada": max(0.0, camp_mean - last_camp_units),
                    "expected_value": camp_mean,
                    "observed_value": last_camp_units,
                    "confidence_band": (float(band_lo), float(band_hi)),
                })

    return out


def _dnc_estimada(sow_row: dict, expected_weekly: float) -> float | None:
    """DNC = Potencial × SoW_historico − E[Y_{T+1}]; clipped to ≥0."""
    pot = sow_row.get("potencial")
    sow = sow_row.get("sow_historico")
    if pot is None or sow is None or pd.isna(pot) or pd.isna(sow):
        return None
    weekly_potencial = float(pot) / 52.0
    target = weekly_potencial * float(sow)
    return float(max(0.0, target - expected_weekly))


def _detect_technical_signals(
    history: pd.DataFrame,
    today: date,
) -> list[dict]:
    out: list[dict] = []
    purchases = _purchase_dates_from_history(history)
    if len(purchases) < 2:
        return out

    twin = TechnicalTwin()
    try:
        twin.fit(purchases)
    except ValueError:
        return out

    band_lo, band_hi = twin.confidence_band_days()
    expected = twin.expected_next_purchase_days()
    silence = twin.silence_days(today)

    # Deterioro requires ≥3 IPTs (~ ≥4 purchases) per fit.
    history_recent_camp = bool(history.tail(2)["is_campaign"].any()) if not history.empty else False
    if twin.is_deterioration(today) and not history_recent_camp:
        out.append({
            "tipo": "DETERIORO_SOSTENIDO_TECNICO",
            "semanas_fuera_banda": max(1, silence // 7),
            "captura_actual": None,
            "captura_historica": None,
            "dnc_estimada": None,
            "expected_value": float(expected),
            "observed_value": float(silence),
            "confidence_band": (float(band_lo), float(band_hi)),
        })
    elif twin.is_suspicious_pause(today):
        out.append({
            "tipo": "PAUSA_SOSPECHOSA",
            "semanas_fuera_banda": max(1, silence // 7),
            "captura_actual": None,
            "captura_historica": None,
            "dnc_estimada": None,
            "expected_value": float(expected),
            "observed_value": float(silence),
            "confidence_band": (float(band_lo), float(band_hi)),
        })
    return out


# --- Cross-family signal ---------------------------------------------------


def _detect_cross_signal(
    client_histories: dict[str, pd.DataFrame],
    today: date,
) -> dict | None:
    """Drop simultaneously in ≥CROSS_NEGATIVE_MIN_FAMILIES categorias."""
    drops = 0
    last_obs_total = 0.0
    expected_total = 0.0
    for cat, hist in client_histories.items():
        if hist.empty:
            continue
        recent = hist.sort_values("semana").tail(4)
        baseline = hist.sort_values("semana").iloc[:-4]
        if recent.empty or baseline.empty:
            continue
        if recent["unidades_netas"].mean() < 0.7 * max(baseline["unidades_netas"].mean(), 1e-9):
            drops += 1
        last_obs_total += float(recent["unidades_netas"].sum())
        expected_total += float(baseline["unidades_netas"].mean() * len(recent))

    if drops >= CROSS_NEGATIVE_MIN_FAMILIES:
        return {
            "tipo": "SEÑAL_CRUZADA_NEGATIVA",
            "semanas_fuera_banda": 4,
            "captura_actual": None,
            "captura_historica": None,
            "dnc_estimada": None,
            "expected_value": float(expected_total),
            "observed_value": float(last_obs_total),
            "confidence_band": (0.0, float(expected_total) * 1.5),
        }
    return None


# --- Maturity gating + urgency scoring -------------------------------------


def _maturity_blocks_signal(maturity: str, tipo: str) -> bool:
    """Bajo maturity blocks deterioration alerts; only "absence" alerts pass."""
    if maturity == "Bajo" and tipo not in (
        "DEMANDA_NO_CAPTURADA",
        "PAUSA_SOSPECHOSA",
    ):
        return True
    return False


def score_urgencia(
    *,
    dnc_estimada: float | None,
    semanas_fuera_banda: int,
    indice_madurez: str,
    precio_medio: float,
    dnc_normalizer: float = 5000.0,
) -> float:
    """U = w1·impacto + w2·persistencia + w3·madurez.

    Impacto monetiza la DNC con `precio_medio` (€/u.) y se normaliza por
    `dnc_normalizer` (€) para obtener un valor en [0, 1] aproximado.
    """
    impacto_eur = float(dnc_estimada or 0.0) * float(precio_medio or 0.0)
    impacto = float(np.clip(impacto_eur / max(dnc_normalizer, 1.0), 0.0, 1.0))
    persistencia = float(min(semanas_fuera_banda / 8.0, 1.0))
    madurez_factor = MADUREZ_FACTOR.get(indice_madurez, 0.3)
    return (
        URGENCY_W_IMPACTO * impacto
        + URGENCY_W_PERSISTENCIA * persistencia
        + URGENCY_W_MADUREZ * madurez_factor
    )


# --- Public entry-point ----------------------------------------------------


def run_detection(
    weekly: pd.DataFrame,
    sow: pd.DataFrame,
    precio_medio: pd.DataFrame,
    today: date | None = None,
    max_clients: int | None = None,
) -> list[Signal]:
    """Iterate clients × categorias and emit Signal objects.

    Parameters
    ----------
    weekly : output of ETL `client_category_week.parquet`.
    sow    : output of ETL `sow_potencial.parquet`.
    precio_medio : output of ETL `precio_medio_categoria.parquet`.
    today  : reference date (default = max(weekly.semana) + 7 days).
    max_clients : optional cap (useful for fast iteration during dev).
    """
    if weekly.empty:
        return []

    weekly = weekly.copy()
    weekly["semana"] = pd.to_datetime(weekly["semana"]).dt.date

    if today is None:
        today = max(weekly["semana"]) + timedelta(days=7)

    price_lookup = dict(zip(precio_medio["categoria_h"], precio_medio["precio_medio"]))

    # Population lambda per categoria (commodity baseline for cold-start clients).
    pop_lambda = (
        weekly.groupby("categoria_h")["unidades_netas"]
        .apply(lambda s: fit_population_lambda(s.values))
        .to_dict()
    )

    sow_lookup: dict[tuple[str, str], dict] = {
        (r["id_cliente"], r["categoria_h"]): r.to_dict()
        for _, r in sow.iterrows()
    }

    out: list[Signal] = []
    clients = sorted(weekly["id_cliente"].unique().tolist())
    if max_clients is not None:
        clients = clients[:max_clients]

    timestamp_now = datetime.now()

    for cid in clients:
        client_df = weekly[weekly["id_cliente"] == cid]
        per_cat: dict[str, pd.DataFrame] = {
            cat: g for cat, g in client_df.groupby("categoria_h")
        }
        provincia_raw, territorial = _territorial_for(client_df)
        provincia = territorial.provincia or provincia_raw or "Desconocida"

        client_signals: list[Signal] = []

        for cat, hist_raw in per_cat.items():
            bloque = CATEGORIA_TO_BLOQUE.get(cat)
            if bloque is None:
                continue
            hist = reindex_full_weekly(hist_raw, today)
            per_cat[cat] = hist  # update in place so cross-detector sees zero-filled view
            maturity = compute_indice_madurez(hist_raw)  # maturity uses ORIGINAL purchase weeks

            sow_row = sow_lookup.get((cid, cat), {
                "potencial": None, "sow_historico": None, "potencial_fiable": False,
            })

            raw_signals: list[dict] = []
            if bloque == "Commodities":
                raw_signals.extend(
                    _detect_commodity_signals(
                        hist, sow_row, pop_lambda.get(cat, 0.0), today
                    )
                )
            else:
                raw_signals.extend(_detect_technical_signals(hist, today))

            precio = float(price_lookup.get(cat, 0.0))

            for s in raw_signals:
                if _maturity_blocks_signal(maturity, s["tipo"]):
                    continue
                urgency = score_urgencia(
                    dnc_estimada=s.get("dnc_estimada"),
                    semanas_fuera_banda=s["semanas_fuera_banda"],
                    indice_madurez=maturity,
                    precio_medio=precio,
                )
                narrative_ctx = {
                    "id_cliente": cid,
                    "categoria_h": cat,
                    "bloque": bloque,
                    "indice_madurez": maturity,
                    "potencial": sow_row.get("potencial"),
                    "sow": sow_row.get("sow_historico"),
                    "precio_medio": precio,
                    **s,
                }
                signal = Signal(
                    id_cliente=cid,
                    categoria_h=cat,
                    bloque=bloque,
                    tipo=s["tipo"],
                    semanas_fuera_banda=s["semanas_fuera_banda"],
                    captura_actual=s.get("captura_actual"),
                    captura_historica=s.get("captura_historica"),
                    dnc_estimada=s.get("dnc_estimada"),
                    expected_value=float(s["expected_value"]),
                    observed_value=float(s["observed_value"]),
                    confidence_band=tuple(s["confidence_band"]),
                    indice_madurez=maturity,
                    score_urgencia=float(urgency),
                    impacto_estimado=float(s.get("dnc_estimada") * precio) if s.get("dnc_estimada") else None,
                    narrativa=generate_narrative(s["tipo"], narrative_ctx),
                    timestamp=timestamp_now,
                    provincia=provincia,
                    provincia_raw=provincia_raw,
                    comunidad_autonoma=territorial.comunidad_autonoma,
                    lat=territorial.lat,
                    lon=territorial.lon,
                    territorial_source=territorial.source,
                )
                client_signals.append(signal)

        # Cross-family check (after per-category alerts so we know history exists)
        cross_raw = _detect_cross_signal(per_cat, today)
        if cross_raw is not None:
            # Use mean maturity across categorias as a coarse proxy.
            maturities = [compute_indice_madurez(h) for h in per_cat.values()]
            maturity = max(maturities, key=lambda m: MADUREZ_FACTOR.get(m, 0.0)) if maturities else "Bajo"
            urgency = score_urgencia(
                dnc_estimada=None,
                semanas_fuera_banda=cross_raw["semanas_fuera_banda"],
                indice_madurez=maturity,
                precio_medio=float(np.mean(list(price_lookup.values())) if price_lookup else 0.0),
            )
            narrative_ctx = {
                "id_cliente": cid,
                "categoria_h": "TODAS",
                "bloque": "Cross",
                "indice_madurez": maturity,
                **cross_raw,
            }
            client_signals.append(Signal(
                id_cliente=cid,
                categoria_h="TODAS",
                bloque="Cross",
                tipo="SEÑAL_CRUZADA_NEGATIVA",
                semanas_fuera_banda=cross_raw["semanas_fuera_banda"],
                captura_actual=None,
                captura_historica=None,
                dnc_estimada=None,
                expected_value=cross_raw["expected_value"],
                observed_value=cross_raw["observed_value"],
                confidence_band=cross_raw["confidence_band"],
                indice_madurez=maturity,
                score_urgencia=float(urgency),
                impacto_estimado=None,
                narrativa=generate_narrative("SEÑAL_CRUZADA_NEGATIVA", narrative_ctx),
                timestamp=timestamp_now,
                provincia=provincia,
                provincia_raw=provincia_raw,
                comunidad_autonoma=territorial.comunidad_autonoma,
                lat=territorial.lat,
                lon=territorial.lon,
                territorial_source=territorial.source,
            ))

        # Cross-selling opportunity (OPORTUNITAT_CREUADA)
        # If client buys Categoria C1 heavily but is missing another category
        cats_bought = set(per_cat.keys())
        all_cats = set(CATEGORIA_TO_BLOQUE.keys())
        missing_cats = all_cats - cats_bought
        
        c1_hist = per_cat.get("Categoria C1")
        if c1_hist is not None and not c1_hist.empty:
            recent_c1 = c1_hist.sort_values("semana").tail(12)
            c1_units = float(recent_c1["unidades_netas"].sum())
            if c1_units > 20:  # Consumo consolidado en Anestesia
                for missing_cat in missing_cats:
                    bloque_missing = CATEGORIA_TO_BLOQUE.get(missing_cat, "Cross")
                    urgency_op = score_urgencia(
                        dnc_estimada=10.0,  # Proxy for potential
                        semanas_fuera_banda=0,
                        indice_madurez="Alto",
                        precio_medio=float(price_lookup.get(missing_cat, 0.0)),
                    )
                    narrative_ctx_op = {
                        "id_cliente": cid,
                        "categoria_h": missing_cat,
                        "bloque": bloque_missing,
                        "indice_madurez": "Alto",
                        "observed_value": c1_units,
                    }
                    client_signals.append(Signal(
                        id_cliente=cid,
                        categoria_h=missing_cat,
                        bloque=bloque_missing,
                        tipo="OPORTUNITAT_CREUADA",
                        semanas_fuera_banda=0,
                        captura_actual=None,
                        captura_historica=None,
                        dnc_estimada=10.0,
                        expected_value=0.0,
                        observed_value=c1_units,
                        confidence_band=(0.0, 0.0),
                        indice_madurez="Alto",
                        score_urgencia=float(urgency_op * 0.8), # Slightly lower urgency than retention
                        impacto_estimado=10.0 * float(price_lookup.get(missing_cat, 0.0)),
                        narrativa=generate_narrative("OPORTUNITAT_CREUADA", narrative_ctx_op),
                        timestamp=timestamp_now,
                        provincia=provincia,
                        provincia_raw=provincia_raw,
                        comunidad_autonoma=territorial.comunidad_autonoma,
                        lat=territorial.lat,
                        lon=territorial.lon,
                        territorial_source=territorial.source,
                    ))

        out.extend(client_signals)

    return sorted(out, key=lambda s: -s.score_urgencia)
