"""Sanity validators run at the end of the ETL pipeline.

Goal: fail loudly when an invariant breaks rather than silently producing a
broken parquet that downstream layers will misinterpret.
"""
from __future__ import annotations

import logging
from typing import Any

import pandas as pd

from .mappings import CATEGORIA_TO_BLOQUE, MAX_DATE_YEAR, MIN_DATE_YEAR

log = logging.getLogger(__name__)


class ValidationError(Exception):
    """Raised when a hard ETL invariant is violated."""


def validate_pipeline(df: pd.DataFrame) -> dict[str, Any]:
    """Run sanity checks on the final weekly aggregate.

    Returns a small report dict with row count, date span, and counts per
    bloque/categoria. Hard failures raise ValidationError; soft anomalies are
    logged as warnings.
    """
    report: dict[str, Any] = {}

    if df.empty:
        raise ValidationError("Pipeline output is empty.")

    required = {
        "id_cliente", "categoria_h", "bloque", "semana",
        "unidades_netas", "valor_neto", "is_campaign",
        "n_facturas", "provincia",
    }
    missing = required - set(df.columns)
    if missing:
        raise ValidationError(f"Missing required columns: {sorted(missing)}")

    from pandas.api.types import is_string_dtype, is_object_dtype
    if not (is_string_dtype(df["id_cliente"]) or is_object_dtype(df["id_cliente"])):
        raise ValidationError(
            f"id_cliente must be string dtype (got {df['id_cliente'].dtype}); "
            "see Tarea 1.1 in plan.md."
        )

    dups = df.duplicated(subset=["id_cliente", "categoria_h", "semana"]).sum()
    if dups:
        raise ValidationError(
            f"{dups} duplicated (id_cliente, categoria_h, semana) rows."
        )

    semanas = pd.to_datetime(df["semana"])
    yr_min, yr_max = semanas.dt.year.min(), semanas.dt.year.max()
    if yr_min < MIN_DATE_YEAR or yr_max > MAX_DATE_YEAR:
        raise ValidationError(
            f"semana spans {yr_min}-{yr_max}; expected {MIN_DATE_YEAR}-{MAX_DATE_YEAR}."
        )

    cats = set(df["categoria_h"].unique())
    unknown = cats - set(CATEGORIA_TO_BLOQUE.keys())
    if unknown:
        raise ValidationError(f"Unknown categoria_h values: {sorted(unknown)}")

    bad_block = df.loc[
        df["bloque"] != df["categoria_h"].map(CATEGORIA_TO_BLOQUE)
    ]
    if not bad_block.empty:
        raise ValidationError(
            f"{len(bad_block)} rows have bloque inconsistent with categoria_h."
        )

    if (df["unidades_netas"].isna() | df["valor_neto"].isna()).any():
        raise ValidationError("Found NaN in unidades_netas or valor_neto.")

    if (df["n_facturas"] < 0).any():
        raise ValidationError("Negative n_facturas detected.")

    report.update({
        "rows": int(len(df)),
        "clientes": int(df["id_cliente"].nunique()),
        "semanas": int(df["semana"].nunique()),
        "min_date": str(semanas.dt.date.min()),
        "max_date": str(semanas.dt.date.max()),
        "by_bloque": df.groupby("bloque").size().to_dict(),
        "by_categoria": df.groupby("categoria_h").size().to_dict(),
        "campaign_share": float(df["is_campaign"].mean()),
    })

    log.info("ETL validation OK: %s", report)
    return report
