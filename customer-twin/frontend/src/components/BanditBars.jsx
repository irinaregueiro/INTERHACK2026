import React from "react";

const ORDER = ["visita", "llamada", "email", "muestra", "monitorizar"];

export default function BanditBars({ recommendation }) {
  if (!recommendation) return null;
  const { action_probabilities = {}, recommended_action, confidence = 0 } = recommendation;
  const max = Math.max(0.001, ...Object.values(action_probabilities));
  return (
    <div>
      <div className="bandit-bars">
        {ORDER.map((arm) => {
          const p = action_probabilities[arm] ?? 0;
          const pct = (p * 100).toFixed(0);
          const isRec = arm === recommended_action;
          return (
            <div key={arm} className="bandit-row">
              <div className={`name${isRec ? " recommended" : ""}`}>
                {arm}
                {isRec ? " ★" : ""}
              </div>
              <div className="bar">
                <div
                  className="fill"
                  style={{
                    width: `${(p / max) * 100}%`,
                    background: isRec ? "var(--brand)" : "#a8b0c4",
                  }}
                />
              </div>
              <div className="pct">{pct}%</div>
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
