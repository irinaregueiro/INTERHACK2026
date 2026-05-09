"""Interpurchase-time (IPT) twin for technical families (T1 and below).

Default model: log(IPT) ~ Normal(μ, σ²) (log-normal).
Fallback for clients with fewer than MIN_EVENTS_FOR_LOGNORMAL events:
Weibull MLE — more robust on small samples and naturally bounded at 0.

Activation rules implemented:
  DETERIORO_SOSTENIDO_TECNICO  ← silence > P90  AND  positive slope on last 3-4 IPTs
  PAUSA_SOSPECHOSA             ← silence in [P75, P90]
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Optional

import numpy as np
from scipy.special import gamma as gamma_fn
from scipy.stats import lognorm, weibull_min

from etl.mappings import MIN_EVENTS_FOR_LOGNORMAL, SLOPE_WINDOW


def _ipts_from_dates(purchase_dates: list[date]) -> np.ndarray:
    """Days between consecutive purchase dates, sorted ascending."""
    if len(purchase_dates) < 2:
        return np.array([], dtype=float)
    ords = np.array([d.toordinal() for d in sorted(purchase_dates)])
    diffs = np.diff(ords).astype(float)
    return diffs[diffs > 0]  # drop zero-day duplicates if any


@dataclass
class TechnicalTwin:
    """Per-(cliente, categoria_h) interpurchase-time twin."""

    distribution: str = "lognormal"  # 'lognormal' or 'weibull'

    mu: float = field(init=False, default=0.0)
    sigma: float = field(init=False, default=1.0)
    shape: float = field(init=False, default=1.0)
    scale: float = field(init=False, default=1.0)
    ipts: np.ndarray = field(init=False, default_factory=lambda: np.array([]))
    last_purchase: Optional[date] = field(init=False, default=None)
    n_events: int = field(init=False, default=0)

    def fit(self, purchase_dates: list[date]) -> "TechnicalTwin":
        """Estimate IPT distribution parameters from observed purchase dates."""
        if len(purchase_dates) < 2:
            raise ValueError("TechnicalTwin needs at least 2 purchase dates.")

        if len(purchase_dates) < MIN_EVENTS_FOR_LOGNORMAL:
            self.distribution = "weibull"

        ipts = _ipts_from_dates(purchase_dates)
        if ipts.size == 0:
            raise ValueError("All consecutive purchases share the same day.")

        if self.distribution == "lognormal":
            log_ipts = np.log(ipts)
            self.mu = float(log_ipts.mean())
            # ddof=1 to avoid sigma=0 with very few observations.
            self.sigma = float(log_ipts.std(ddof=1) if len(log_ipts) > 1 else 0.5)
            if not np.isfinite(self.sigma) or self.sigma <= 0:
                self.sigma = 0.5
        else:
            shape, _, scale = weibull_min.fit(ipts, floc=0)
            self.shape = float(shape)
            self.scale = float(scale)

        self.ipts = ipts
        self.last_purchase = max(purchase_dates)
        self.n_events = len(purchase_dates)
        return self

    # --- Predictive summaries --------------------------------------------

    def expected_next_purchase_days(self) -> float:
        if self.distribution == "lognormal":
            return float(np.exp(self.mu + self.sigma ** 2 / 2.0))
        return float(self.scale * gamma_fn(1.0 + 1.0 / max(self.shape, 1e-6)))

    def confidence_band_days(self, alpha: float = 0.05) -> tuple[float, float]:
        """[P{alpha/2}, P{1-alpha/2}] of next-event waiting time (days)."""
        if self.distribution == "lognormal":
            lo = float(np.exp(self.mu - 1.96 * self.sigma))
            hi = float(np.exp(self.mu + 1.96 * self.sigma))
            return lo, hi
        lo, hi = weibull_min.ppf([alpha / 2, 1 - alpha / 2], self.shape, scale=self.scale)
        return float(lo), float(hi)

    def quantile_days(self, q: float) -> float:
        if self.distribution == "lognormal":
            return float(lognorm.ppf(q, s=self.sigma, scale=np.exp(self.mu)))
        return float(weibull_min.ppf(q, self.shape, scale=self.scale))

    # --- Activation rules -------------------------------------------------

    def silence_days(self, today: date) -> int:
        if self.last_purchase is None:
            return 0
        return max(0, (today - self.last_purchase).days)

    def is_deterioration(self, today: date) -> bool:
        """Three conditions (campaign clause checked outside):

        1. Silence > P90 of historical IPT.
        2. Positive slope on last SLOPE_WINDOW IPTs (lengthening trend).
        3. Sufficient history (≥3 IPTs).
        """
        if self.ipts.size < 3:
            return False
        silence = self.silence_days(today)
        p90 = self.quantile_days(0.90)
        recent = self.ipts[-SLOPE_WINDOW:]
        if len(recent) < 2:
            return False
        slope = float(np.polyfit(np.arange(len(recent)), recent, 1)[0])
        return silence > p90 and slope > 0.0

    def is_suspicious_pause(self, today: date) -> bool:
        """Silence in [P75, P90] — surveillance only, no action."""
        if self.ipts.size < 2:
            return False
        silence = self.silence_days(today)
        p75 = self.quantile_days(0.75)
        p90 = self.quantile_days(0.90)
        return p75 <= silence <= p90
