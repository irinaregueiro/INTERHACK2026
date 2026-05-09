"""FastAPI application — orchestrates ETL output, signals, bandit and voice.

Endpoints (per plan.md):
    GET  /api/signals
    GET  /api/signals/{id}/detail
    POST /api/signals/{id}/feedback
    POST /api/signals/{id}/voice_briefing
    GET  /api/territorial_alerts            (optional)
    GET  /api/health                        (operational)

Behaviour when processed data is missing:
    - The first call to any data-bound endpoint runs detection on the cached
      parquet if available. If neither parquet nor a previous run is found,
      the API falls back to mock signals served from `demo/mock_signals.py`,
      sets the response header `X-Data-Source: mock`, and logs a warning.
"""
from __future__ import annotations

import logging
import os
from collections import Counter
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

# Load .env (if present) before any module reads os.environ. The file lives
# at the project root next to this file's parent directory.
try:
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / ".env")
except ImportError:  # pragma: no cover - dotenv is in requirements.txt
    pass

import pandas as pd
from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from etl.pipeline import (
    PROC_DIR,
    is_processed_data_available,
    load_precio_medio,
    load_sow,
    load_weekly,
)
from models.signal_detector import run_detection
from shared.schemas import (
    ALL_SIGNAL_TYPES,
    BanditRecommendation,
    Signal,
    parse_signal_id,
)

from .bandit import ContextualBandit, context_for_signal
from .voice import VoiceDisabledError, is_enabled as voice_is_enabled, synthesize

log = logging.getLogger(__name__)

# --- App + middleware ------------------------------------------------------

app = FastAPI(
    title="Customer Twin API",
    description="Probabilistic digital-twin signals + adaptive recommender.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Data-Source"],
)


# --- App-level state -------------------------------------------------------


class _State:
    signals: list[Signal] = []
    weekly: Optional[pd.DataFrame] = None
    sow: Optional[pd.DataFrame] = None
    precio: Optional[pd.DataFrame] = None
    bandit: ContextualBandit = ContextualBandit(seed=7)
    data_source: str = "unknown"  # "real" | "mock"
    # In-memory lifecycle state per signal_id. Persists while the API process
    # is alive; resets on restart (acceptable for MVP / demo).
    signal_status: dict[str, dict] = {}


STATE = _State()
STATE.bandit.seed_demo_priors(n_interactions=50)


# --- Lifecycle constants ---------------------------------------------------

VALID_STATUSES: set[str] = {
    "active",
    "in_progress",
    "watching",
    "dismissed",
    "high_priority",
    "resolved",
}
ACTIONABLE_STATUSES: set[str] = {"active", "high_priority", "in_progress"}
VALID_OUTCOMES: set[str] = {"acted", "false_alarm", "priority_up", "watching"}

DEFAULT_STATUS: dict = {
    "status": "active",
    "action_taken": None,
    "priority": 0,
    "dismiss_reason": None,
    "updated_at": None,
}


# --- Loading ---------------------------------------------------------------


def _load_real_signals(max_clients: int | None = None) -> list[Signal]:
    weekly = load_weekly()
    sow = load_sow()
    precio = load_precio_medio()
    STATE.weekly, STATE.sow, STATE.precio = weekly, sow, precio
    return run_detection(weekly, sow, precio, max_clients=max_clients)


def _load_mock_signals() -> list[Signal]:
    from .demo_signals import build_mock_signals  # local import → mock-only path
    return build_mock_signals()


@app.on_event("startup")
def _bootstrap() -> None:
    """Load signals once at startup. Cap to 1500 clients for snappy demos."""
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    cap = int(os.getenv("CT_MAX_CLIENTS", "1500"))
    if is_processed_data_available():
        try:
            STATE.signals = _load_real_signals(max_clients=cap)
            STATE.data_source = "real"
            log.info("API booted with %d real signals (cap=%d clients).",
                     len(STATE.signals), cap)
            return
        except Exception as e:  # pragma: no cover - hardening
            log.exception("Real signal loading failed; falling back to mock: %s", e)
    log.warning("Processed parquet not found — serving MOCK signals.")
    STATE.signals = _load_mock_signals()
    STATE.data_source = "mock"


# --- Helpers ---------------------------------------------------------------


def _signals_index() -> dict[str, Signal]:
    return {s.signal_id: s for s in STATE.signals}


def _attach_data_source(response: Response) -> None:
    response.headers["X-Data-Source"] = STATE.data_source


def _status_for(signal_id: str) -> dict:
    """Return the current lifecycle record for a signal (defaults to active)."""
    return dict(STATE.signal_status.get(signal_id) or DEFAULT_STATUS)


def _set_status(
    signal_id: str,
    *,
    status: Optional[str] = None,
    action_taken: Optional[str] = None,
    priority: Optional[int] = None,
    dismiss_reason: Optional[str] = None,
) -> dict:
    rec = STATE.signal_status.get(signal_id) or dict(DEFAULT_STATUS)
    if status is not None:
        rec["status"] = status
    if action_taken is not None:
        rec["action_taken"] = action_taken
    if priority is not None:
        rec["priority"] = priority
    if dismiss_reason is not None:
        rec["dismiss_reason"] = dismiss_reason
    rec["updated_at"] = datetime.now().isoformat(timespec="seconds")
    STATE.signal_status[signal_id] = rec
    return rec


def _history_for_chart(signal: Signal, n_weeks: int = 16) -> list[dict]:
    """Return last `n_weeks` of weekly aggregates for the chart, plus band lines."""
    if STATE.weekly is None or signal.categoria_h == "TODAS":
        # Fallback: synthetic series anchored on the band. Used in mock mode.
        today = date.today()
        out = []
        lo, hi = signal.confidence_band
        center = signal.expected_value
        for i in range(n_weeks):
            wk = today - timedelta(days=7 * (n_weeks - i - 1))
            out.append({
                "semana": wk.isoformat(),
                "observed": float(max(0.0, center * 0.9 + (i % 3) * 1.5)),
                "expected": float(center),
                "band_lo": float(lo),
                "band_hi": float(hi),
                "is_campaign": False,
            })
        # Make the last point reflect the alert
        out[-1]["observed"] = float(signal.observed_value)
        return out

    # Reindex to a continuous weekly grid so zero-purchase weeks render properly.
    from models.signal_detector import reindex_full_weekly

    raw = STATE.weekly[
        (STATE.weekly["id_cliente"] == signal.id_cliente)
        & (STATE.weekly["categoria_h"] == signal.categoria_h)
    ]
    if raw.empty:
        return []

    today_ref = max(STATE.weekly["semana"]) if STATE.weekly is not None else date.today()
    full = reindex_full_weekly(raw, today_ref).tail(n_weeks)

    lo, hi = signal.confidence_band
    expected = signal.expected_value
    rows = []
    for _, r in full.iterrows():
        sem = r["semana"]
        rows.append({
            "semana": sem.isoformat() if hasattr(sem, "isoformat") else str(sem),
            "observed": float(r["unidades_netas"]),
            "expected": float(expected),
            "band_lo": float(lo),
            "band_hi": float(hi),
            "is_campaign": bool(r["is_campaign"]),
        })
    return rows


# --- Endpoints -------------------------------------------------------------


@app.get("/api/health")
def health() -> dict:
    return {
        "status": "ok",
        "data_source": STATE.data_source,
        "n_signals": len(STATE.signals),
        "voice_enabled": voice_is_enabled(),
        "now": datetime.now().isoformat(timespec="seconds"),
    }


@app.get("/api/signals")
def list_signals(
    response: Response,
    tipo: Optional[str] = Query(None, description="Filter by signal type."),
    bloque: Optional[str] = Query(None, description="Filter by bloque."),
    provincia: Optional[str] = Query(None),
    status: Optional[str] = Query(
        None,
        description=(
            "Filter by lifecycle status. Omit (default) to return actionable "
            "signals (everything except 'dismissed'). Use a concrete value "
            "(e.g. 'dismissed', 'in_progress') to filter explicitly."
        ),
    ),
    limit: int = Query(50, ge=1, le=500),
) -> list[dict]:
    """Active signals ordered by priority then descending urgency score."""
    _attach_data_source(response)
    signals = STATE.signals
    if tipo:
        if tipo not in ALL_SIGNAL_TYPES:
            raise HTTPException(400, detail=f"Unknown tipo {tipo!r}.")
        signals = [s for s in signals if s.tipo == tipo]
    if bloque:
        signals = [s for s in signals if s.bloque == bloque]
    if provincia:
        signals = [s for s in signals if (s.provincia or "").lower() == provincia.lower()]

    if status is not None and status not in VALID_STATUSES:
        raise HTTPException(400, detail=f"Unknown status {status!r}.")

    enriched = [(s, _status_for(s.signal_id)) for s in signals]
    if status:
        enriched = [(s, st) for s, st in enriched if st["status"] == status]
    else:
        # Default view: hide dismissed alerts so the list stays actionable.
        enriched = [(s, st) for s, st in enriched if st["status"] != "dismissed"]

    enriched.sort(key=lambda t: (-int(t[1].get("priority", 0)), -t[0].score_urgencia))
    enriched = enriched[:limit]

    return [{
        "signal_id": s.signal_id,
        "id_cliente": s.id_cliente,
        "categoria_h": s.categoria_h,
        "bloque": s.bloque,
        "tipo": s.tipo,
        "semanas_fuera_banda": s.semanas_fuera_banda,
        "score_urgencia": round(s.score_urgencia, 4),
        "indice_madurez": s.indice_madurez,
        "provincia": s.provincia,
        "narrativa": s.narrativa,
        "status": st["status"],
        "action_taken": st["action_taken"],
        "priority": st["priority"],
        "updated_at": st["updated_at"],
        "dismiss_reason": st["dismiss_reason"],
    } for s, st in enriched]


@app.get("/api/signals/counts")
def signal_counts(response: Response) -> dict:
    _attach_data_source(response)
    by_tipo = Counter(s.tipo for s in STATE.signals)
    by_bloque = Counter(s.bloque for s in STATE.signals)
    by_madurez = Counter(s.indice_madurez for s in STATE.signals)
    by_status: Counter = Counter()
    for s in STATE.signals:
        st = _status_for(s.signal_id)
        by_status[st["status"]] += 1
    actionable_total = sum(c for k, c in by_status.items() if k in ACTIONABLE_STATUSES)
    return {
        "total": len(STATE.signals),
        "actionable_total": actionable_total,
        "by_tipo": dict(by_tipo),
        "by_bloque": dict(by_bloque),
        "by_madurez": dict(by_madurez),
        "by_status": dict(by_status),
    }


@app.get("/api/signals/{signal_id}/detail")
def signal_detail(signal_id: str, response: Response) -> dict:
    _attach_data_source(response)
    idx = _signals_index()
    if signal_id not in idx:
        raise HTTPException(404, detail=f"Signal {signal_id!r} not found.")
    signal = idx[signal_id]
    bandit_rec = STATE.bandit.recommend(context_for_signal(signal))
    return {
        "signal": signal.model_dump(),
        "status": _status_for(signal_id),
        "history": _history_for_chart(signal),
        "bandit": bandit_rec.model_dump(),
    }


class FeedbackBody(BaseModel):
    action: str
    outcome: str  # 'acted' | 'false_alarm' | 'priority_up' | 'watching'
    reason: Optional[str] = None  # optional dismiss reason


@app.post("/api/signals/{signal_id}/feedback")
def submit_feedback(signal_id: str, body: FeedbackBody, response: Response) -> dict:
    """Combined endpoint: registers the lifecycle transition and, when the
    outcome carries reward information, also updates the bandit posterior.

    Reward semantics (intentionally narrow — most outcomes don't update it):
        * acted        → bandit reward 1.0 (acceptance proxy; not the real
                         4-week sales outcome — see note below).
        * false_alarm  → bandit reward 0.0 (genuine negative signal).
        * priority_up  → no bandit update (operational priority, not reward).
        * watching     → no bandit update (deferred decision).
    """
    _attach_data_source(response)
    idx = _signals_index()
    if signal_id not in idx:
        raise HTTPException(404, detail=f"Signal {signal_id!r} not found.")
    if body.outcome not in VALID_OUTCOMES:
        raise HTTPException(400, detail=f"Invalid outcome {body.outcome!r}.")
    signal = idx[signal_id]
    ctx = context_for_signal(signal)

    new_status: Optional[str] = None
    action_taken: Optional[str] = None
    priority: Optional[int] = None
    dismiss_reason: Optional[str] = body.reason

    if body.outcome == "acted":
        # User accepted the recommendation. We treat 'monitorizar' as a soft
        # decision (watching) rather than an in-progress task.
        if body.action == "monitorizar":
            new_status = "watching"
        else:
            new_status = "in_progress"
        action_taken = body.action
        # NOTE: this is an *acceptance* signal, not the real commercial outcome
        # (which would arrive after ~4 weeks of follow-up sales). Kept as a
        # reward update for demo continuity so the bandit still learns from
        # commercial intent, but a production pipeline should distinguish
        # acceptance from the eventual conversion outcome.
        STATE.bandit.update(ctx, body.action, 1.0)
    elif body.outcome == "false_alarm":
        new_status = "dismissed"
        STATE.bandit.update(ctx, body.action, 0.0)
    elif body.outcome == "priority_up":
        new_status = "high_priority"
        priority = 1
        # Intentionally NO bandit update — operator priority is not a reward.
    elif body.outcome == "watching":
        new_status = "watching"
        action_taken = "monitorizar"
        # No bandit update.

    rec = _set_status(
        signal_id,
        status=new_status,
        action_taken=action_taken,
        priority=priority,
        dismiss_reason=dismiss_reason,
    )
    return {
        "status": "ok",
        "signal_status": rec,
        "bandit_recommendation": STATE.bandit.recommend(ctx).model_dump(),
    }


@app.post("/api/signals/{signal_id}/voice_briefing")
def voice_briefing(signal_id: str, request: Request, response: Response) -> dict:
    _attach_data_source(response)
    idx = _signals_index()
    if signal_id not in idx:
        raise HTTPException(404, detail=f"Signal {signal_id!r} not found.")
    signal = idx[signal_id]
    if not voice_is_enabled():
        raise HTTPException(
            503,
            detail={
                "error": "voice_disabled",
                "message": "Set ELEVENLABS_API_KEY to enable voice briefing.",
            },
        )
    try:
        result = synthesize(signal.narrativa)
    except VoiceDisabledError as e:
        raise HTTPException(503, detail={"error": "voice_disabled", "message": str(e)})
    except Exception as e:  # pragma: no cover - network errors
        log.exception("ElevenLabs synthesis failed: %s", e)
        raise HTTPException(502, detail={"error": "tts_failed", "message": str(e)})

    base = str(request.base_url).rstrip("/")
    return {
        "audio_url": f"{base}/api/audio/{result.audio_path.name}",
        "cached": result.cached,
        "voice_id": result.voice_id,
    }


@app.get("/api/audio/{filename}")
def serve_audio(filename: str) -> FileResponse:
    from .voice import CACHE_DIR
    path = CACHE_DIR / filename
    if not path.exists() or not filename.endswith(".mp3"):
        raise HTTPException(404, detail="audio not found")
    return FileResponse(path, media_type="audio/mpeg")


@app.get("/api/territorial_alerts")
def territorial_alerts(response: Response, weeks: int = 4, min_count: int = 3) -> list[dict]:
    """Provinces with ≥`min_count` FUGA_PARCIAL_COMMODITY alerts in the last `weeks` weeks.

    The dataset is a static historical snapshot, so "in the last `weeks` weeks"
    refers to the timestamp of signal generation (which is `now`). For an MVP
    demo we treat all currently-active FUGA signals as the recent window.
    """
    _attach_data_source(response)
    counts = Counter()
    for s in STATE.signals:
        if s.tipo == "FUGA_PARCIAL_COMMODITY" and s.provincia:
            counts[(s.provincia, s.categoria_h)] += 1
    out = [
        {"provincia": prov, "categoria_h": cat, "n_alertas": n}
        for (prov, cat), n in counts.items()
        if n >= min_count
    ]
    return sorted(out, key=lambda d: -d["n_alertas"])


@app.post("/api/admin/reload")
def reload_data() -> dict:
    """Re-run detection from disk (admin-only; useful after re-running ETL)."""
    if not is_processed_data_available():
        raise HTTPException(503, detail="Processed data unavailable.")
    cap = int(os.getenv("CT_MAX_CLIENTS", "1500"))
    STATE.signals = _load_real_signals(max_clients=cap)
    STATE.data_source = "real"
    return {"status": "ok", "n_signals": len(STATE.signals)}
