import React, { useCallback, useEffect, useState } from "react";

import { fetchCounts, fetchSignals } from "./api/client.js";
import AlertList from "./components/AlertList.jsx";
import DetailPanel from "./components/DetailPanel.jsx";
import Sidebar from "./components/Sidebar.jsx";
import TerritorialMap from "./components/TerritorialMap.jsx";
import TopBar from "./components/TopBar.jsx";

const INITIAL_FILTER = {
  tipo: null,
  bloque: null,
  status: null,
  madurez: null,
  provincia: null,
  comunidad_autonoma: null,
};

export default function App() {
  const [signals, setSignals] = useState([]);
  const [counts, setCounts] = useState(null);
  const [filter, setFilter] = useState(INITIAL_FILTER);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dataSource, setDataSource] = useState(null);
  const [showMap, setShowMap] = useState(true);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [{ data, source }, c] = await Promise.all([
        fetchSignals({
          tipo: filter.tipo,
          bloque: filter.bloque,
          status: filter.status,
          madurez: filter.madurez,
          provincia: filter.provincia,
          comunidad_autonoma: filter.comunidad_autonoma,
          limit: 200,
        }),
        fetchCounts(),
      ]);
      setSignals(data);
      setCounts(c);
      setDataSource(source);
      setSelected((prev) => (data.some((s) => s.signal_id === prev) ? prev : data[0]?.signal_id ?? null));
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [
    filter.tipo,
    filter.bloque,
    filter.status,
    filter.madurez,
    filter.provincia,
    filter.comunidad_autonoma,
  ]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleProvinciaSelect = (provincia) =>
    setFilter((f) => ({ ...f, provincia, comunidad_autonoma: null }));
  const handleComunidadSelect = (ccaa) =>
    setFilter((f) => ({ ...f, provincia: null, comunidad_autonoma: ccaa }));

  return (
    <div className="root">
      <TopBar
        dataSource={dataSource}
        totalSignals={counts?.actionable_total ?? counts?.total}
        showMap={showMap}
        onToggleMap={() => setShowMap((v) => !v)}
      />
      <Sidebar counts={counts} filter={filter} onFilter={setFilter} />
      <main className="main-panel">
        {showMap && (
          <TerritorialMap
            filter={filter}
            onProvinciaSelect={handleProvinciaSelect}
            onComunidadSelect={handleComunidadSelect}
          />
        )}
        <AlertList
          signals={signals}
          selected={selected}
          onSelect={setSelected}
          loading={loading}
          error={error}
          statusFilter={filter.status}
        />
      </main>
      <DetailPanel signalId={selected} onUpdate={refresh} />
    </div>
  );
}
