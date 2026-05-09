"""Thin re-export of urgency scoring so the API has a single import path.

The actual implementation lives next to the detector to avoid circular
dependencies. This module also exposes a small helper to refresh the score
of an existing Signal after threshold changes (without re-running the twins).
"""
from __future__ import annotations

from models.signal_detector import score_urgencia
from shared.schemas import Signal

__all__ = ["score_urgencia", "rescore"]


def rescore(signal: Signal, precio_medio: float) -> Signal:
    """Return a copy of `signal` with `score_urgencia` recomputed."""
    new_score = score_urgencia(
        dnc_estimada=signal.dnc_estimada,
        semanas_fuera_banda=signal.semanas_fuera_banda,
        indice_madurez=signal.indice_madurez,
        precio_medio=precio_medio,
    )
    return signal.model_copy(update={"score_urgencia": float(new_score)})
