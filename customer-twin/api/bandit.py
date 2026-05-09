"""Contextual Multi-Armed Bandit (Thompson Sampling).

Each (segment, arm) pair holds a Beta(α, β) posterior over the binary reward
(client made a qualifying purchase in the 4 weeks following the action).
Cold-start uses uniform Beta(1, 1) priors, per the spec.

For demo purposes the bandit can be pre-seeded with a small batch of
deterministic synthetic interactions so the first round of recommendations is
non-trivial. Real production bandits would only update from real feedback.
"""
from __future__ import annotations

import logging
import threading
from typing import Iterable

import numpy as np

from shared.schemas import ACTION_ARMS, BanditRecommendation

log = logging.getLogger(__name__)


def _magnitude_bucket(divergencia: float) -> str:
    if divergencia is None:
        return "media"
    d = abs(float(divergencia))
    if d > 1.5:
        return "alta"
    if d > 0.7:
        return "media"
    return "baja"


def build_segment(context: dict) -> str:
    """Discretize context into a small bucket key.

    Schema: '<tipo_senal>|<indice_madurez>|<magnitud>'
    """
    return "|".join([
        str(context.get("tipo_senal", "?")),
        str(context.get("indice_madurez", "?")),
        _magnitude_bucket(context.get("divergencia")),
    ])


class ContextualBandit:
    """Thompson Sampling over Beta posteriors per (segment, arm)."""

    ACTIONS: tuple[str, ...] = ACTION_ARMS

    def __init__(self, seed: int | None = 7):
        self._rng = np.random.default_rng(seed)
        self._lock = threading.Lock()
        # posteriors[segment][arm] = (alpha, beta)
        self.posteriors: dict[str, dict[str, tuple[float, float]]] = {}

    # ---- core API ---------------------------------------------------------

    def _ensure_segment(self, segment: str) -> None:
        if segment not in self.posteriors:
            self.posteriors[segment] = {a: (1.0, 1.0) for a in self.ACTIONS}

    def recommend(self, context: dict) -> BanditRecommendation:
        """Sample once per arm, return softmax-normalized probabilities."""
        segment = build_segment(context)
        with self._lock:
            self._ensure_segment(segment)
            arms = self.posteriors[segment]
            samples = {a: float(self._rng.beta(*arms[a])) for a in self.ACTIONS}

        total = sum(samples.values()) or 1.0
        probs = {a: v / total for a, v in samples.items()}
        recommended = max(probs, key=probs.get)
        # Confidence proxy: how much the top arm leads the runner-up.
        ordered = sorted(probs.values(), reverse=True)
        confidence = float(ordered[0] - ordered[1]) if len(ordered) >= 2 else 0.0
        return BanditRecommendation(
            signal_id=context.get("signal_id", ""),
            action_probabilities=probs,
            recommended_action=recommended,
            confidence=confidence,
        )

    def update(self, context: dict, action: str, reward: float) -> None:
        """Apply a Beta-Bernoulli update for the chosen arm."""
        if action not in self.ACTIONS:
            log.warning("bandit.update: unknown action %r — ignored.", action)
            return
        r = 1.0 if reward >= 0.5 else 0.0
        segment = build_segment(context)
        with self._lock:
            self._ensure_segment(segment)
            a, b = self.posteriors[segment][action]
            self.posteriors[segment][action] = (a + r, b + (1 - r))

    # ---- demo helpers -----------------------------------------------------

    def state(self) -> dict[str, dict[str, tuple[float, float]]]:
        with self._lock:
            return {
                seg: {arm: tuple(map(float, ab)) for arm, ab in arms.items()}
                for seg, arms in self.posteriors.items()
            }

    def seed_demo_priors(self, n_interactions: int = 50) -> None:
        """Pre-populate with realistic synthetic interactions.

        Encodes a few stylized facts so the demo shows the bandit "knows"
        useful patterns without requiring weeks of real feedback:

          * High-magnitude FUGA → visita presencial works best
          * Low-magnitude PAUSA  → email is enough
          * DETERIORO_SOSTENIDO_TECNICO → muestra works for high maturity, llamada otherwise
          * DEMANDA_NO_CAPTURADA → llamada / muestra outperform monitorizar

        Determinism: uses the bandit's own RNG; calling on a fresh instance
        with the same seed yields the same posteriors.
        """
        # (signal_type, maturity, magnitude, best_arm, success_prob)
        scenarios: list[tuple[str, str, str, str, float]] = [
            ("FUGA_PARCIAL_COMMODITY",  "Alto",  "alta",  "visita",      0.75),
            ("FUGA_PARCIAL_COMMODITY",  "Medio", "alta",  "llamada",     0.68),
            ("FUGA_PARCIAL_COMMODITY",  "Alto",  "media", "llamada",     0.62),
            ("PAUSA_SOSPECHOSA",        "Alto",  "baja",  "email",       0.55),
            ("PAUSA_SOSPECHOSA",        "Medio", "baja",  "email",       0.50),
            ("DETERIORO_SOSTENIDO_TECNICO", "Alto",  "alta",  "muestra", 0.72),
            ("DETERIORO_SOSTENIDO_TECNICO", "Medio", "alta",  "llamada", 0.60),
            ("DEMANDA_NO_CAPTURADA",    "Alto",  "media", "muestra",     0.65),
            ("DEMANDA_NO_CAPTURADA",    "Medio", "media", "llamada",     0.58),
            ("CAMPAIGN_NO_RESPONSE",    "Alto",  "media", "email",       0.55),
            ("SEÑAL_CRUZADA_NEGATIVA",  "Alto",  "alta",  "visita",      0.78),
        ]

        per_scenario = max(1, n_interactions // len(scenarios))

        for tipo, mat, mag, best_arm, p_best in scenarios:
            ctx = {"tipo_senal": tipo, "indice_madurez": mat, "divergencia": {
                "alta": 2.0, "media": 1.0, "baja": 0.3
            }[mag]}
            for _ in range(per_scenario):
                # Best arm gets reward with p_best; other arms with low probability
                for arm in self.ACTIONS:
                    p = p_best if arm == best_arm else 0.18
                    reward = 1.0 if self._rng.random() < p else 0.0
                    self.update(ctx, arm, reward)
        log.info("Bandit seeded with %d scenarios × %d ≈ %d interactions",
                 len(scenarios), per_scenario, len(scenarios) * per_scenario)


def context_for_signal(signal) -> dict:
    """Build the discretized context dict from a Signal."""
    expected = signal.expected_value or 1.0
    observed = signal.observed_value or 0.0
    divergencia = abs(observed - expected) / max(abs(expected), 1.0)
    return {
        "signal_id": signal.signal_id,
        "tipo_senal": signal.tipo,
        "indice_madurez": signal.indice_madurez,
        "divergencia": divergencia,
        "categoria_h": signal.categoria_h,
        "provincia": signal.provincia,
    }
