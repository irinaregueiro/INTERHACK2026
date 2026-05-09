import React from "react";
import TerritorialMap from "./TerritorialMap.jsx";

const TIPOS = [
  { key: null, label: "Todas las señales" },
  { key: "FUGA_PARCIAL_COMMODITY", label: "Fuga parcial" },
  { key: "DETERIORO_SOSTENIDO_TECNICO", label: "Deterioro técnico" },
  { key: "DEMANDA_NO_CAPTURADA", label: "Demanda no capturada" },
  { key: "PAUSA_SOSPECHOSA", label: "Pausa sospechosa" },
  { key: "CAMPAIGN_NO_RESPONSE", label: "Sin rpta. campaña" },
  { key: "SEÑAL_CRUZADA_NEGATIVA", label: "Caída transversal" },
  { key: "OPORTUNITAT_CREUADA", label: "Oportunidad cross-selling" },
];

const BLOQUES = [
  { key: "Commodities", label: "Commodities" },
  { key: "Productos Técnicos", label: "Productos técnicos" },
  { key: "Cross", label: "Cross-familia" },
];

const MADUREZ = [
  { key: "Alto", label: "Madurez Alta" },
  { key: "Medio", label: "Madurez Media" },
  { key: "Bajo", label: "Madurez Baja" },
];

const STATUSES = [
  { key: null, label: "Activas (todas)" },
  { key: "active", label: "Pendientes" },
  { key: "high_priority", label: "Prioridad máxima" },
  { key: "in_progress", label: "En curso" },
  { key: "watching", label: "En vigilancia" },
  { key: "dismissed", label: "Descartadas" },
];

export default function Sidebar({ counts, filter, onFilter }) {
  const byTipo = counts?.by_tipo ?? {};
  const byBloque = counts?.by_bloque ?? {};
  const byStatus = counts?.by_status ?? {};
  const byMadurez = counts?.by_madurez ?? {};
  const actionableTotal = counts?.actionable_total ?? counts?.total ?? 0;
  return (
    <nav className="sidebar">
      <h3>Por estado</h3>
      {STATUSES.map((s) => {
        const isActive = filter.status === s.key;
        let count;
        if (s.key === null) count = actionableTotal;
        else count = byStatus[s.key] ?? 0;
        return (
          <button
            key={s.label}
            className={`nav-item${isActive ? " active" : ""}`}
            onClick={() => onFilter({ ...filter, status: s.key })}
          >
            <span>{s.label}</span>
            <span className="nav-count">{count}</span>
          </button>
        );
      })}

      <h3 style={{ marginTop: 18 }}>Por tipo</h3>
      {TIPOS.map((t) => {
        const isActive = filter.tipo === t.key && !filter.bloque;
        const count = t.key ? byTipo[t.key] ?? 0 : counts?.total ?? 0;
        return (
          <button
            key={t.label}
            className={`nav-item${isActive ? " active" : ""}`}
            onClick={() => onFilter({ ...filter, tipo: t.key, bloque: null, madurez: null, provincia: null })}
          >
            <span>{t.label}</span>
            <span className="nav-count">{count}</span>
          </button>
        );
      })}

      <h3 style={{ marginTop: 18 }}>Por bloque</h3>
      {BLOQUES.map((b) => {
        const isActive = filter.bloque === b.key;
        const count = byBloque[b.key] ?? 0;
        return (
          <button
            key={b.key}
            className={`nav-item${isActive ? " active" : ""}`}
            onClick={() => onFilter({ ...filter, tipo: null, bloque: b.key, madurez: null, provincia: null })}
          >
            <span>{b.label}</span>
            <span className="nav-count">{count}</span>
          </button>
        );
      })}

      <h3 style={{ marginTop: 18 }}>Por madurez</h3>
      {MADUREZ.map((m) => {
        const isActive = filter.madurez === m.key;
        const count = byMadurez[m.key] ?? 0;
        return (
          <button
            key={m.key}
            className={`nav-item${isActive ? " active" : ""}`}
            onClick={() => onFilter({ ...filter, tipo: null, bloque: null, madurez: m.key, provincia: null })}
          >
            <span>{m.label}</span>
            <span className="nav-count">{count}</span>
          </button>
        );
      })}
      <TerritorialMap 
        selectedProvincia={filter.provincia} 
        onProvinciaSelect={(p) => onFilter({ ...filter, provincia: p })}
      />
    </nav>
  );
}
