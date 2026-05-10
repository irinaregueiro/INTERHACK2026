"""ETL pipeline: Datasets.xlsx → client_category_week.parquet.

Implements Tareas 1.1–1.6 of plan.md. The output is a single tidy DataFrame
at (id_cliente, categoria_h, semana) that downstream layers consume through
`load_client_history`.

Side outputs written to data/processed/:
  - client_category_week.parquet  (the main weekly series)
  - precio_medio_categoria.parquet (per-categoria_h average unit price)
  - sow_potencial.parquet         (per-(cliente, categoria_h) SoW & potencial)
"""
from __future__ import annotations

import argparse
import logging
from datetime import date
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

from .mappings import (
    CAMPANAS_COLS,
    CATEGORIA_TO_BLOQUE,
    CLIENTES_COLS,
    FAMILIA_TO_CATEGORIA,
    POTENCIAL_FIABLE_RATIO,
    POTENCIAL_COLS,
    PRODUCTOS_COLS,
    REQUIRED_SHEETS,
    SHEET_CAMPANAS,
    SHEET_CLIENTES,
    SHEET_POTENCIAL,
    SHEET_PRODUCTOS,
    SHEET_VENTAS,
    VENTAS_COLS,
    WEEK_FREQ,
)
from .validators import validate_pipeline

log = logging.getLogger(__name__)

# --- Paths -----------------------------------------------------------------

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROC_DIR = ROOT / "data" / "processed"

DEFAULT_RAW_FILE = RAW_DIR / "Datasets.xlsx"
OUT_WEEKLY = PROC_DIR / "client_category_week.parquet"
OUT_PRICE = PROC_DIR / "precio_medio_categoria.parquet"
OUT_POTENCIAL = PROC_DIR / "sow_potencial.parquet"


# --- Loaders ---------------------------------------------------------------


def _read_sheets(xlsx_path: Path) -> dict[str, pd.DataFrame]:
    """Load all required sheets, validating their presence up front."""
    if not xlsx_path.exists():
        raise FileNotFoundError(f"Source Excel not found: {xlsx_path}")
    xl = pd.ExcelFile(xlsx_path)
    missing = set(REQUIRED_SHEETS) - set(xl.sheet_names)
    if missing:
        raise ValueError(f"Missing sheets in {xlsx_path.name}: {sorted(missing)}")
    return {s: pd.read_excel(xl, sheet_name=s) for s in REQUIRED_SHEETS}


def _coerce_id(series: pd.Series) -> pd.Series:
    """Normalize an ID column to clean string form.

    Raw IDs mix short ("14052") and long ("1000100724") integers. Floats with
    trailing ".0" are stripped. NaN becomes empty string and the row is
    expected to be filtered out by the caller if that matters.
    """
    s = series.astype("object")
    return s.map(
        lambda v: ""
        if pd.isna(v)
        else str(int(v)) if isinstance(v, (int, float, np.integer, np.floating)) else str(v).strip()
    )


# --- Steps -----------------------------------------------------------------


def _build_campaign_intervals(df_camp: pd.DataFrame) -> pd.DataFrame:
    """Return a small frame with one row per campaign window."""
    out = pd.DataFrame({
        "campana": df_camp[CAMPANAS_COLS["campana"]].astype(str),
        "fecha_inicio": pd.to_datetime(df_camp[CAMPANAS_COLS["fecha_inicio"]]),
        "fecha_fin": pd.to_datetime(df_camp[CAMPANAS_COLS["fecha_fin"]]),
    })
    return out.dropna()


def _is_campaign_week(week_start: pd.Series, intervals: pd.DataFrame) -> pd.Series:
    """For each ISO-week-Monday, True iff any day of the week intersects a window."""
    if intervals.empty:
        return pd.Series(False, index=week_start.index)
    week_end = week_start + pd.Timedelta(days=6)
    flags = np.zeros(len(week_start), dtype=bool)
    for _, row in intervals.iterrows():
        overlap = (week_start <= row["fecha_fin"]) & (week_end >= row["fecha_inicio"])
        flags |= overlap.to_numpy()
    return pd.Series(flags, index=week_start.index)


def _normalize_ventas(
    ventas: pd.DataFrame,
    productos: pd.DataFrame,
    clientes: pd.DataFrame,
) -> pd.DataFrame:
    """Join Ventas with Productos and Clientes; coerce types; flag huérfanos."""
    v = ventas.copy()
    v[VENTAS_COLS["fecha"]] = pd.to_datetime(v[VENTAS_COLS["fecha"]])

    v = v.rename(columns={
        VENTAS_COLS["num_factura"]: "num_factura",
        VENTAS_COLS["fecha"]: "fecha",
        VENTAS_COLS["id_cliente"]: "id_cliente",
        VENTAS_COLS["id_producto"]: "id_producto",
        VENTAS_COLS["unidades"]: "unidades",
        VENTAS_COLS["valor"]: "valor",
    })
    v["id_cliente"] = _coerce_id(v["id_cliente"])
    v["id_producto"] = _coerce_id(v["id_producto"])

    p = productos.rename(columns={
        PRODUCTOS_COLS["id_producto"]: "id_producto",
        PRODUCTOS_COLS["bloque"]: "bloque",
        PRODUCTOS_COLS["categoria_h"]: "categoria_h",
        PRODUCTOS_COLS["familia_h"]: "familia_h",
    })[["id_producto", "bloque", "categoria_h", "familia_h"]].copy()
    p["id_producto"] = _coerce_id(p["id_producto"])

    n_before = len(v)
    v = v.merge(p, on="id_producto", how="left")
    n_unmapped = v["categoria_h"].isna().sum()
    if n_unmapped:
        log.warning("ETL: %d / %d Ventas rows have no Producto mapping; dropped.",
                    n_unmapped, n_before)
        v = v.dropna(subset=["categoria_h"])

    c = clientes.rename(columns={
        CLIENTES_COLS["id_cliente"]: "id_cliente",
        CLIENTES_COLS["provincia"]: "provincia",
    })[["id_cliente", "provincia"]].copy()
    c["id_cliente"] = _coerce_id(c["id_cliente"])
    c = c.drop_duplicates(subset=["id_cliente"])

    v = v.merge(c, on="id_cliente", how="left")
    v["cliente_huerfano"] = v["provincia"].isna()
    n_huer = v["cliente_huerfano"].sum()
    if n_huer:
        log.info("ETL: %d Ventas rows belong to %d huérfanos.",
                 n_huer, v.loc[v["cliente_huerfano"], "id_cliente"].nunique())
    v["provincia"] = v["provincia"].fillna("Desconocida")
    return v


def _aggregate_weekly(v: pd.DataFrame, campaign_intervals: pd.DataFrame) -> pd.DataFrame:
    """Aggregate normalized invoice lines to weekly (cliente, categoria_h) buckets.

    Week start = Monday of the ISO week that contains `fecha`. Computed
    explicitly because pandas' "W-MON" period anchor labels weeks by their
    *end* Monday, which would shift the first observation a week back.
    """
    v = v.copy()
    days_to_monday = pd.to_timedelta(v["fecha"].dt.weekday, unit="D")
    v["semana"] = (v["fecha"].dt.normalize() - days_to_monday)

    agg = (
        v.groupby(
            ["id_cliente", "categoria_h", "bloque", "provincia", "semana"],
            as_index=False,
        )
        .agg(
            unidades_netas=("unidades", "sum"),
            valor_neto=("valor", "sum"),
            n_facturas=("num_factura", "nunique"),
        )
    )
    agg["is_campaign"] = _is_campaign_week(agg["semana"], campaign_intervals)
    agg["semana"] = agg["semana"].dt.date
    return agg


def _compute_potencial(potencial: pd.DataFrame) -> pd.DataFrame:
    """Pivot Potencial to (id_cliente, categoria_h) with annual potencial units."""
    p = potencial.rename(columns={
        POTENCIAL_COLS["id_cliente"]: "id_cliente",
        POTENCIAL_COLS["familia"]: "familia",
        POTENCIAL_COLS["categoria_productos"]: "categoria_productos",
        POTENCIAL_COLS["potencial"]: "potencial",
    }).copy()
    p["id_cliente"] = _coerce_id(p["id_cliente"])

    # Map Familia → Categoria_H. The data already provides Categoria Productos
    # which equals Categoria_H for the three observed families; we prefer it
    # when present and fall back to FAMILIA_TO_CATEGORIA.
    p["categoria_h"] = p["categoria_productos"].where(
        p["categoria_productos"].notna(),
        p["familia"].map(FAMILIA_TO_CATEGORIA),
    )

    p = (
        p.dropna(subset=["categoria_h"])
        .groupby(["id_cliente", "categoria_h"], as_index=False)
        .agg(potencial=("potencial", "sum"))
    )
    return p


def _compute_sow_and_fiable(
    weekly: pd.DataFrame,
    potencial: pd.DataFrame,
) -> pd.DataFrame:
    """Compute SoW histórico anualizado and the potencial_fiable flag.

    SoW = (annualized observed units) / potencial_declared.
    potencial_fiable = annualized_observed <= POTENCIAL_FIABLE_RATIO * potencial.
    Customers without a declared potencial keep NaN values; downstream
    detectors treat them defensively.
    """
    # Annualize observed units across the full observation window per pair.
    weeks_per_year = 52.0
    span = (
        weekly.groupby(["id_cliente", "categoria_h"])
        .agg(
            unidades_total=("unidades_netas", "sum"),
            n_semanas=("semana", "nunique"),
        )
        .reset_index()
    )
    span["unidades_anualizadas"] = (
        span["unidades_total"] / span["n_semanas"].clip(lower=1)
    ) * weeks_per_year

    sow = span.merge(potencial, on=["id_cliente", "categoria_h"], how="left")
    sow["sow_historico"] = np.where(
        (sow["potencial"].notna()) & (sow["potencial"] > 0),
        sow["unidades_anualizadas"] / sow["potencial"],
        np.nan,
    )
    sow["potencial_fiable"] = np.where(
        sow["potencial"].notna() & (sow["potencial"] > 0),
        sow["unidades_anualizadas"] <= POTENCIAL_FIABLE_RATIO * sow["potencial"],
        False,
    )
    return sow[
        ["id_cliente", "categoria_h", "potencial", "unidades_anualizadas",
         "sow_historico", "potencial_fiable"]
    ]


def _compute_precio_medio(weekly: pd.DataFrame) -> pd.DataFrame:
    """Average unit price per categoria_h, used by urgency scoring."""
    g = (
        weekly.groupby("categoria_h")
        .agg(valor_total=("valor_neto", "sum"), unidades_total=("unidades_netas", "sum"))
        .reset_index()
    )
    g["precio_medio"] = np.where(
        g["unidades_total"] > 0, g["valor_total"] / g["unidades_total"], 0.0
    )
    return g[["categoria_h", "precio_medio"]]


# --- Public API ------------------------------------------------------------


def run_pipeline(
    xlsx_path: Path = DEFAULT_RAW_FILE,
    out_dir: Path = PROC_DIR,
) -> pd.DataFrame:
    """Run the full ETL and persist outputs. Returns the weekly DataFrame."""
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Loading %s ...", xlsx_path)
    sheets = _read_sheets(xlsx_path)

    ventas = sheets[SHEET_VENTAS]
    productos = sheets[SHEET_PRODUCTOS]
    clientes = sheets[SHEET_CLIENTES]
    potencial = sheets[SHEET_POTENCIAL]
    campanas = sheets[SHEET_CAMPANAS]

    norm = _normalize_ventas(ventas, productos, clientes)
    intervals = _build_campaign_intervals(campanas)
    weekly = _aggregate_weekly(norm, intervals)

    pot = _compute_potencial(potencial)
    sow = _compute_sow_and_fiable(weekly, pot)
    price = _compute_precio_medio(weekly)

    validate_pipeline(weekly)

    weekly.to_parquet(OUT_WEEKLY, index=False)
    sow.to_parquet(OUT_POTENCIAL, index=False)
    price.to_parquet(OUT_PRICE, index=False)

    log.info("ETL outputs written to %s", out_dir)
    return weekly


def load_weekly(out_dir: Path = PROC_DIR) -> pd.DataFrame:
    """Load processed weekly DataFrame from parquet."""
    return pd.read_parquet(out_dir / OUT_WEEKLY.name)


def load_sow(out_dir: Path = PROC_DIR) -> pd.DataFrame:
    return pd.read_parquet(out_dir / OUT_POTENCIAL.name)


def load_precio_medio(out_dir: Path = PROC_DIR) -> pd.DataFrame:
    return pd.read_parquet(out_dir / OUT_PRICE.name)


def load_client_history(
    id_cliente: str,
    categoria_h: str,
    out_dir: Path = PROC_DIR,
) -> pd.DataFrame:
    """Return the weekly time series for a single (cliente, categoria_h) pair."""
    df = load_weekly(out_dir)
    return (
        df[(df["id_cliente"] == id_cliente) & (df["categoria_h"] == categoria_h)]
        .sort_values("semana")
        .reset_index(drop=True)
    )


def is_processed_data_available(out_dir: Path = PROC_DIR) -> bool:
    required = (OUT_WEEKLY.name, OUT_POTENCIAL.name, OUT_PRICE.name)
    return all((out_dir / name).exists() for name in required)


# --- CLI -------------------------------------------------------------------


def _main(argv: Optional[list[str]] = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Run the Customer Twin ETL.")
    parser.add_argument("--input", type=Path, default=DEFAULT_RAW_FILE)
    parser.add_argument("--output", type=Path, default=PROC_DIR)
    args = parser.parse_args(argv)
    df = run_pipeline(args.input, args.output)
    print(f"OK: wrote {len(df):,} weekly rows to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
