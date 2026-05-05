import { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from './api';
import { FiltersBar } from './components/Filters';
import { KpiCards } from './components/KpiCards';
import { Leaderboard } from './components/Leaderboard';
import { MonthlyChart } from './components/MonthlyChart';
import { RegionProductPivot } from './components/RegionProductPivot';
import type {
  Filters,
  Kpis,
  LeaderRow,
  MonthlyPoint,
  PivotRow,
  Selection,
} from './types';
import styles from './App.module.css';

interface DashboardData {
  kpis: Kpis;
  monthly: MonthlyPoint[];
  pivot: PivotRow[];
}

export function App() {
  const [filters, setFilters] = useState<Filters | null>(null);
  const [selection, setSelection] = useState<Selection | null>(null);
  const [data, setData] = useState<DashboardData | null>(null);
  const [leaderboardMonth, setLeaderboardMonth] = useState<number>(1);
  const [leaderboard, setLeaderboard] = useState<LeaderRow[] | null>(null);
  const [healthMode, setHealthMode] = useState<string>('?');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  // Initial load: filters + health mode.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [f, h] = await Promise.all([api.filters(), api.health()]);
        if (cancelled) return;
        setFilters(f);
        setHealthMode(h.mode);
        if (f.years.length === 0 || f.regions.length === 0 || f.products.length === 0) {
          setError('No data available — check that the materialized views are populated.');
          setLoading(false);
          return;
        }
        setSelection({
          year: f.years[0],
          regions: [...f.regions],
          products: [...f.products],
        });
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : String(e));
          setLoading(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const fetchDashboard = useCallback(async (sel: Selection) => {
    setLoading(true);
    setError(null);
    try {
      const [kpis, monthly, pivot] = await Promise.all([
        api.kpis(sel),
        api.monthly(sel),
        api.regionProduct(sel),
      ]);
      setData({ kpis, monthly: monthly.points, pivot: pivot.rows });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, []);

  // Re-fetch dashboard data on selection change.
  useEffect(() => {
    if (!selection) return;
    if (selection.regions.length === 0 || selection.products.length === 0) {
      setData(null);
      setLoading(false);
      return;
    }
    void fetchDashboard(selection);
  }, [selection, fetchDashboard]);

  // Re-fetch leaderboard when year or month changes.
  useEffect(() => {
    if (!selection) return;
    let cancelled = false;
    (async () => {
      try {
        const lb = await api.leaderboard(selection.year, leaderboardMonth);
        if (!cancelled) setLeaderboard(lb.rows);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [selection, leaderboardMonth]);

  const banner = useMemo(() => {
    if (error) return <div className={styles.error}>⚠ {error}</div>;
    if (!filters) return <div className={styles.info}>Loading filters…</div>;
    return null;
  }, [error, filters]);

  return (
    <div className={styles.app}>
      <header className={styles.header}>
        <div>
          <h1>Sales Dashboard</h1>
          <p>Materialized views via Serverless SQL — Flask + React + Vite.</p>
        </div>
        <span className={styles.modeBadge} data-mode={healthMode}>
          {healthMode}
        </span>
      </header>

      {banner}

      {filters && selection && (
        <FiltersBar filters={filters} selection={selection} onChange={setSelection} />
      )}

      {selection && (selection.regions.length === 0 || selection.products.length === 0) && (
        <div className={styles.info}>Select at least one region and one product.</div>
      )}

      {loading && !data && filters && selection && (
        <div className={styles.info}>Loading dashboard…</div>
      )}

      {data && (
        <>
          <section className={styles.section}>
            <KpiCards kpis={data.kpis} />
          </section>
          <section className={styles.section}>
            <MonthlyChart points={data.monthly} />
          </section>
          <section className={styles.section}>
            <h2>Revenue by Region × Product</h2>
            <RegionProductPivot rows={data.pivot} />
          </section>
        </>
      )}

      {selection && leaderboard && (
        <section className={styles.section}>
          <h2>🏆 Rep Leaderboard</h2>
          <Leaderboard
            rows={leaderboard}
            month={leaderboardMonth}
            onMonthChange={setLeaderboardMonth}
          />
        </section>
      )}
    </div>
  );
}
