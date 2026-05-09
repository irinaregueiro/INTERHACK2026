"""Poisson-Gamma twin for commodity families (C1, C2).

Likelihood:        Y_t | λ ~ Poisson(λ)
Conjugate prior:   λ ~ Gamma(α, β)
Posterior:         λ | Y ~ Gamma(α + ΣY_t, β + T)
Predictive:        Y_{T+1} ~ NegBin(α + ΣY_t, β/(β+1))

Campaign weeks are excluded from the parametric fit by the caller via
`exclude_campaigns` (they remain available for CAMPAIGN_NO_RESPONSE detection).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
from scipy.stats import nbinom

from etl.mappings import DEFAULT_PRIOR_ALPHA, DEFAULT_PRIOR_BETA, MIN_WEEKS_FOR_OWN_PRIOR


@dataclass
class CommodityTwin:
    """Per-(cliente, categoria_h) Poisson-Gamma twin.

    Parameters
    ----------
    alpha_prior : Gamma shape prior. Higher = stronger pull towards population.
    beta_prior  : Gamma rate prior. Acts as effective number of prior weeks.
    population_lambda : optional informed prior for cold-start clients
        (typically the family-wide mean λ). When provided and the client has
        fewer than MIN_WEEKS_FOR_OWN_PRIOR observations, alpha/beta are
        re-derived to match this mean with low precision.
    """

    alpha_prior: float = DEFAULT_PRIOR_ALPHA
    beta_prior: float = DEFAULT_PRIOR_BETA
    population_lambda: Optional[float] = None

    # State (set by .fit())
    alpha_post: float = field(init=False, default=0.0)
    beta_post: float = field(init=False, default=0.0)
    lambda_hat: float = field(init=False, default=0.0)
    n_used: int = field(init=False, default=0)

    def fit(
        self,
        weekly_units: np.ndarray,
        exclude_campaigns: Optional[np.ndarray] = None,
    ) -> "CommodityTwin":
        """Compute posterior from observed weekly units.

        weekly_units : array of non-negative weekly unit sums.
        exclude_campaigns : boolean mask, True = drop that week from the fit.
        """
        weekly_units = np.asarray(weekly_units, dtype=float)
        weekly_units = np.clip(weekly_units, a_min=0.0, a_max=None)

        if exclude_campaigns is None:
            mask = np.zeros(len(weekly_units), dtype=bool)
        else:
            mask = np.asarray(exclude_campaigns, dtype=bool)

        clean = weekly_units[~mask]

        # Cold-start: weak informed prior centered on population mean.
        if len(clean) < MIN_WEEKS_FOR_OWN_PRIOR and self.population_lambda is not None:
            # Encode pop mean with effective sample size 2 (low precision).
            self.alpha_post = max(self.population_lambda * 2.0, 1e-3)
            self.beta_post = 2.0
        else:
            self.alpha_post = self.alpha_prior + float(clean.sum())
            self.beta_post = self.beta_prior + float(len(clean))

        self.lambda_hat = self.alpha_post / max(self.beta_post, 1e-9)
        self.n_used = int(len(clean))
        return self

    def predict_distribution(self) -> "nbinom":
        """Return scipy.stats.nbinom predictive distribution for next week."""
        n = self.alpha_post
        p = self.beta_post / (self.beta_post + 1.0)
        return nbinom(n, p)

    def confidence_band(self, alpha: float = 0.05) -> tuple[float, float]:
        """[lo, hi] containing (1-alpha) of predicted weekly units."""
        d = self.predict_distribution()
        return float(d.ppf(alpha / 2)), float(d.ppf(1 - alpha / 2))

    def expected_units(self) -> float:
        return float(self.predict_distribution().mean())

    def divergence_score(self, observed: float) -> float:
        """Standardized residual of observed vs predictive."""
        d = self.predict_distribution()
        std = float(d.std())
        if std <= 0:
            return 0.0
        return (float(observed) - float(d.mean())) / std

    def quantile(self, q: float) -> float:
        return float(self.predict_distribution().ppf(q))


def fit_population_lambda(units_by_week: np.ndarray) -> float:
    """Convenience: family-wide average weekly units, used as cold-start prior."""
    arr = np.asarray(units_by_week, dtype=float)
    arr = arr[~np.isnan(arr)]
    if len(arr) == 0:
        return 0.0
    return float(np.clip(arr.mean(), 0.0, None))
