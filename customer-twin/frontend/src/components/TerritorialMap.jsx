import React, { useEffect, useState } from "react";
import { fetchTerritorial } from "../api/client.js";

export default function TerritorialMap({ onProvinciaSelect, selectedProvincia }) {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetchTerritorial({ minCount: 1 }).then(res => {
      setData(res);
      setLoading(false);
    });
  }, []);

  if (loading) return null;
  if (!data || data.length === 0) return null;

  // Aggregate by province across categories
  const aggregated = data.reduce((acc, curr) => {
    acc[curr.provincia] = (acc[curr.provincia] || 0) + curr.n_alertas;
    return acc;
  }, {});

  const maxAlerts = Math.max(...Object.values(aggregated));
  
  const sorted = Object.entries(aggregated)
    .sort((a, b) => b[1] - a[1])
    .slice(0, 5); // top 5

  return (
    <div style={{ marginTop: 24, padding: "0 10px" }}>
      <h3 style={{ margin: "0 0 10px 0", fontSize: 11, textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--text-dim)" }}>
        Mapa Territorial (Top 5)
      </h3>
      <div style={{ display: "grid", gap: 8 }}>
        {sorted.map(([prov, count]) => {
          const pct = Math.round((count / maxAlerts) * 100);
          const isActive = selectedProvincia === prov;
          return (
            <button 
              key={prov} 
              onClick={() => onProvinciaSelect(isActive ? null : prov)}
              style={{
                textAlign: "left",
                background: isActive ? "var(--surface-2)" : "transparent",
                padding: "6px 8px",
                borderRadius: 6,
                border: isActive ? "1px solid var(--border)" : "1px solid transparent",
                width: "100%"
              }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", fontSize: 12, marginBottom: 4 }}>
                <span style={{ fontWeight: isActive ? 600 : 500, color: isActive ? "var(--brand)" : "var(--text)" }}>
                  {prov}
                </span>
                <span style={{ color: "var(--danger)", fontWeight: 600 }}>{count} alertas</span>
              </div>
              <div style={{ height: 4, background: "var(--surface-2)", borderRadius: 2, overflow: "hidden" }}>
                <div style={{ width: `${pct}%`, height: "100%", background: "var(--danger)", borderRadius: 2 }} />
              </div>
            </button>
          );
        })}
      </div>
    </div>
  );
}
