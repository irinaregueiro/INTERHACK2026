// Lightweight fetch client for the Customer Twin API.
// Falls back to bundled mock signals if the backend is unreachable so the
// dashboard remains demonstrable in offline mode.

import mockSignals from "./mockSignals.json";

const BASE = ""; // Vite proxy rewrites /api → backend in dev.

async function get(path) {
  const res = await fetch(`${BASE}${path}`);
  if (!res.ok) throw new Error(`GET ${path} → ${res.status}`);
  return { data: await res.json(), source: res.headers.get("X-Data-Source") || "real" };
}

async function post(path, body) {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) throw new Error(`POST ${path} → ${res.status}`);
  if (res.status === 204) return { data: null };
  return { data: await res.json() };
}

export async function fetchSignals({ tipo, bloque, status, limit = 50 } = {}) {
  const params = new URLSearchParams();
  if (tipo) params.set("tipo", tipo);
  if (bloque) params.set("bloque", bloque);
  if (status) params.set("status", status);
  params.set("limit", String(limit));
  try {
    return await get(`/api/signals?${params.toString()}`);
  } catch (e) {
    console.warn("API unreachable, using bundled mock signals:", e.message);
    return { data: mockSignals, source: "mock-bundled" };
  }
}

export async function fetchCounts() {
  try {
    return (await get("/api/signals/counts")).data;
  } catch {
    return computeCountsFromMock();
  }
}

export async function fetchSignalDetail(signalId) {
  const enc = encodeURIComponent(signalId);
  try {
    return (await get(`/api/signals/${enc}/detail`)).data;
  } catch (e) {
    console.warn("Detail fetch failed; building synthetic detail:", e.message);
    const sig = mockSignals.find((s) => s.signal_id === signalId) || mockSignals[0];
    return buildSyntheticDetail(sig);
  }
}

export async function postFeedback(signalId, action, outcome, reason = null) {
  const enc = encodeURIComponent(signalId);
  const body = { action, outcome };
  if (reason) body.reason = reason;
  return (await post(`/api/signals/${enc}/feedback`, body)).data;
}

export async function postVoiceBriefing(signalId) {
  const enc = encodeURIComponent(signalId);
  const res = await fetch(`/api/signals/${enc}/voice_briefing`, { method: "POST" });
  if (!res.ok) {
    if (res.status === 503) {
      const body = await res.json().catch(() => ({}));
      throw new VoiceDisabledError(body?.detail?.message || "Voice disabled");
    }
    throw new Error(`voice_briefing → ${res.status}`);
  }
  return res.json();
}

export async function fetchTerritorial({ minCount = 2 } = {}) {
  try {
    return (await get(`/api/territorial_alerts?min_count=${minCount}`)).data;
  } catch {
    return [];
  }
}

export class VoiceDisabledError extends Error {
  constructor(msg) {
    super(msg);
    this.name = "VoiceDisabledError";
  }
}

// --- Helpers ---------------------------------------------------------------

function computeCountsFromMock() {
  const counts = { total: mockSignals.length, by_tipo: {}, by_bloque: {}, by_madurez: {} };
  mockSignals.forEach((s) => {
    counts.by_tipo[s.tipo] = (counts.by_tipo[s.tipo] || 0) + 1;
    counts.by_bloque[s.bloque] = (counts.by_bloque[s.bloque] || 0) + 1;
    counts.by_madurez[s.indice_madurez] = (counts.by_madurez[s.indice_madurez] || 0) + 1;
  });
  return counts;
}

function buildSyntheticDetail(sig) {
  const today = new Date();
  const history = [];
  for (let i = 0; i < 14; i += 1) {
    const wk = new Date(today.getTime() - (13 - i) * 7 * 86400 * 1000);
    history.push({
      semana: wk.toISOString().slice(0, 10),
      observed: Math.max(0, sig.expected_value * 0.85 + (i % 3) * (sig.expected_value * 0.1)),
      expected: sig.expected_value,
      band_lo: sig.confidence_band ? sig.confidence_band[0] : 0,
      band_hi: sig.confidence_band ? sig.confidence_band[1] : sig.expected_value * 1.5,
      is_campaign: i === 9,
    });
  }
  history[history.length - 1].observed = sig.observed_value;
  return {
    signal: sig,
    history,
    bandit: {
      signal_id: sig.signal_id,
      action_probabilities: { visita: 0.42, llamada: 0.21, email: 0.15, muestra: 0.13, monitorizar: 0.09 },
      recommended_action: "visita",
      confidence: 0.21,
    },
  };
}
