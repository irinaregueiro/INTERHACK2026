"""Deterministic Spanish narrative generation.

Templates are filled with concrete numbers from the twin/signal so the text
is fully traceable. No LLM. Probabilistic language only — never claim that
churn or fuga is *confirmed*. Per the spec, the system surfaces indicios
("probabilidad alta", "compatible con", "indicios de").
"""
from __future__ import annotations

from typing import Any

# --- Templates -------------------------------------------------------------

TEMPLATE_FUGA = (
    "Cliente {id_cliente} en {categoria_h}: la captura observada en las últimas "
    "{semanas_fuera_banda} semanas ({observed:.0f} u.) cae por debajo del rango "
    "esperado [{band_lo:.0f}–{band_hi:.0f}] u. (esperado central {expected:.0f} u.). "
    "{sow_clause}{potencial_clause}"
    "Los datos son compatibles con una pérdida parcial de cuota en esta familia. "
    "Confianza del twin: {indice_madurez}. Recomendación orientativa: "
    "validar con el comercial antes de tomar acciones contundentes."
)

TEMPLATE_DNC = (
    "Cliente {id_cliente} en {categoria_h}: con un potencial declarado de "
    "{potencial:.0f} u./año, la captura histórica se mantiene en torno al "
    "{sow:.0%}. Existe demanda no capturada estimada de {dnc:.0f} u./semana. "
    "Hipótesis principal: oportunidad comercial no explotada (no es una pérdida)."
)

TEMPLATE_DETERIORO = (
    "Cliente {id_cliente} en {categoria_h}: el silencio actual ({observed:.0f} días) "
    "supera el percentil 90 del intervalo histórico entre compras "
    "[{band_lo:.0f}–{band_hi:.0f}] días, y los últimos intervalos muestran un "
    "alargamiento sostenido. Patrón compatible con un deterioro técnico "
    "incipiente. Confianza del twin: {indice_madurez}."
)

TEMPLATE_PAUSA = (
    "Cliente {id_cliente} en {categoria_h}: el silencio observado "
    "({observed:.0f} días) se sitúa en la zona de vigilancia [P75–P90] del "
    "intervalo entre compras esperado. No constituye alerta accionable; "
    "solo se recomienda observación."
)

TEMPLATE_CAMPAIGN = (
    "Cliente {id_cliente} en {categoria_h}: respondía históricamente a las "
    "campañas (media {expected:.0f} u. vs. baseline) pero no respondió a la "
    "última (observado {observed:.0f} u.). Indicio probabilístico de "
    "desactivación de respuesta promocional."
)

TEMPLATE_CRUZADA = (
    "Cliente {id_cliente}: caída simultánea en al menos dos categorías "
    "respecto al patrón histórico durante las últimas semanas. Patrón "
    "compatible con un deterioro transversal de la relación comercial."
)

TEMPLATE_OPORTUNITAT = (
    "Cliente {id_cliente}: presenta un consumo consolidado en anestesia/commodity "
    "({observed:.0f} u. recientes) pero nulo en la familia de producto objetivo ({categoria_h}). "
    "Excelente candidato para venta cruzada (Next Best Product)."
)


TEMPLATES: dict[str, str] = {
    "FUGA_PARCIAL_COMMODITY": TEMPLATE_FUGA,
    "DEMANDA_NO_CAPTURADA": TEMPLATE_DNC,
    "DETERIORO_SOSTENIDO_TECNICO": TEMPLATE_DETERIORO,
    "PAUSA_SOSPECHOSA": TEMPLATE_PAUSA,
    "CAMPAIGN_NO_RESPONSE": TEMPLATE_CAMPAIGN,
    "SEÑAL_CRUZADA_NEGATIVA": TEMPLATE_CRUZADA,
    "OPORTUNITAT_CREUADA": TEMPLATE_OPORTUNITAT,
}


# --- Filler ---------------------------------------------------------------


def _fmt_or_dash(val: Any, fmt: str = "{:.0f}") -> str:
    if val is None:
        return "—"
    try:
        return fmt.format(float(val))
    except (TypeError, ValueError):
        return str(val)


def generate_narrative(tipo: str, ctx: dict[str, Any]) -> str:
    """Render the template for `tipo` with `ctx`. Falls back to a generic line."""
    template = TEMPLATES.get(tipo)
    if template is None:
        return f"Señal {tipo} detectada para cliente {ctx.get('id_cliente', '?')}."

    band_lo, band_hi = ctx.get("confidence_band", (0.0, 0.0))

    sow = ctx.get("sow")
    pot = ctx.get("potencial")
    sow_clause = (
        f"La captura histórica anualizada se sitúa en el {sow:.0%}. "
        if isinstance(sow, (int, float)) and sow == sow  # not NaN
        else ""
    )
    potencial_clause = (
        f"Potencial declarado: {pot:.0f} u./año. "
        if isinstance(pot, (int, float)) and pot == pot
        else ""
    )

    fields = {
        "id_cliente": ctx.get("id_cliente", "?"),
        "categoria_h": ctx.get("categoria_h", "?"),
        "semanas_fuera_banda": int(ctx.get("semanas_fuera_banda", 0) or 0),
        "observed": float(ctx.get("observed_value", 0.0) or 0.0),
        "expected": float(ctx.get("expected_value", 0.0) or 0.0),
        "band_lo": float(band_lo or 0.0),
        "band_hi": float(band_hi or 0.0),
        "indice_madurez": ctx.get("indice_madurez", "Bajo"),
        "potencial": float(pot) if isinstance(pot, (int, float)) and pot == pot else 0.0,
        "sow": float(sow) if isinstance(sow, (int, float)) and sow == sow else 0.0,
        "dnc": float(ctx.get("dnc_estimada") or 0.0),
        "sow_clause": sow_clause,
        "potencial_clause": potencial_clause,
    }

    try:
        return template.format(**fields)
    except KeyError as e:
        # Defensive: never throw at narrative time.
        return f"Señal {tipo} para {ctx.get('id_cliente', '?')} (campo faltante: {e})."
