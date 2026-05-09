import React from "react";

export default function ROIBanner({ signals }) {
  if (!signals || signals.length === 0) return null;

  let totalFuga = 0;
  let totalDnc = 0;

  signals.forEach((s) => {
    if (s.status === "dismissed" || s.status === "resolved") return;
    
    // Impacto is DNC (units) * avg price. We added this to the API as `impacto_estimado`.
    const impact = s.impacto_estimado || 0;
    
    if (s.tipo === "FUGA_PARCIAL_COMMODITY" || s.tipo === "DETERIORO_SOSTENIDO_TECNICO") {
      totalFuga += impact;
    } else if (s.tipo === "DEMANDA_NO_CAPTURADA" || s.tipo === "CAMPAIGN_NO_RESPONSE" || s.tipo === "OPORTUNITAT_CREUADA") {
      totalDnc += impact;
    }
  });

  const formatter = new Intl.NumberFormat('es-ES', { style: 'currency', currency: 'EUR', maximumFractionDigits: 0 });

  return (
    <div style={{
      display: "grid", 
      gridTemplateColumns: "1fr 1fr", 
      gap: 12, 
      marginBottom: 16,
      background: "var(--surface)",
      border: "1px solid var(--border)",
      borderRadius: 8,
      padding: 14
    }}>
      <div style={{ display: "flex", flexDirection: "column", gap: 4 }}>
        <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 600 }}>
          Riesgo de fuga (Anualizado)
        </span>
        <span style={{ fontSize: 20, fontWeight: 700, color: "var(--danger)", letterSpacing: "-0.02em" }}>
          {formatter.format(totalFuga * 52)}
        </span>
      </div>
      <div style={{ display: "flex", flexDirection: "column", gap: 4, borderLeft: "1px solid var(--border)", paddingLeft: 12 }}>
        <span style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: "0.06em", color: "var(--text-dim)", fontWeight: 600 }}>
          Oportunidad DNC (Anualizada)
        </span>
        <span style={{ fontSize: 20, fontWeight: 700, color: "var(--info)", letterSpacing: "-0.02em" }}>
          {formatter.format(totalDnc * 52)}
        </span>
      </div>
    </div>
  );
}
