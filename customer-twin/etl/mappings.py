"""Configurable constants and lookup tables for the ETL layer.

Anything that depends on the source-file conventions (sheet names, column
names, business mappings) lives here so a single edit updates all consumers.
The values reflect the actual headers observed in `Datasets.xlsx`.
"""
from __future__ import annotations

# --- Sheet names -----------------------------------------------------------

SHEET_VENTAS = "Ventas"
SHEET_PRODUCTOS = "Productos"
SHEET_CLIENTES = "Clientes"
SHEET_POTENCIAL = "Potencial"
SHEET_CAMPANAS = "Campañas"

REQUIRED_SHEETS: tuple[str, ...] = (
    SHEET_VENTAS,
    SHEET_PRODUCTOS,
    SHEET_CLIENTES,
    SHEET_POTENCIAL,
    SHEET_CAMPANAS,
)

# --- Column names (per sheet) ---------------------------------------------
# NOTE: column names in the source file are inconsistent across sheets
# ("Id. Cliente" vs "Id.Cliente"). They are normalized to canonical names
# inside `pipeline.py`.

VENTAS_COLS = {
    "num_factura": "Num.Fact",
    "fecha": "Fecha",
    "id_cliente": "Id. Cliente",
    "id_producto": "Id. Producto",
    "unidades": "Unidades",
    "valor": "Valores_H",
}

PRODUCTOS_COLS = {
    "id_producto": "Id.Prod",
    "bloque": "Bloque analítico",
    "categoria_h": "Categoria_H",
    "familia_h": "Familia_H",
}

CLIENTES_COLS = {
    "id_cliente": "Id. Cliente",
    "provincia": "Provincia",
}

POTENCIAL_COLS = {
    "id_cliente": "Id.Cliente",
    "familia": "Familia",
    "categoria_productos": "Categoria Productos",
    "potencial": "Potencial_H",
}

CAMPANAS_COLS = {
    "campana": "Campaña",
    "fecha_inicio": "Fecha inicio",
    "fecha_fin": "Fecha fin",
}

# --- Business mappings -----------------------------------------------------

CATEGORIA_TO_BLOQUE: dict[str, str] = {
    "Categoria C1": "Commodities",
    "Categoria C2": "Commodities",
    "Categoria T1": "Productos Técnicos",
}

# Map between Potencial.Familia (commercial label) and Productos.Categoria_H.
# Inferred from the 1:1 correspondence in the dataset:
#   Anestesia    -> Categoria C1
#   Bioseguridad -> Categoria C2
#   Biomateriales-> Categoria T1
FAMILIA_TO_CATEGORIA: dict[str, str] = {
    "Anestesia": "Categoria C1",
    "Bioseguridad": "Categoria C2",
    "Biomateriales": "Categoria T1",
}

# --- Configurable thresholds (twin + detector) ----------------------------

DEFAULT_PRIOR_ALPHA = 1.0
DEFAULT_PRIOR_BETA = 1.0

MIN_WEEKS_FOR_OWN_PRIOR = 8           # spec: ≥8 weeks → fit own prior
MIN_EVENTS_FOR_LOGNORMAL = 4          # IPT: ≥4 events → log-normal, else Weibull
SLOPE_WINDOW = 4                      # last 3-4 IPTs for trend slope

POTENCIAL_FIABLE_RATIO = 1.2          # venta_anualizada ≤ 1.2 * potencial
SOW_DNC_THRESHOLD = 0.50              # DEMANDA_NO_CAPTURADA: SoW never > 50%
FUGA_PARCIAL_CONSEC_WEEKS = 3         # ≥3 consecutive weeks below P25
CROSS_NEGATIVE_MIN_FAMILIES = 2       # signal cruzada: drop in ≥2 families simultaneously

# Urgency scoring weights
URGENCY_W_IMPACTO = 0.5
URGENCY_W_PERSISTENCIA = 0.3
URGENCY_W_MADUREZ = 0.2

MADUREZ_FACTOR: dict[str, float] = {"Alto": 1.0, "Medio": 0.7, "Bajo": 0.3}

# --- Time discretization ---------------------------------------------------

WEEK_FREQ = "W-MON"  # ISO week, anchored to Monday

# --- Data ranges sanity ----------------------------------------------------

MIN_DATE_YEAR = 2021
MAX_DATE_YEAR = 2025
