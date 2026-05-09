import React, { useEffect, useState } from "react";

import {
  fetchSignalDetail,
  postFeedback,
  postVoiceBriefing,
  VoiceDisabledError,
} from "../api/client.js";

import BanditBars from "./BanditBars.jsx";
import ConfidenceChart from "./ConfidenceChart.jsx";

const ACTION_LABELS = {
  visita: "Crear tarea: visita",
  llamada: "Crear tarea: llamada",
  email: "Preparar email",
  muestra: "Solicitar muestra",
  monitorizar: "Pasar a vigilancia",
};

const STATUS_LABEL = {
  active: { label: "Pendiente", cls: "pending" },
  in_progress: { label: "En curso", cls: "progress" },
  watching: { label: "En vigilancia", cls: "watching" },
  high_priority: { label: "Prioridad máxima", cls: "priority" },
  dismissed: { label: "Descartada", cls: "dismissed" },
  resolved: { label: "Resuelta", cls: "resolved" },
};

const DISMISS_REASONS = [
  { value: "", label: "Sin motivo" },
  { value: "error_datos", label: "Error de datos" },
  { value: "campana_conocida", label: "Campaña conocida" },
  { value: "cliente_gestionado", label: "Cliente ya gestionado" },
  { value: "no_aplica", label: "No aplica" },
];

function fmt(v, fallback = "—", digits = 1) {
  if (v === null || v === undefined || Number.isNaN(v)) return fallback;
  if (typeof v !== "number") return v;
  return v.toLocaleString("es-ES", { maximumFractionDigits: digits });
}

function toastFor(outcome, action) {
  if (outcome === "acted") {
    if (action === "monitorizar") return "Cliente pasado a vigilancia";
    const labelMap = {
      visita: "Tarea creada: visita",
      llamada: "Tarea creada: llamada",
      email: "Email preparado",
      muestra: "Solicitud de muestra registrada",
    };
    return labelMap[action] ?? `Acción registrada: ${action}`;
  }
  if (outcome === "false_alarm") return "Alerta descartada como falsa alarma";
  if (outcome === "priority_up") return "Alerta marcada como prioridad máxima";
  if (outcome === "watching") return "Cliente pasado a vigilancia";
  return "Acción registrada";
}

export default function DetailPanel({ signalId, onUpdate }) {
  const [detail, setDetail] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [audioUrl, setAudioUrl] = useState(null);
  const [voiceErr, setVoiceErr] = useState(null);
  const [toast, setToast] = useState(null);
  const [busy, setBusy] = useState(false);
  const [dismissReason, setDismissReason] = useState("");

  useEffect(() => {
    if (!signalId) {
      setDetail(null);
      return undefined;
    }
    setLoading(true);
    setError(null);
    setAudioUrl(null);
    setVoiceErr(null);
    setDismissReason("");
    let cancelled = false;
    fetchSignalDetail(signalId)
      .then((d) => {
        if (!cancelled) setDetail(d);
      })
      .catch((e) => {
        if (!cancelled) setError(e.message || String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [signalId]);

  if (!signalId) {
    return (
      <aside className="detail">
        <div className="empty">
          <div style={{ fontSize: 32 }}>📊</div>
          <div>Selecciona una alerta de la lista para ver el detalle del twin.</div>
        </div>
      </aside>
    );
  }

  if (loading || !detail) {
    return (
      <aside className="detail">
        <div className="loading"><span className="dot-pulse" />Cargando detalle…</div>
      </aside>
    );
  }
  if (error) {
    return (
      <aside className="detail">
        <h2>Error</h2>
        <div className="small">{error}</div>
      </aside>
    );
  }

  const sig = detail.signal;
  const status = detail.status?.status ?? "active";
  const stMeta = STATUS_LABEL[status];
  const recommendedAction = detail.bandit?.recommended_action ?? "visita";
  const acceptLabel = ACTION_LABELS[recommendedAction] ?? "Aceptar recomendación";

  const submit = async (action, outcome, reason = null) => {
    if (busy) return;
    setBusy(true);
    try {
      const res = await postFeedback(signalId, action, outcome, reason);
      if (res?.bandit_recommendation) {
        setDetail((prev) => ({
          ...prev,
          bandit: res.bandit_recommendation,
          status: res.signal_status ?? prev.status,
        }));
      } else if (res?.signal_status) {
        setDetail((prev) => ({ ...prev, status: res.signal_status }));
      }
      setToast(toastFor(outcome, action));
      onUpdate?.();
      setTimeout(() => setToast(null), 2400);
    } catch (e) {
      setToast(`Error: ${e.message || e}`);
      setTimeout(() => setToast(null), 3000);
    } finally {
      setBusy(false);
    }
  };

  const onAccept = () => submit(recommendedAction, "acted");
  const onDismiss = () => submit(recommendedAction, "false_alarm", dismissReason || null);
  const onPriority = () => submit(recommendedAction, "priority_up");

  const onVoice = async () => {
    setVoiceErr(null);
    setAudioUrl(null);
    try {
      const r = await postVoiceBriefing(signalId);
      setAudioUrl(r.audio_url);
    } catch (e) {
      if (e instanceof VoiceDisabledError) {
        setVoiceErr("Briefing de voz no disponible (configurar ELEVENLABS_API_KEY).");
      } else {
        setVoiceErr(e.message || String(e));
      }
    }
  };

  return (
    <aside className="detail">
      <h2>Cliente {sig.id_cliente}</h2>
      <div className="small">
        {sig.categoria_h} · {sig.bloque} · {sig.provincia ?? "—"} · IM {sig.indice_madurez}
      </div>

      {stMeta && (
        <div className="status-row">
          <span className={`status-badge ${stMeta.cls}`}>
            {status === "high_priority" ? "★ " : ""}{stMeta.label}
          </span>
          {detail.status?.action_taken && (
            <span className="small">
              Acción: <strong>{detail.status.action_taken}</strong>
            </span>
          )}
          {detail.status?.dismiss_reason && (
            <span className="small">
              Motivo: {detail.status.dismiss_reason.replace(/_/g, " ")}
            </span>
          )}
        </div>
      )}

      <section className="detail-section">
        <h4>KPIs del twin</h4>
        <div className="kpis">
          <div className="kpi">
            <div className="k">Captura actual</div>
            <div className="v">{sig.captura_actual !== null ? fmt(sig.captura_actual) : "—"}</div>
          </div>
          <div className="kpi">
            <div className="k">Captura histórica</div>
            <div className="v">{sig.captura_historica !== null ? fmt(sig.captura_historica) : "—"}</div>
          </div>
          <div className="kpi">
            <div className="k">DNC estimada</div>
            <div className="v">{sig.dnc_estimada !== null ? `${fmt(sig.dnc_estimada)} u./sem.` : "—"}</div>
          </div>
          <div className="kpi">
            <div className="k">Semanas fuera de banda</div>
            <div className="v neg">{sig.semanas_fuera_banda}</div>
          </div>
          <div className="kpi">
            <div className="k">Score de urgencia</div>
            <div className="v">{fmt(sig.score_urgencia, "—", 2)}</div>
          </div>
          <div className="kpi">
            <div className="k">Banda predictiva</div>
            <div className="v">
              [{fmt(sig.confidence_band?.[0])} – {fmt(sig.confidence_band?.[1])}]
            </div>
          </div>
        </div>
      </section>

      <section className="detail-section">
        <h4>Evolución y banda de confianza</h4>
        <ConfidenceChart history={detail.history} signal={sig} />
      </section>

      <section className="detail-section">
        <h4>Narrativa causal</h4>
        <div className="narrative-box">{sig.narrativa}</div>
      </section>

      <section className="detail-section">
        <h4>Acción recomendada</h4>
        <BanditBars recommendation={detail.bandit} />
        <div className="feedback-row">
          <button
            className="btn primary"
            onClick={onAccept}
            disabled={busy}
            title={`Aceptar la recomendación: ${recommendedAction}`}
          >
            {acceptLabel}
          </button>
          <button
            className="btn"
            onClick={onPriority}
            disabled={busy}
            title="Marcar como prioridad máxima (sube en la lista)"
          >
            ★ Prioridad máxima
          </button>
          <div className="dismiss-group">
            <select
              className="dismiss-reason"
              value={dismissReason}
              onChange={(e) => setDismissReason(e.target.value)}
              disabled={busy}
              title="Motivo opcional para descartar la alerta"
            >
              {DISMISS_REASONS.map((r) => (
                <option key={r.value} value={r.value}>{r.label}</option>
              ))}
            </select>
            <button
              className="btn danger"
              onClick={onDismiss}
              disabled={busy}
            >
              Falsa alarma
            </button>
          </div>
          <button className="btn" onClick={onVoice}>
            Briefing de voz
          </button>
        </div>
        {audioUrl && (
          <div className="audio-block">
            <audio controls autoPlay src={audioUrl} />
          </div>
        )}
        {voiceErr && (
          <div className="small" style={{ marginTop: 8, color: "var(--warn)" }}>
            {voiceErr}
          </div>
        )}
      </section>

      {toast && <div className="toast">{toast}</div>}
    </aside>
  );
}
