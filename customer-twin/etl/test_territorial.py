"""Unit tests for the territorial normalization layer.

Run with::

    python -m pytest etl/test_territorial.py -q

The dataset shipped with this project ("Sta.Cruz Tenerife", "Vizcaya",
"Gipúzkoa", "Orense" …) is the source of the variant list — every spelling
that appears there must round-trip to a canonical provincia and a CCAA.
"""
from __future__ import annotations

import pytest

from .territorial import (
    CCAA_OFICIALES,
    PROVINCIAS,
    POSTAL_TO_PROVINCIA,
    ccaa_for_provincia,
    normalize_provincia,
)


# ---------------------------------------------------------------------------
# Static contracts
# ---------------------------------------------------------------------------


def test_52_provinces_registered():
    assert len(PROVINCIAS) == 52


def test_19_ccaa_registered():
    # 17 CCAA + 2 ciudades autónomas (Ceuta, Melilla)
    assert len(set(CCAA_OFICIALES)) == 19


def test_every_provincia_has_a_known_ccaa():
    for p in PROVINCIAS.values():
        assert p.ccaa in CCAA_OFICIALES, p


def test_every_postal_prefix_resolves():
    for prefix, provincia in POSTAL_TO_PROVINCIA.items():
        assert provincia in PROVINCIAS, prefix


# ---------------------------------------------------------------------------
# Real-world variants present in Datasets.xlsx
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,canonical",
    [
        ("Sta.Cruz Tenerife", "Santa Cruz de Tenerife"),
        ("sta cruz tenerife", "Santa Cruz de Tenerife"),
        ("Tenerife", "Santa Cruz de Tenerife"),
        ("Vizcaya", "Bizkaia"),
        ("Gipúzkoa", "Gipuzkoa"),
        ("Guipúzcoa", "Gipuzkoa"),
        ("Álava", "Álava"),
        ("Araba", "Álava"),
        ("Orense", "Ourense"),
        ("La Coruña", "A Coruña"),
        ("A Coruña", "A Coruña"),
        ("Lerida", "Lleida"),
        ("Gerona", "Girona"),
        ("Baleares", "Illes Balears"),
        ("Castellón", "Castellón"),
        ("Castelló", "Castellón"),
        ("Cádiz", "Cádiz"),
        ("MADRID", "Madrid"),
        ("  málaga ", "Málaga"),
    ],
)
def test_name_variants_normalize(raw, canonical):
    m = normalize_provincia(raw)
    assert m.provincia == canonical, raw
    assert m.comunidad_autonoma == ccaa_for_provincia(canonical)
    assert m.source == "name"


def test_postal_code_fallback():
    m = normalize_provincia(None, postal_code="08025")
    assert m.provincia == "Barcelona"
    assert m.source == "postal"


def test_postal_code_two_digit():
    m = normalize_provincia(None, postal_code="35")
    assert m.provincia == "Las Palmas"
    assert m.source == "postal"


def test_city_fallback():
    m = normalize_provincia(None, ciudad="Bilbao")
    assert m.provincia == "Bizkaia"
    assert m.source == "city"


def test_city_fallback_donostia():
    m = normalize_provincia(None, ciudad="Donostia")
    assert m.provincia == "Gipuzkoa"


def test_unknown_returns_no_match_but_does_not_raise():
    m = normalize_provincia("Lorem Ipsum")
    assert m.provincia is None
    assert m.comunidad_autonoma is None
    assert m.source == "unknown"


def test_andorra_is_flagged_non_spain():
    m = normalize_provincia("Andorra")
    assert m.provincia is None
    assert m.source == "non_spain"


def test_empty_inputs():
    m = normalize_provincia("", postal_code=None, ciudad=None)
    assert m.source == "unknown"


def test_resolution_priority_name_wins_over_postal():
    # Name match should win even if a misleading postal code is supplied.
    m = normalize_provincia("Madrid", postal_code="08025")
    assert m.provincia == "Madrid"
    assert m.source == "name"
