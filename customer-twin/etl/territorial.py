"""Territorial normalization for Spanish provinces and comunidades autónomas.

This module is the single source of truth for everything territorial:
    * canonical province names (50 provincias + Ceuta + Melilla)
    * comunidad-autónoma mapping
    * accent / casing / spelling aliases
    * 2-digit postal-code → provincia fallback
    * approximate (lat, lon) for proportional-symbol maps
    * approximate SVG coordinates (0..1000 × 0..700) for the dashboard map

The dataset received in this project mixes several spellings ("Vizcaya" vs
"Bizkaia", "Sta.Cruz Tenerife" vs "Santa Cruz de Tenerife", "Orense" vs
"Ourense", "A Coruña" vs "La Coruña", "Gipúzkoa" vs "Guipúzcoa", …) and a few
non-Spanish entries (e.g. "Andorra"). `normalize_provincia` collapses every
variant to a stable canonical name so the rest of the pipeline can rely on it.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass
from typing import Optional

# ---------------------------------------------------------------------------
# Canonical reference data
# ---------------------------------------------------------------------------

# Comunidades autónomas (17) plus the two ciudades autónomas (Ceuta, Melilla).
ANDALUCIA = "Andalucía"
ARAGON = "Aragón"
ASTURIAS = "Principado de Asturias"
BALEARES = "Illes Balears"
CANARIAS = "Canarias"
CANTABRIA = "Cantabria"
CASTILLA_LEON = "Castilla y León"
CASTILLA_MANCHA = "Castilla-La Mancha"
CATALUNYA = "Cataluña"
VALENCIA_CCAA = "Comunitat Valenciana"
EXTREMADURA = "Extremadura"
GALICIA = "Galicia"
MADRID_CCAA = "Comunidad de Madrid"
MURCIA_CCAA = "Región de Murcia"
NAVARRA_CCAA = "Comunidad Foral de Navarra"
PAIS_VASCO = "País Vasco"
RIOJA_CCAA = "La Rioja"
CEUTA = "Ceuta"
MELILLA = "Melilla"

CCAA_OFICIALES: tuple[str, ...] = (
    ANDALUCIA, ARAGON, ASTURIAS, BALEARES, CANARIAS, CANTABRIA,
    CASTILLA_LEON, CASTILLA_MANCHA, CATALUNYA, VALENCIA_CCAA, EXTREMADURA,
    GALICIA, MADRID_CCAA, MURCIA_CCAA, NAVARRA_CCAA, PAIS_VASCO, RIOJA_CCAA,
    CEUTA, MELILLA,
)


@dataclass(frozen=True)
class Provincia:
    nombre: str           # canonical display name
    ccaa: str             # canonical CCAA name
    lat: float            # capital latitude (approx)
    lon: float            # capital longitude (approx)
    svg_x: float          # SVG x in 0..1000 (peninsula+canarias inset)
    svg_y: float          # SVG y in 0..700


# Geographic centres are approximate (province capital). SVG coordinates are
# tuned for a 1000×700 viewBox where Canary Islands sit in a bottom-left inset
# so the layout reads as a Spain map at a glance.
PROVINCIAS: dict[str, Provincia] = {
    # Andalucía
    "Almería":       Provincia("Almería", ANDALUCIA, 36.84, -2.46, 705, 595),
    "Cádiz":         Provincia("Cádiz", ANDALUCIA, 36.53, -6.30, 470, 615),
    "Córdoba":       Provincia("Córdoba", ANDALUCIA, 37.89, -4.78, 545, 555),
    "Granada":       Provincia("Granada", ANDALUCIA, 37.18, -3.60, 615, 590),
    "Huelva":        Provincia("Huelva", ANDALUCIA, 37.26, -6.95, 440, 580),
    "Jaén":          Provincia("Jaén", ANDALUCIA, 37.77, -3.78, 605, 545),
    "Málaga":        Provincia("Málaga", ANDALUCIA, 36.72, -4.42, 555, 615),
    "Sevilla":       Provincia("Sevilla", ANDALUCIA, 37.39, -5.99, 480, 575),
    # Aragón
    "Huesca":        Provincia("Huesca", ARAGON, 42.14, -0.41, 760, 215),
    "Teruel":        Provincia("Teruel", ARAGON, 40.34, -1.10, 730, 360),
    "Zaragoza":      Provincia("Zaragoza", ARAGON, 41.65, -0.88, 720, 285),
    # Asturias
    "Asturias":      Provincia("Asturias", ASTURIAS, 43.36, -5.85, 470, 130),
    # Baleares
    "Illes Balears": Provincia("Illes Balears", BALEARES, 39.57, 2.65, 945, 405),
    # Canarias (inset positions)
    "Las Palmas":    Provincia("Las Palmas", CANARIAS, 28.10, -15.41, 235, 645),
    "Santa Cruz de Tenerife": Provincia("Santa Cruz de Tenerife", CANARIAS, 28.46, -16.25, 130, 645),
    # Cantabria
    "Cantabria":     Provincia("Cantabria", CANTABRIA, 43.46, -3.81, 555, 130),
    # Castilla y León
    "Ávila":         Provincia("Ávila", CASTILLA_LEON, 40.66, -4.70, 510, 360),
    "Burgos":        Provincia("Burgos", CASTILLA_LEON, 42.34, -3.70, 575, 215),
    "León":          Provincia("León", CASTILLA_LEON, 42.60, -5.57, 460, 200),
    "Palencia":      Provincia("Palencia", CASTILLA_LEON, 42.01, -4.53, 525, 235),
    "Salamanca":     Provincia("Salamanca", CASTILLA_LEON, 40.97, -5.66, 440, 330),
    "Segovia":       Provincia("Segovia", CASTILLA_LEON, 40.95, -4.12, 545, 320),
    "Soria":         Provincia("Soria", CASTILLA_LEON, 41.76, -2.46, 625, 290),
    "Valladolid":    Provincia("Valladolid", CASTILLA_LEON, 41.65, -4.72, 510, 290),
    "Zamora":        Provincia("Zamora", CASTILLA_LEON, 41.50, -5.74, 445, 285),
    # Castilla-La Mancha
    "Albacete":      Provincia("Albacete", CASTILLA_MANCHA, 38.99, -1.86, 670, 445),
    "Ciudad Real":   Provincia("Ciudad Real", CASTILLA_MANCHA, 38.98, -3.93, 565, 460),
    "Cuenca":        Provincia("Cuenca", CASTILLA_MANCHA, 40.07, -2.13, 645, 385),
    "Guadalajara":   Provincia("Guadalajara", CASTILLA_MANCHA, 40.63, -3.16, 620, 340),
    "Toledo":        Provincia("Toledo", CASTILLA_MANCHA, 39.86, -4.02, 550, 405),
    # Cataluña
    "Barcelona":     Provincia("Barcelona", CATALUNYA, 41.39, 2.16, 880, 280),
    "Girona":        Provincia("Girona", CATALUNYA, 41.98, 2.82, 920, 235),
    "Lleida":        Provincia("Lleida", CATALUNYA, 41.61, 0.62, 815, 260),
    "Tarragona":     Provincia("Tarragona", CATALUNYA, 41.12, 1.25, 845, 320),
    # Comunitat Valenciana
    "Alicante":      Provincia("Alicante", VALENCIA_CCAA, 38.35, -0.48, 745, 480),
    "Castellón":     Provincia("Castellón", VALENCIA_CCAA, 39.98, -0.04, 780, 370),
    "Valencia":      Provincia("Valencia", VALENCIA_CCAA, 39.47, -0.38, 760, 415),
    # Extremadura
    "Badajoz":       Provincia("Badajoz", EXTREMADURA, 38.88, -6.97, 405, 460),
    "Cáceres":       Provincia("Cáceres", EXTREMADURA, 39.47, -6.37, 430, 405),
    # Galicia
    "A Coruña":      Provincia("A Coruña", GALICIA, 43.36, -8.41, 350, 145),
    "Lugo":          Provincia("Lugo", GALICIA, 43.01, -7.56, 395, 165),
    "Ourense":       Provincia("Ourense", GALICIA, 42.34, -7.86, 380, 220),
    "Pontevedra":    Provincia("Pontevedra", GALICIA, 42.43, -8.65, 340, 200),
    # Madrid
    "Madrid":        Provincia("Madrid", MADRID_CCAA, 40.42, -3.70, 580, 360),
    # Murcia
    "Murcia":        Provincia("Murcia", MURCIA_CCAA, 37.99, -1.13, 705, 510),
    # Navarra
    "Navarra":       Provincia("Navarra", NAVARRA_CCAA, 42.82, -1.65, 685, 195),
    # País Vasco
    "Álava":         Provincia("Álava", PAIS_VASCO, 42.85, -2.67, 635, 195),
    "Bizkaia":       Provincia("Bizkaia", PAIS_VASCO, 43.26, -2.93, 615, 155),
    "Gipuzkoa":      Provincia("Gipuzkoa", PAIS_VASCO, 43.32, -1.98, 665, 155),
    # La Rioja
    "La Rioja":      Provincia("La Rioja", RIOJA_CCAA, 42.46, -2.45, 640, 235),
    # Ceuta y Melilla
    "Ceuta":         Provincia("Ceuta", CEUTA, 35.89, -5.32, 510, 660),
    "Melilla":       Provincia("Melilla", MELILLA, 35.29, -2.94, 620, 660),
}


def _strip(s: str) -> str:
    """Lowercase, collapse whitespace, remove accents and punctuation."""
    if s is None:
        return ""
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    out = []
    for ch in s:
        if ch.isalnum() or ch == " ":
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _build_alias_table() -> dict[str, str]:
    """Map every accepted variant (already _strip-ped) to a canonical key."""
    aliases: dict[str, list[str]] = {
        "A Coruña": [
            "a coruna", "la coruna", "coruna", "coruña", "a coruña",
            "la coruña", "corunna",
        ],
        "Álava": ["alava", "araba", "araba alava", "alava araba"],
        "Albacete": ["albacete"],
        "Alicante": ["alicante", "alacant"],
        "Almería": ["almeria"],
        "Asturias": ["asturias", "principado de asturias", "oviedo"],
        "Ávila": ["avila"],
        "Badajoz": ["badajoz"],
        "Illes Balears": [
            "baleares", "illes balears", "islas baleares", "balears",
            "palma", "mallorca", "ibiza", "menorca",
        ],
        "Barcelona": ["barcelona", "bcn"],
        "Bizkaia": ["vizcaya", "bizkaia", "bilbao", "biscaya"],
        "Burgos": ["burgos"],
        "Cáceres": ["caceres"],
        "Cádiz": ["cadiz"],
        "Cantabria": ["cantabria", "santander"],
        "Castellón": [
            "castellon", "castello", "castello de la plana",
            "castellon de la plana",
        ],
        "Ceuta": ["ceuta"],
        "Ciudad Real": ["ciudad real"],
        "Córdoba": ["cordoba"],
        "Cuenca": ["cuenca"],
        "Gipuzkoa": [
            "guipuzcoa", "gipuzkoa", "gipuskoa", "gipuzcoa",
            "san sebastian", "donostia", "donostia san sebastian",
        ],
        "Girona": ["girona", "gerona"],
        "Granada": ["granada"],
        "Guadalajara": ["guadalajara"],
        "Huelva": ["huelva"],
        "Huesca": ["huesca"],
        "Jaén": ["jaen"],
        "La Rioja": ["la rioja", "rioja", "logrono"],
        "Las Palmas": [
            "las palmas", "las palmas de gran canaria", "gran canaria",
            "lanzarote", "fuerteventura", "palmas",
        ],
        "León": ["leon"],
        "Lleida": ["lleida", "lerida"],
        "Lugo": ["lugo"],
        "Madrid": ["madrid", "comunidad de madrid"],
        "Málaga": ["malaga"],
        "Melilla": ["melilla"],
        "Murcia": ["murcia", "region de murcia"],
        "Navarra": [
            "navarra", "nafarroa", "comunidad foral de navarra", "pamplona",
            "iruna", "iruña",
        ],
        "Ourense": ["ourense", "orense"],
        "Palencia": ["palencia"],
        "Pontevedra": ["pontevedra", "vigo"],
        "Salamanca": ["salamanca"],
        "Santa Cruz de Tenerife": [
            "santa cruz de tenerife", "tenerife", "sta cruz tenerife",
            "sta cruz de tenerife", "santa cruz tenerife",
            "s c de tenerife", "sc tenerife", "la palma", "el hierro", "la gomera",
        ],
        "Segovia": ["segovia"],
        "Sevilla": ["sevilla", "seville"],
        "Soria": ["soria"],
        "Tarragona": ["tarragona"],
        "Teruel": ["teruel"],
        "Toledo": ["toledo"],
        "Valencia": ["valencia", "valencia ciudad", "valencia capital"],
        "Valladolid": ["valladolid"],
        "Zamora": ["zamora"],
        "Zaragoza": ["zaragoza", "saragossa"],
    }
    table: dict[str, str] = {}
    for canonical, variants in aliases.items():
        # Always include the canonical, accent-stripped form too.
        for variant in (*variants, canonical):
            key = _strip(variant)
            if key:
                table[key] = canonical
    return table


_ALIAS_TABLE: dict[str, str] = _build_alias_table()

# 2-digit postal-code prefix → provincia (Spain's official assignment).
POSTAL_TO_PROVINCIA: dict[str, str] = {
    "01": "Álava", "02": "Albacete", "03": "Alicante", "04": "Almería",
    "05": "Ávila", "06": "Badajoz", "07": "Illes Balears", "08": "Barcelona",
    "09": "Burgos", "10": "Cáceres", "11": "Cádiz", "12": "Castellón",
    "13": "Ciudad Real", "14": "Córdoba", "15": "A Coruña", "16": "Cuenca",
    "17": "Girona", "18": "Granada", "19": "Guadalajara", "20": "Gipuzkoa",
    "21": "Huelva", "22": "Huesca", "23": "Jaén", "24": "León", "25": "Lleida",
    "26": "La Rioja", "27": "Lugo", "28": "Madrid", "29": "Málaga",
    "30": "Murcia", "31": "Navarra", "32": "Ourense", "33": "Asturias",
    "34": "Palencia", "35": "Las Palmas", "36": "Pontevedra", "37": "Salamanca",
    "38": "Santa Cruz de Tenerife", "39": "Cantabria", "40": "Segovia",
    "41": "Sevilla", "42": "Soria", "43": "Tarragona", "44": "Teruel",
    "45": "Toledo", "46": "Valencia", "47": "Valladolid", "48": "Bizkaia",
    "49": "Zamora", "50": "Zaragoza", "51": "Ceuta", "52": "Melilla",
}

# Provincias not in Spain (never raise, just signal "unmapped" cleanly).
NON_SPANISH = {"andorra", "portugal", "francia", "marruecos"}


@dataclass(frozen=True)
class TerritorialMatch:
    provincia: Optional[str]
    comunidad_autonoma: Optional[str]
    lat: Optional[float]
    lon: Optional[float]
    svg_x: Optional[float]
    svg_y: Optional[float]
    source: str  # 'name' | 'postal' | 'city' | 'unknown' | 'non_spain'


_UNKNOWN = TerritorialMatch(None, None, None, None, None, None, "unknown")


def _match_from_canonical(name: str, source: str) -> TerritorialMatch:
    p = PROVINCIAS[name]
    return TerritorialMatch(
        provincia=p.nombre,
        comunidad_autonoma=p.ccaa,
        lat=p.lat,
        lon=p.lon,
        svg_x=p.svg_x,
        svg_y=p.svg_y,
        source=source,
    )


def normalize_provincia(
    raw: Optional[str] = None,
    *,
    postal_code: Optional[str] = None,
    ciudad: Optional[str] = None,
) -> TerritorialMatch:
    """Resolve a (possibly messy) territorial input to a canonical provincia.

    Resolution order:
      1. ``raw`` matched against alias table (handles tildes, casing, variants).
      2. ``postal_code``: first two digits map deterministically to a provincia.
      3. ``ciudad`` matched against the alias table (cities resolve to their
         provincia — e.g. "Bilbao" → "Bizkaia").
      4. Otherwise return an unmapped match (callers can render as "Sin
         ubicación" without dropping the alert).

    Non-Spanish entries (Andorra, etc.) are returned with ``source="non_spain"``
    and ``provincia=None`` so the dashboard can group them out without crashing.
    """
    # 1. Direct name lookup.
    if raw:
        key = _strip(raw)
        if key in NON_SPANISH:
            return TerritorialMatch(None, None, None, None, None, None, "non_spain")
        if key in _ALIAS_TABLE:
            return _match_from_canonical(_ALIAS_TABLE[key], "name")

    # 2. Postal code (CP).
    if postal_code:
        digits = "".join(c for c in str(postal_code) if c.isdigit())
        # Accept short forms ("8" → "08") *only* when the value clearly looks
        # like a CP (≤5 digits). Anything else is treated as the first two
        # digits of a full 5-digit code.
        if 0 < len(digits) <= 5:
            prefix = digits.zfill(2)[:2] if len(digits) <= 2 else digits[:2]
            canonical = POSTAL_TO_PROVINCIA.get(prefix)
            if canonical:
                return _match_from_canonical(canonical, "postal")

    # 3. City name (uses the same alias table — many cities are listed there).
    if ciudad:
        key = _strip(ciudad)
        if key in _ALIAS_TABLE:
            return _match_from_canonical(_ALIAS_TABLE[key], "city")

    return _UNKNOWN


def list_canonical_provincias() -> list[Provincia]:
    """Return the 52 canonical provincias (sorted alphabetically by name)."""
    return sorted(PROVINCIAS.values(), key=lambda p: p.nombre)


def ccaa_for_provincia(provincia: str) -> Optional[str]:
    """Return the CCAA for a canonical provincia name, or None."""
    p = PROVINCIAS.get(provincia)
    return p.ccaa if p else None
