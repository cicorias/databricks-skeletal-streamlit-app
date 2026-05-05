import type { Filters, Selection } from '../types';
import styles from './Filters.module.css';

interface Props {
  filters: Filters;
  selection: Selection;
  onChange: (next: Selection) => void;
}

export function FiltersBar({ filters, selection, onChange }: Props) {
  const toggle = (list: string[], value: string) =>
    list.includes(value) ? list.filter((v) => v !== value) : [...list, value];

  return (
    <div className={styles.bar}>
      <label className={styles.field}>
        <span>Year</span>
        <select
          value={selection.year}
          onChange={(e) => onChange({ ...selection, year: Number(e.target.value) })}
        >
          {filters.years.map((y) => (
            <option key={y} value={y}>
              {y}
            </option>
          ))}
        </select>
      </label>

      <fieldset className={styles.fieldset}>
        <legend>Region</legend>
        <div className={styles.checks}>
          {filters.regions.map((r) => (
            <label key={r} className={styles.check}>
              <input
                type="checkbox"
                checked={selection.regions.includes(r)}
                onChange={() =>
                  onChange({ ...selection, regions: toggle(selection.regions, r) })
                }
              />
              <span>{r}</span>
            </label>
          ))}
        </div>
      </fieldset>

      <fieldset className={styles.fieldset}>
        <legend>Product</legend>
        <div className={styles.checks}>
          {filters.products.map((p) => (
            <label key={p} className={styles.check}>
              <input
                type="checkbox"
                checked={selection.products.includes(p)}
                onChange={() =>
                  onChange({ ...selection, products: toggle(selection.products, p) })
                }
              />
              <span>{p}</span>
            </label>
          ))}
        </div>
      </fieldset>
    </div>
  );
}
