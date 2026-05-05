import type { PivotRow } from '../types';
import styles from './RegionProductPivot.module.css';

interface Props {
  rows: PivotRow[];
}

export function RegionProductPivot({ rows }: Props) {
  const regions = Array.from(new Set(rows.map((r) => r.region))).sort();
  const products = Array.from(new Set(rows.map((r) => r.product))).sort();
  const lookup = new Map<string, number>();
  for (const r of rows) lookup.set(`${r.region}::${r.product}`, r.revenue);

  const fmt = (n: number) => `$${n.toLocaleString('en-US', { maximumFractionDigits: 0 })}`;

  return (
    <div className={styles.wrap}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Region</th>
            {products.map((p) => (
              <th key={p}>{p}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {regions.map((region) => (
            <tr key={region}>
              <th scope="row">{region}</th>
              {products.map((p) => (
                <td key={p}>{fmt(lookup.get(`${region}::${p}`) ?? 0)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
