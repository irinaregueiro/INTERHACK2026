import React from "react";

function isoWeek(d) {
  const dt = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
  const dayNum = (dt.getUTCDay() + 6) % 7;
  dt.setUTCDate(dt.getUTCDate() - dayNum + 3);
  const firstThursday = new Date(Date.UTC(dt.getUTCFullYear(), 0, 4));
  return 1 + Math.round((dt - firstThursday) / (7 * 86400 * 1000));
}

export default function TopBar({ dataSource, totalSignals, showMap, onToggleMap }) {
  const week = isoWeek(new Date());
  return (
    <header className="topbar">
      <div className="brand">
        <span className="brand-mark" />
        <span>Customer Twin</span>
        <span style={{ color: "var(--text-dim)", fontWeight: 500, marginLeft: 6 }}>
          · Smart Demand Signals
        </span>
      </div>
      <div className="meta">
        {onToggleMap && (
          <button
            className={`map-toggle-pill${showMap ? " active" : ""}`}
            onClick={onToggleMap}
            title="Mostrar / ocultar mapa territorial"
          >
            {showMap ? "Ocultar mapa" : "Ver mapa territorial"}
          </button>
        )}
        <span><span className="live-dot" /> en vivo</span>
        <span>Semana {week}</span>
        <span>{totalSignals ?? "…"} señales activas</span>
        {dataSource ? (
          <span className={`data-source-pill${dataSource !== "real" ? " mock" : ""}`}>
            {dataSource === "real" ? "datos reales" : "demo / mock"}
          </span>
        ) : null}
      </div>
    </header>
  );
}
