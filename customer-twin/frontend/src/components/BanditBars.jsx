import React from "react";

const ORDER = ["visita", "llamada", "email", "muestra", "monitorizar"];

export default function BanditBars({ recommendation, previousRecommendation }) {
  if (!recommendation) return null;
  const { action_probabilities = {}, recommended_action, confidence = 0 } = recommendation;
  const max = Math.max(0.001, ...Object.values(action_probabilities));
  return (
    <div>
      <div className="bandit-bars">
        {ORDER.map((arm) => {
          const p = action_probabilities[arm] ?? 0;
          const prev_p = previousRecommendation?.action_probabilities?.[arm];
          const pct = (p * 100).toFixed(0);
          const isRec = arm === recommended_action;
          const diff = prev_p !== undefined ? ((p - prev_p) * 100).toFixed(1) : null;
          return (
            <div key={arm} className="bandit-row">
              <div className={`name${isRec ? " recommended" : ""}`}>
                {arm}
                {isRec ? " ★" : ""}
              </div>
              <div className="bar" style={{ position: "relative" }}>
                {prev_p !== undefined && (
                  <div 
                    style={{
                      position: "absolute",
                      left: 0, top: 0, bottom: 0,
                      width: `${(prev_p / max) * 100}%`,
                      background: "rgba(0,0,0,0.1)",
                      borderRight: "2px solid var(--text-dim)"
                    }}
                  />
                )}
                <div
                  className="fill"
                  style={{
                    width: `${(p / max) * 100}%`,
                    background: isRec ? "var(--brand)" : "#a8b0c4",
                    opacity: 0.85
                  }}
                />
              </div>
              <div className="pct" style={{ display: "flex", gap: 4, justifyContent: "flex-end" }}>
                <span>{pct}%</span>
                {diff && (
                  <span style={{ fontSize: 10, color: parseFloat(diff) >= 0 ? "var(--success)" : "var(--danger)", width: 24, textAlign: "right" }}>
                    {parseFloat(diff) >= 0 ? "+" : ""}{diff}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>
      <div className="small" style={{ marginTop: 8 }}>
        Confianza de la recomendación:{" "}
        <strong>{(confidence * 100).toFixed(0)}%</strong>
        {" "}— aumenta a medida que se acumulan interacciones del comercial.
      </div>
    </div>
  );
}
