import React, { useCallback, useEffect, useState } from "react";

import { fetchCounts, fetchSignals } from "./api/client.js";
import AlertList from "./components/AlertList.jsx";
import DetailPanel from "./components/DetailPanel.jsx";
import Sidebar from "./components/Sidebar.jsx";
import TopBar from "./components/TopBar.jsx";

export default function App() {
  const [signals, setSignals] = useState([]);
  const [counts, setCounts] = useState(null);
  const [filter, setFilter] = useState({ tipo: null, bloque: null, status: null, madurez: null, provincia: null });
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [dataSource, setDataSource] = useState(null);

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
          limit: 200,
        }),
        fetchCounts(),
      ]);
      setSignals(data);
      setCounts(c);
      setDataSource(source);
      // Keep selection only if still in list.
      setSelected((prev) => (data.some((s) => s.signal_id === prev) ? prev : data[0]?.signal_id ?? null));
    } catch (e) {
      setError(e.message || String(e));
    } finally {
      setLoading(false);
    }
  }, [filter.tipo, filter.bloque, filter.status, filter.madurez, filter.provincia]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <div className="root">
      <TopBar
        dataSource={dataSource}
        totalSignals={counts?.actionable_total ?? counts?.total}
      />
      <Sidebar counts={counts} filter={filter} onFilter={setFilter} />
      <AlertList
        signals={signals}
        selected={selected}
        onSelect={setSelected}
        loading={loading}
        error={error}
        statusFilter={filter.status}
      />
      <DetailPanel signalId={selected} onUpdate={refresh} />
    </div>
  );
}
