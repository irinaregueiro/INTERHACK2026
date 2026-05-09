import React from "react";
import { Line } from "react-chartjs-2";
import {
  Chart as ChartJS,
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Filler,
  Tooltip,
  Legend,
} from "chart.js";

ChartJS.register(CategoryScale, LinearScale, PointElement, LineElement, Filler, Tooltip, Legend);

export default function ConfidenceChart({ history, signal }) {
  if (!history?.length) return <div className="small">Sin historial disponible.</div>;

  const labels = history.map((r) => r.semana);
  const observed = history.map((r) => r.observed);
  const expected = history.map((r) => r.expected);
  const lo = history.map((r) => r.band_lo);
  const hi = history.map((r) => r.band_hi);

  // Color the observed point red if outside band.
  const pointColors = history.map((r) => {
    if (r.observed > r.band_hi || r.observed < r.band_lo) return "#d62f3a";
    return "#1f3da3";
  });

  const data = {
    labels,
    datasets: [
      {
        label: "Banda P95",
        data: hi,
        borderColor: "rgba(9, 133, 81, 0.45)",
        borderDash: [4, 3],
        backgroundColor: "rgba(9, 133, 81, 0.08)",
        pointRadius: 0,
        fill: "+1",
        tension: 0.25,
      },
      {
        label: "Banda P5",
        data: lo,
        borderColor: "rgba(9, 133, 81, 0.45)",
        borderDash: [4, 3],
        pointRadius: 0,
        backgroundColor: "rgba(9, 133, 81, 0.0)",
        fill: false,
        tension: 0.25,
      },
      {
        label: "Esperado",
        data: expected,
        borderColor: "rgba(31, 61, 163, 0.55)",
        borderWidth: 1.5,
        pointRadius: 0,
        borderDash: [2, 2],
        fill: false,
      },
      {
        label: "Observado",
        data: observed,
        borderColor: "#1f3da3",
        backgroundColor: "rgba(31, 61, 163, 0.05)",
        pointBackgroundColor: pointColors,
        pointBorderColor: pointColors,
        pointRadius: 3,
        borderWidth: 2,
        tension: 0.2,
        fill: false,
      },
    ],
  };

  const options = {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "bottom", labels: { boxWidth: 10, font: { size: 11 } } },
      tooltip: {
        callbacks: {
          afterBody: (items) => {
            const idx = items[0]?.dataIndex;
            const row = history[idx];
            return row?.is_campaign ? "[campaña activa]" : "";
          },
        },
      },
    },
    scales: {
      x: { ticks: { font: { size: 10 }, maxRotation: 0, autoSkip: true } },
      y: { beginAtZero: true, ticks: { font: { size: 10 } } },
    },
  };

  return (
    <div style={{ height: 220 }}>
      <Line data={data} options={options} />
    </div>
  );
}
