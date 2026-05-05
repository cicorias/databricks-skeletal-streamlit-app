import type { Kpis } from '../types';
import styles from './KpiCards.module.css';

const fmtMoney = (n: number) =>
  `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;
const fmtCount = (n: number) => n.toLocaleString('en-US');

interface Props {
  kpis: Kpis;
}

export function KpiCards({ kpis }: Props) {
  const cards = [
    { label: 'Total Revenue', value: fmtMoney(kpis.revenue) },
    { label: 'Total Orders', value: fmtCount(kpis.orders) },
    { label: 'Completed Rev', value: fmtMoney(kpis.completed) },
    { label: 'Refunded Rev', value: fmtMoney(kpis.refunded) },
  ];

  return (
    <div className={styles.grid}>
      {cards.map((c) => (
        <div key={c.label} className={styles.card}>
          <div className={styles.label}>{c.label}</div>
          <div className={styles.value}>{c.value}</div>
        </div>
      ))}
    </div>
  );
}
