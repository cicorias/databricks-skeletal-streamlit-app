import type { LeaderRow } from '../types';
import styles from './Leaderboard.module.css';

interface Props {
  rows: LeaderRow[];
  month: number;
  onMonthChange: (m: number) => void;
}

export function Leaderboard({ rows, month, onMonthChange }: Props) {
  const fmt = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;

  return (
    <div className={styles.wrap}>
      <div className={styles.head}>
        <label>
          Month: <strong>{month}</strong>
          <input
            type="range"
            min={1}
            max={12}
            value={month}
            onChange={(e) => onMonthChange(Number(e.target.value))}
          />
        </label>
      </div>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Rank</th>
            <th>Sales Rep</th>
            <th>Orders</th>
            <th>Revenue</th>
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 && (
            <tr>
              <td colSpan={4} className={styles.empty}>
                No leaderboard data for the selected month.
              </td>
            </tr>
          )}
          {rows.map((r) => (
            <tr key={r.rank}>
              <td>{r.rank}</td>
              <td>{r.sales_rep}</td>
              <td>{r.orders.toLocaleString()}</td>
              <td>{fmt(r.revenue)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
