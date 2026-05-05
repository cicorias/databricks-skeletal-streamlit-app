import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import type { MonthlyPoint } from '../types';
import styles from './MonthlyChart.module.css';

interface Props {
  points: MonthlyPoint[];
}

export function MonthlyChart({ points }: Props) {
  return (
    <div className={styles.row}>
      <div className={styles.col}>
        <h3>Monthly Revenue</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={points} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef0f3" />
            <XAxis dataKey="month" />
            <YAxis tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
            <Tooltip
              formatter={(v: number) => [`$${v.toLocaleString()}`, 'Revenue']}
              labelFormatter={(m) => `Month ${m}`}
            />
            <Bar dataKey="revenue" fill="#3b82f6" />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <div className={styles.col}>
        <h3>Monthly Orders</h3>
        <ResponsiveContainer width="100%" height={260}>
          <BarChart data={points} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="#eef0f3" />
            <XAxis dataKey="month" />
            <YAxis />
            <Tooltip labelFormatter={(m) => `Month ${m}`} />
            <Bar dataKey="orders" fill="#10b981" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </div>
  );
}
