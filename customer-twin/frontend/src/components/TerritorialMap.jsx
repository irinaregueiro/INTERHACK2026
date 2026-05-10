import React, { useEffect, useMemo, useRef, useState } from "react";

import {
  fetchTerritorialDiagnostics,
  fetchTerritorialSummary,
} from "../api/client.js";

// SVG layout: matches the (svg_x, svg_y) values produced by etl/territorial.py.
const VIEW_W = 1000;
const VIEW_H = 700;

// Colour ramp: light blue → deep red as alert density grows.
const RAMP = [
  "#e6efff", // 0
  "#c7daff",
  "#9fbcff",
  "#6f97ff",
  "#3a73f5",
  "#1f3da3",
  "#aa1f6c",
  "#d62f3a", // hottest
];

function rampColor(weight) {
  if (!Number.isFinite(weight)) return RAMP[0];
  const idx = Math.min(RAMP.length - 1, Math.max(0, Math.floor(weight * (RAMP.length - 1))));
  return RAMP[idx];
}

function radiusFor(count, max, mode) {
  if (!count || !max) return 6;
  // Square-root scaling so a 10×bigger province isn't 10× the radius.
  const r = Math.sqrt(count / max);
  const min = mode === "ccaa" ? 18 : 8;
  const top = mode === "ccaa" ? 56 : 34;
  return min + r * (top - min);
}

function formatEur(v) {
  if (!v && v !== 0) return "—";
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)} M€`;
  if (v >= 1_000) return `${(v / 1_000).toFixed(1)} k€`;
  return `${Math.round(v)} €`;
}

function tipoLabel(t) {
  return ({
    FUGA_PARCIAL_COMMODITY: "Fuga parcial",
    DEMANDA_NO_CAPTURADA: "Demanda no capturada",
    DETERIORO_SOSTENIDO_TECNICO: "Deterioro técnico",
    PAUSA_SOSPECHOSA: "Pausa sospechosa",
    CAMPAIGN_NO_RESPONSE: "Sin rpta. campaña",
    "SEÑAL_CRUZADA_NEGATIVA": "Caída transversal",
    OPORTUNITAT_CREUADA: "Oportunidad cross",
  })[t] || t;
}

// Aggregate provincia buckets into CCAA buckets with a single representative
// (lat, lon) anchor used to position bubbles in CCAA mode. The anchor is the
// alert-weighted centroid of provincias inside the CCAA so a CCAA dominated
// by Madrid doesn't drift off to a peripheral province.
function ccaaBubbles(provinciaBuckets) {
  const out = new Map();
  provinciaBuckets.forEach((p) => {
    if (!p.comunidad_autonoma || p.svg_x == null) return;
    const key = p.comunidad_autonoma;
    const cur = out.get(key) || {
      comunidad_autonoma: key,
      n_alerts: 0,
      provincias: new Set(),
      by_tipo: {},
      by_madurez: {},
      impacto_total_eur: 0,
      _wx: 0,
      _wy: 0,
      _w: 0,
    };
    cur.n_alerts += p.n_alerts;
    cur.provincias.add(p.provincia);
    Object.entries(p.by_tipo || {}).forEach(([k, v]) => {
      cur.by_tipo[k] = (cur.by_tipo[k] || 0) + v;
    });
    Object.entries(p.by_madurez || {}).forEach(([k, v]) => {
      cur.by_madurez[k] = (cur.by_madurez[k] || 0) + v;
    });
    cur.impacto_total_eur += p.impacto_total_eur || 0;
    cur._wx += p.svg_x * p.n_alerts;
    cur._wy += p.svg_y * p.n_alerts;
    cur._w += p.n_alerts;
    out.set(key, cur);
  });
  return Array.from(out.values()).map((c) => ({
    ...c,
    provincias: Array.from(c.provincias).sort(),
    svg_x: c._w ? c._wx / c._w : null,
    svg_y: c._w ? c._wy / c._w : null,
  }));
}

export default function TerritorialMap({
  filter,
  onProvinciaSelect,
  onComunidadSelect,
}) {
  const [summary, setSummary] = useState(null);
  const [diag, setDiag] = useState(null);
  const [mode, setMode] = useState("provincias"); // 'provincias' | 'ccaa'
  const [hovered, setHovered] = useState(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const svgRef = useRef(null);

  useEffect(() => {
    let alive = true;
    Promise.all([fetchTerritorialSummary(), fetchTerritorialDiagnostics()]).then(
      ([s, d]) => {
        if (!alive) return;
        setSummary(s);
        setDiag(d);
      },
    );
    return () => {
      alive = false;
    };
  }, []);

  const bubbles = useMemo(() => {
    if (!summary) return [];
    if (mode === "ccaa") {
      return ccaaBubbles(summary.by_provincia || []);
    }
    return (summary.by_provincia || []).filter((p) => p.svg_x != null);
  }, [summary, mode]);

  const maxAlerts = useMemo(
    () => bubbles.reduce((m, b) => Math.max(m, b.n_alerts), 0),
    [bubbles],
  );

  const ranking = useMemo(() => {
    if (!summary) return [];
    const items =
      mode === "ccaa"
        ? bubbles.map((c) => ({
            key: c.comunidad_autonoma,
            label: c.comunidad_autonoma,
            count: c.n_alerts,
            sub: `${c.provincias.length} prov.`,
          }))
        : (summary.by_provincia || []).map((p) => ({
            key: p.provincia,
            label: p.provincia,
            count: p.n_alerts,
            sub: p.comunidad_autonoma,
          }));
    return items.sort((a, b) => b.count - a.count);
  }, [summary, bubbles, mode]);

  if (!summary) {
    return (
      <div className="map-card map-loading">
        <div className="loading">
          <span className="dot-pulse" /> Cargando mapa territorial…
        </div>
      </div>
    );
  }

  const onBubbleEnter = (b, evt) => {
    setHovered(b);
    if (svgRef.current) {
      const rect = svgRef.current.getBoundingClientRect();
      setTooltipPos({ x: evt.clientX - rect.left, y: evt.clientY - rect.top });
    }
  };
  const onBubbleMove = (evt) => {
    if (svgRef.current) {
      const rect = svgRef.current.getBoundingClientRect();
      setTooltipPos({ x: evt.clientX - rect.left, y: evt.clientY - rect.top });
    }
  };
  const onBubbleLeave = () => setHovered(null);

  const handleClickBubble = (b) => {
    if (mode === "ccaa") {
      const sel = filter?.comunidad_autonoma === b.comunidad_autonoma ? null : b.comunidad_autonoma;
      onComunidadSelect?.(sel);
    } else {
      const sel = filter?.provincia === b.provincia ? null : b.provincia;
      onProvinciaSelect?.(sel);
    }
  };

  const totalActionable = summary.total_actionable ?? 0;
  const mapped = summary.mapped_alerts ?? 0;
  const unmapped = summary.unmapped_alerts ?? 0;
  const coverage = totalActionable
    ? Math.round((mapped / totalActionable) * 1000) / 10
    : 100;

  const topRanking = ranking.slice(0, 8);

  return (
    <section className="map-card">
      <header className="map-header">
        <div>
          <h2>Mapa territorial · España</h2>
          <p className="map-sub">
            {mapped.toLocaleString("es-ES")} alertas ubicadas
            {" · "}
            {summary.provincia_count} provincias · {summary.ccaa_count} CCAA
            {unmapped > 0 && (
              <span className="map-unmapped"> · {unmapped} sin ubicación</span>
            )}
          </p>
        </div>
        <div className="map-toggle" role="tablist">
          <button
            role="tab"
            aria-selected={mode === "provincias"}
            className={`toggle-btn${mode === "provincias" ? " active" : ""}`}
            onClick={() => setMode("provincias")}
          >
            Provincias
          </button>
          <button
            role="tab"
            aria-selected={mode === "ccaa"}
            className={`toggle-btn${mode === "ccaa" ? " active" : ""}`}
            onClick={() => setMode("ccaa")}
          >
            Comunidades
          </button>
        </div>
      </header>

      <div className="map-body">
        <div className="map-svg-wrap">
          <svg
            ref={svgRef}
            viewBox={`0 0 ${VIEW_W} ${VIEW_H}`}
            preserveAspectRatio="xMidYMid meet"
            className="map-svg"
            onMouseMove={onBubbleMove}
          >
            <defs>
              <radialGradient id="seaBg" cx="50%" cy="50%" r="80%">
                <stop offset="0%" stopColor="#f5f7fb" />
                <stop offset="100%" stopColor="#dde4ef" />
              </radialGradient>
              <filter id="bubbleShadow" x="-50%" y="-50%" width="200%" height="200%">
                <feDropShadow dx="0" dy="2" stdDeviation="2" floodOpacity="0.2" />
              </filter>
            </defs>
            <rect x={0} y={0} width={VIEW_W} height={VIEW_H} fill="url(#seaBg)" rx={18} ry={18} />

            {/* Iberian peninsula silhouette — coarse polygon traced over the
                province coordinates so the dots read as a Spain map. */}
            <path
              d={SPAIN_OUTLINE}
              fill="#ffffff"
              stroke="#c8d0de"
              strokeWidth={1.2}
              strokeLinejoin="round"
            />
            {/* Balearic + Canarias islands inset */}
            <path d={BALEARES_OUTLINE} fill="#ffffff" stroke="#c8d0de" strokeWidth={1.2} />
            <rect
              x={70}
              y={605}
              width={290}
              height={80}
              fill="#ffffff"
              stroke="#c8d0de"
              strokeWidth={1.2}
              strokeDasharray="4 4"
              rx={10}
            />
            <text
              x={78}
              y={622}
              fontSize={11}
              fill="#8a91a3"
              letterSpacing="0.05em"
            >
              CANARIAS
            </text>

            {/* Bubbles */}
            {bubbles.map((b) => {
              const isSel =
                (mode === "ccaa" && filter?.comunidad_autonoma === b.comunidad_autonoma) ||
                (mode !== "ccaa" && filter?.provincia === b.provincia);
              const r = radiusFor(b.n_alerts, maxAlerts, mode);
              const w = b.n_alerts / Math.max(1, maxAlerts);
              const fill = rampColor(w);
              return (
                <g
                  key={mode === "ccaa" ? b.comunidad_autonoma : b.provincia}
                  onMouseEnter={(e) => onBubbleEnter(b, e)}
                  onMouseLeave={onBubbleLeave}
                  onClick={() => handleClickBubble(b)}
                  className={`bubble${isSel ? " selected" : ""}`}
                >
                  <circle
                    cx={b.svg_x}
                    cy={b.svg_y}
                    r={r + 6}
                    fill={fill}
                    opacity={isSel ? 0.18 : 0.12}
                  />
                  <circle
                    cx={b.svg_x}
                    cy={b.svg_y}
                    r={r}
                    fill={fill}
                    stroke={isSel ? "#1d2330" : "#ffffff"}
                    strokeWidth={isSel ? 2.5 : 1.4}
                    filter="url(#bubbleShadow)"
                  />
                  {(mode === "ccaa" || r > 14) && (
                    <text
                      x={b.svg_x}
                      y={b.svg_y + 4}
                      textAnchor="middle"
                      fontSize={mode === "ccaa" ? 13 : 11}
                      fontWeight={700}
                      fill="#fff"
                      pointerEvents="none"
                    >
                      {b.n_alerts}
                    </text>
                  )}
                </g>
              );
            })}

            {/* Legend */}
            <g transform={`translate(${VIEW_W - 230}, ${VIEW_H - 56})`}>
              <text x={0} y={-6} fontSize={11} fill="#5e6679" letterSpacing="0.06em">
                INTENSIDAD DE ALERTAS
              </text>
              {RAMP.map((c, i) => (
                <rect
                  key={c}
                  x={i * 26}
                  y={0}
                  width={26}
                  height={10}
                  fill={c}
                />
              ))}
              <text x={0} y={26} fontSize={10} fill="#8a91a3">
                pocas
              </text>
              <text x={RAMP.length * 26 - 26} y={26} fontSize={10} fill="#8a91a3" textAnchor="end">
                muchas
              </text>
            </g>
          </svg>

          {hovered && (
            <div
              className="map-tooltip"
              style={{
                left: Math.min(tooltipPos.x + 14, 680),
                top: Math.max(tooltipPos.y - 10, 10),
              }}
            >
              <div className="tt-title">
                {mode === "ccaa" ? hovered.comunidad_autonoma : hovered.provincia}
                {mode !== "ccaa" && hovered.comunidad_autonoma && (
                  <span className="tt-ccaa">{hovered.comunidad_autonoma}</span>
                )}
              </div>
              <div className="tt-row">
                <strong>{hovered.n_alerts}</strong> alertas
                {hovered.impacto_total_eur > 0 && (
                  <span className="tt-impact">
                    · impacto ~{formatEur(hovered.impacto_total_eur)}
                  </span>
                )}
              </div>
              {hovered.by_tipo && (
                <ul className="tt-list">
                  {Object.entries(hovered.by_tipo)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 3)
                    .map(([k, v]) => (
                      <li key={k}>
                        <span className="dot" />
                        {tipoLabel(k)} <span className="num">{v}</span>
                      </li>
                    ))}
                </ul>
              )}
              {mode === "ccaa" && hovered.provincias && (
                <div className="tt-foot">
                  {hovered.provincias.length} provincias incluidas
                </div>
              )}
              <div className="tt-action">Click para filtrar</div>
            </div>
          )}
        </div>

        <aside className="map-side">
          <div className="map-stats">
            <div className="map-stat">
              <span className="k">Alertas ubicadas</span>
              <span className="v">{mapped.toLocaleString("es-ES")}</span>
            </div>
            <div className="map-stat">
              <span className="k">Cobertura</span>
              <span className="v">{coverage}%</span>
            </div>
            <div className="map-stat">
              <span className="k">CCAA cubiertas</span>
              <span className="v">{summary.ccaa_count}</span>
            </div>
            <div className="map-stat">
              <span className="k">Sin ubicación</span>
              <span className={`v${unmapped ? " warn" : ""}`}>{unmapped}</span>
            </div>
          </div>

          <div className="map-rank">
            <div className="rank-head">
              <span>Top {mode === "ccaa" ? "comunidades" : "provincias"}</span>
              <span className="rank-count">{ranking.length}</span>
            </div>
            <ol className="rank-list">
              {topRanking.map((r, idx) => {
                const isSel =
                  (mode === "ccaa" && filter?.comunidad_autonoma === r.key) ||
                  (mode !== "ccaa" && filter?.provincia === r.key);
                const pct = ranking[0]?.count
                  ? (r.count / ranking[0].count) * 100
                  : 0;
                return (
                  <li
                    key={r.key}
                    className={`rank-item${isSel ? " selected" : ""}`}
                    onClick={() =>
                      mode === "ccaa"
                        ? onComunidadSelect?.(isSel ? null : r.key)
                        : onProvinciaSelect?.(isSel ? null : r.key)
                    }
                  >
                    <span className="rank-idx">#{idx + 1}</span>
                    <div className="rank-body">
                      <div className="rank-row">
                        <span className="rank-label">{r.label}</span>
                        <span className="rank-num">{r.count}</span>
                      </div>
                      {r.sub && <span className="rank-sub">{r.sub}</span>}
                      <div className="rank-track">
                        <div className="rank-fill" style={{ width: `${pct}%` }} />
                      </div>
                    </div>
                  </li>
                );
              })}
            </ol>
            {(filter?.provincia || filter?.comunidad_autonoma) && (
              <button
                className="rank-clear"
                onClick={() => {
                  onProvinciaSelect?.(null);
                  onComunidadSelect?.(null);
                }}
              >
                Quitar filtro territorial
              </button>
            )}
          </div>

          {diag && (
            <div className="map-diag">
              <div className="diag-row">
                <span>Ubicación por nombre</span>
                <span>{diag.by_source?.name ?? 0}</span>
              </div>
              {(diag.by_source?.postal ?? 0) > 0 && (
                <div className="diag-row">
                  <span>Por código postal</span>
                  <span>{diag.by_source.postal}</span>
                </div>
              )}
              {(diag.by_source?.city ?? 0) > 0 && (
                <div className="diag-row">
                  <span>Por ciudad</span>
                  <span>{diag.by_source.city}</span>
                </div>
              )}
              {(diag.by_source?.unknown ?? 0) > 0 && (
                <div className="diag-row warn">
                  <span>No identificadas</span>
                  <span>{diag.by_source.unknown}</span>
                </div>
              )}
            </div>
          )}
        </aside>
      </div>
    </section>
  );
}

// Coarse Iberian peninsula outline. Coordinates are tuned to the same
// 1000×700 viewBox used to position the province bubbles, so the dots sit
// inside the silhouette. It is intentionally low-detail — this is decorative
// scaffolding, not a cartographic map.
const SPAIN_OUTLINE =
  "M315 165 Q300 150 320 132 L355 122 L420 118 L470 110 L530 110 L600 130 L650 138 L685 158 L735 180 L800 200 L870 220 L920 232 L935 260 L905 285 L865 295 L850 320 L820 350 L790 385 L778 420 L760 460 L745 500 L730 540 L705 575 L675 610 L630 625 L555 632 L495 632 L455 625 L425 610 L405 580 L375 530 L350 470 L335 410 L325 340 L320 280 L315 220 Z";

const BALEARES_OUTLINE =
  "M905 395 q12 -8 28 -3 q14 5 18 16 q4 11 -8 19 q-12 8 -28 3 q-14 -5 -18 -16 q-4 -11 8 -19 z M955 410 q6 -2 8 4 q2 6 -4 9 q-6 2 -8 -4 q-2 -6 4 -9 z";
