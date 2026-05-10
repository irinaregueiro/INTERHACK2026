"""Shared Pydantic data contracts.

Single source of truth for the boundaries between ETL, models, bandit, and API.
Every layer must import from here rather than redefining structures locally.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Literal, Optional
from pydantic import BaseModel, Field

# --- Domain enumerations --------------------------------------------------

SignalType = Literal[
    "FUGA_PARCIAL_COMMODITY",
    "DEMANDA_NO_CAPTURADA",
    "DETERIORO_SOSTENIDO_TECNICO",
    "PAUSA_SOSPECHOSA",
    "CAMPAIGN_NO_RESPONSE",
    "SEÑAL_CRUZADA_NEGATIVA",
    "OPORTUNITAT_CREUADA",
]

Bloque = Literal["Commodities", "Productos Técnicos", "Cross"]

MaturityLevel = Literal["Alto", "Medio", "Bajo"]

CategoriaH = Literal["Categoria C1", "Categoria C2", "Categoria T1", "TODAS"]

ALL_SIGNAL_TYPES: tuple[str, ...] = (
    "FUGA_PARCIAL_COMMODITY",
    "DEMANDA_NO_CAPTURADA",
    "DETERIORO_SOSTENIDO_TECNICO",
    "PAUSA_SOSPECHOSA",
    "CAMPAIGN_NO_RESPONSE",
    "SEÑAL_CRUZADA_NEGATIVA",
    "OPORTUNITAT_CREUADA",
)

ACTION_ARMS: tuple[str, ...] = ("visita", "llamada", "email", "muestra", "monitorizar")

# --- Schemas ---------------------------------------------------------------


class ClientFamilyWeek(BaseModel):
    """Weekly aggregate at (id_cliente, categoria_h, semana).

    Output of the ETL layer, input of the twin models.
    `id_cliente` is a string because raw IDs mix short (e.g. "14052") and long
    (e.g. "1000100724") numeric forms; coercing to int risks losing leading
    zeros and is rejected by the ETL contract (Tarea 1.1).
    """

    id_cliente: str
    categoria_h: str
    bloque: str
    semana: date
    unidades_netas: float
    valor_neto: float
    is_campaign: bool
    n_facturas: int
    provincia: str


class Signal(BaseModel):
    """Detected divergence emitted by the signal detector.

    `bloque` is included so the documented `/api/signals?bloque=` filter is
    implementable without re-joining the categoria→bloque map at the API layer.
    """

    id_cliente: str
    categoria_h: str
    bloque: str
    tipo: SignalType
    semanas_fuera_banda: int
    captura_actual: Optional[float] = None  # None for technical signals
    captura_historica: Optional[float] = None
    dnc_estimada: Optional[float] = None
    expected_value: float
    observed_value: float
    confidence_band: tuple[float, float]
    indice_madurez: MaturityLevel
    score_urgencia: float
    impacto_estimado: Optional[float] = None  # EUR impact for ROI calculations
    narrativa: str
    timestamp: datetime
    provincia: Optional[str] = None              # canonical provincia (or None if unmapped)
    provincia_raw: Optional[str] = None          # raw value seen in the dataset (debug / audit)
    comunidad_autonoma: Optional[str] = None     # canonical CCAA name
    lat: Optional[float] = None                  # capital approx — for proportional-symbol map
    lon: Optional[float] = None
    territorial_source: Optional[str] = None     # 'name' | 'postal' | 'city' | 'unknown' | 'non_spain'

    @property
    def signal_id(self) -> str:
        """Deterministic identifier: '<id_cliente>|<categoria_h>|<tipo>'.

        Stable across runs so the frontend can deep-link or cache by id.
        Returned in raw form (with '|' and spaces); HTTP clients must
        percent-encode when embedding in URL paths (FastAPI auto-decodes
        path parameters on the server side).
        """
        return f"{self.id_cliente}|{self.categoria_h}|{self.tipo}"


def parse_signal_id(signal_id: str) -> tuple[str, str, str]:
    """Inverse of `Signal.signal_id`. Accepts both raw and percent-encoded."""
    from urllib.parse import unquote

    raw = unquote(signal_id)
    parts = raw.split("|")
    if len(parts) != 3:
        raise ValueError(f"Invalid signal_id: {signal_id!r}")
    return parts[0], parts[1], parts[2]


class BanditRecommendation(BaseModel):
    """Output of the contextual bandit at decision time."""

    signal_id: str
    action_probabilities: dict[str, float] = Field(
        default_factory=dict,
        description="Maps arm name (visita/llamada/...) to its sampled probability mass.",
    )
    recommended_action: str
    confidence: float = Field(
        ge=0.0,
        le=1.0,
        description="0-1; high values mean the bandit has clear preference for the recommended arm.",
    )
