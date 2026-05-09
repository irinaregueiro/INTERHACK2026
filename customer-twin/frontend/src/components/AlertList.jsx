import React from "react";

const TIPO_LABEL = {
  FUGA_PARCIAL_COMMODITY: { label: "Fuga parcial", cls: "fuga" },
  DETERIORO_SOSTENIDO_TECNICO: { label: "Deterioro técnico", cls: "deterioro" },
  DEMANDA_NO_CAPTURADA: { label: "Demanda no capturada", cls: "dnc" },
  PAUSA_SOSPECHOSA: { label: "Pausa sospechosa", cls: "pausa" },
  CAMPAIGN_NO_RESPONSE: { label: "Sin respuesta a campaña", cls: "campaign" },
  "SEÑAL_CRUZADA_NEGATIVA": { label: "Señal cruzada", cls: "cross" },
};

const STATUS_LABEL = {
  active: { label: "Pendiente", cls: "pending" },
  in_progress: { label: "En curso", cls: "progress" },
  watching: { label: "En vigilancia", cls: "watching" },
  high_priority: { label: "Prioridad máxima", cls: "priority" },
  dismissed: { label: "Descartada", cls: "dismissed" },
  resolved: { label: "Resuelta", cls: "resolved" },
};

const TITLE_BY_STATUS = {
  null: "Alertas activas",
  active: "Alertas pendientes",
  high_priority: "Prioridad máxima",
  in_progress: "Alertas en curso",
  watching: "En vigilancia",
  dismissed: "Alertas descartadas",
  resolved: "Alertas resueltas",
};

function urgencyClass(score) {
  if (score >= 0.7) return "high";
  if (score >= 0.45) return "med";
  return "low";
}

function exportToCsv(signals) {
  if (!signals || !signals.length) return;
  const headers = ["Cliente", "Categoría", "Tipo", "Bloque", "Score Urgencia", "Madurez", "Provincia", "Semanas Fuera Banda", "Status", "Acción"];
  const rows = signals.map(s => [
    s.id_cliente,
    s.categoria_h,
    s.tipo,
    s.bloque,
    s.score_urgencia.toFixed(4),
    s.indice_madurez,
    s.provincia ?? "",
    s.semanas_fuera_banda,
    s.status ?? "active",
    s.action_taken ?? ""
  ].map(v => `"${String(v).replace(/"/g, '""')}"`).join(","));
  
  const csvContent = "data:text/csv;charset=utf-8," + [headers.join(","), ...rows].join("\n");
  const encodedUri = encodeURI(csvContent);
  const link = document.createElement("a");
  link.setAttribute("href", encodedUri);
  link.setAttribute("download", `customer_twin_alerts_${new Date().toISOString().split('T')[0]}.csv`);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

export default function AlertList({ signals, selected, onSelect, loading, error, statusFilter }) {
  if (loading) {
    return (
      <main className="alerts">
        <div className="loading"><span className="dot-pulse" />Cargando señales…</div>
      </main>
    );
  }
  if (error) {
    return (
      <main className="alerts">
        <h2>Error</h2>
        <p className="subtitle">{String(error)}</p>
      </main>
    );
  }
  const title = TITLE_BY_STATUS[statusFilter ?? "null"] ?? "Alertas";
  const subtitle = statusFilter
    ? `${signals.length} alertas en estado «${STATUS_LABEL[statusFilter]?.label ?? statusFilter}».`
    : `${signals.length} alertas accionables priorizadas (prioridad máxima primero, luego por urgencia).`;
  return (
    <main className="alerts">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h2>{title}</h2>
        <button 
          onClick={() => exportToCsv(signals)}
          className="csv-btn"
          style={{ padding: "6px 12px", background: "var(--brand-accent)", color: "white", border: "none", borderRadius: "4px", cursor: "pointer", fontWeight: 500 }}
        >
          Exportar a CSV
        </button>
      </div>
      <p className="subtitle">{subtitle}</p>
      {signals.map((s) => {
        const meta = TIPO_LABEL[s.tipo] || { label: s.tipo, cls: "" };
        const status = s.status ?? "active";
        const stMeta = STATUS_LABEL[status];
        const cardCls = [
          "alert-card",
          selected === s.signal_id ? "selected" : "",
          status === "high_priority" ? "is-priority" : "",
          status === "in_progress" ? "is-progress" : "",
          status === "watching" ? "is-watching" : "",
          status === "dismissed" ? "is-dismissed" : "",
        ].filter(Boolean).join(" ");
        return (
          <button
            key={s.signal_id}
            className={cardCls}
            onClick={() => onSelect(s.signal_id)}
          >
            <div>
              <div className="meta">
                <span className={`tipo-badge ${meta.cls}`}>{meta.label}</span>
                {stMeta && status !== "active" && (
                  <span className={`status-badge ${stMeta.cls}`}>
                    {status === "high_priority" ? "★ " : ""}{stMeta.label}
                  </span>
                )}
                <span>· {s.categoria_h}</span>
                <span>· {s.semanas_fuera_banda} sem. fuera de banda</span>
                <span>· {s.provincia ?? "—"}</span>
                <span className="maturity-chip">IM {s.indice_madurez}</span>
              </div>
              <div className="title">Cliente {s.id_cliente}</div>
              <div className="narrative">{s.narrativa}</div>
              {s.action_taken && (
                <div className="action-taken">
                  Acción registrada: <strong>{s.action_taken}</strong>
                </div>
              )}
            </div>
            <span className={`urgency-pill ${urgencyClass(s.score_urgencia)}`}>
              U {s.score_urgencia.toFixed(2)}
            </span>
          </button>
        );
      })}
      {signals.length === 0 && (
        <div className="loading" style={{ marginTop: 20 }}>
          No hay alertas que coincidan con el filtro actual.
        </div>
      )}
    </main>
  );
}
