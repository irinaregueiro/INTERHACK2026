"""Mock signals used as a fallback when processed data is missing.

This file is the *only* place where fake signals are constructed. The API
flips to mock mode automatically when the parquet output of the ETL is
absent; in that case the response includes `X-Data-Source: mock` so a UI can
show a banner.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from etl.territorial import normalize_provincia
from shared.schemas import Signal


def build_mock_signals() -> list[Signal]:
    """Return ~10 hand-crafted signals covering all 6 taxonomy types."""
    now = datetime.now()
    out: list[Signal] = []

    samples: list[dict] = [
        dict(
            id_cliente="1000123456", categoria_h="Categoria C1", bloque="Commodities",
            tipo="FUGA_PARCIAL_COMMODITY", semanas_fuera_banda=4, captura_actual=18.0,
            captura_historica=42.0, dnc_estimada=12.0, expected_value=160.0,
            observed_value=72.0, confidence_band=(120.0, 200.0),
            indice_madurez="Alto", score_urgencia=0.82, provincia="Madrid",
            impacto_estimado=240.0,
        ),
        dict(
            id_cliente="1000234567", categoria_h="Categoria C2", bloque="Commodities",
            tipo="FUGA_PARCIAL_COMMODITY", semanas_fuera_banda=3, captura_actual=8.0,
            captura_historica=24.0, dnc_estimada=9.0, expected_value=80.0,
            observed_value=24.0, confidence_band=(56.0, 104.0),
            indice_madurez="Medio", score_urgencia=0.74, provincia="Barcelona",
            impacto_estimado=180.0,
        ),
        dict(
            id_cliente="1000345678", categoria_h="Categoria T1", bloque="Productos Técnicos",
            tipo="DETERIORO_SOSTENIDO_TECNICO", semanas_fuera_banda=6, captura_actual=None,
            captura_historica=None, dnc_estimada=None, expected_value=21.0,
            observed_value=58.0, confidence_band=(7.0, 38.0),
            indice_madurez="Alto", score_urgencia=0.71, provincia="Valencia",
            impacto_estimado=500.0,
        ),
        dict(
            id_cliente="1000456789", categoria_h="Categoria T1", bloque="Productos Técnicos",
            tipo="PAUSA_SOSPECHOSA", semanas_fuera_banda=3, captura_actual=None,
            captura_historica=None, dnc_estimada=None, expected_value=18.0,
            observed_value=24.0, confidence_band=(6.0, 30.0),
            indice_madurez="Medio", score_urgencia=0.45, provincia="Sevilla",
        ),
        dict(
            id_cliente="1000567890", categoria_h="Categoria C1", bloque="Commodities",
            tipo="DEMANDA_NO_CAPTURADA", semanas_fuera_banda=20, captura_actual=0.18,
            captura_historica=0.18, dnc_estimada=14.0, expected_value=10.0,
            observed_value=8.0, confidence_band=(2.0, 18.0),
            indice_madurez="Alto", score_urgencia=0.66, provincia="Bilbao",
            impacto_estimado=280.0,
        ),
        dict(
            id_cliente="1000678901", categoria_h="Categoria C2", bloque="Commodities",
            tipo="DEMANDA_NO_CAPTURADA", semanas_fuera_banda=16, captura_actual=0.32,
            captura_historica=0.32, dnc_estimada=8.0, expected_value=12.0,
            observed_value=10.0, confidence_band=(4.0, 22.0),
            indice_madurez="Medio", score_urgencia=0.58, provincia="Madrid",
            impacto_estimado=160.0,
        ),
        dict(
            id_cliente="1000789012", categoria_h="Categoria C1", bloque="Commodities",
            tipo="CAMPAIGN_NO_RESPONSE", semanas_fuera_banda=1, captura_actual=12.0,
            captura_historica=46.0, dnc_estimada=34.0, expected_value=46.0,
            observed_value=12.0, confidence_band=(28.0, 64.0),
            indice_madurez="Alto", score_urgencia=0.63, provincia="Madrid",
            impacto_estimado=680.0,
        ),
        dict(
            id_cliente="1000890123", categoria_h="TODAS", bloque="Cross",
            tipo="SEÑAL_CRUZADA_NEGATIVA", semanas_fuera_banda=4, captura_actual=None,
            captura_historica=None, dnc_estimada=None, expected_value=120.0,
            observed_value=58.0, confidence_band=(80.0, 160.0),
            indice_madurez="Alto", score_urgencia=0.79, provincia="Zaragoza",
            impacto_estimado=1200.0,
        ),
        dict(
            id_cliente="1000901234", categoria_h="Categoria C1", bloque="Commodities",
            tipo="FUGA_PARCIAL_COMMODITY", semanas_fuera_banda=5, captura_actual=24.0,
            captura_historica=68.0, dnc_estimada=22.0, expected_value=200.0,
            observed_value=120.0, confidence_band=(160.0, 240.0),
            indice_madurez="Alto", score_urgencia=0.69, provincia="Málaga",
            impacto_estimado=440.0,
        ),
        dict(
            id_cliente="1001012345", categoria_h="Categoria T1", bloque="Productos Técnicos",
            tipo="DETERIORO_SOSTENIDO_TECNICO", semanas_fuera_banda=4, captura_actual=None,
            captura_historica=None, dnc_estimada=None, expected_value=14.0,
            observed_value=42.0, confidence_band=(5.0, 26.0),
            indice_madurez="Medio", score_urgencia=0.55, provincia="Madrid",
        ),
    ]

    for sm in samples:
        raw_prov = sm.get("provincia")
        match = normalize_provincia(raw_prov)
        sm["provincia"] = match.provincia or raw_prov
        out.append(Signal(
            **sm,
            timestamp=now - timedelta(hours=1),
            narrativa=_mock_narrative(sm),
            provincia_raw=raw_prov,
            comunidad_autonoma=match.comunidad_autonoma,
            lat=match.lat,
            lon=match.lon,
            territorial_source=match.source,
        ))
    return out


def _mock_narrative(s: dict) -> str:
    return (
        f"[demo mock] Cliente {s['id_cliente']} en {s['categoria_h']} con señal "
        f"{s['tipo']} ({s['semanas_fuera_banda']} semanas fuera de banda)."
    )
