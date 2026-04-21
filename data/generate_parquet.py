"""
generate_parquet.py
-------------------
Run this locally to produce sample monthly sales parquet files.
Then upload the parquet_output/ folder to your Databricks Volume:
  /Volumes/my_catalog/my_schema/raw_data/sales/
"""
import pandas as pd
import numpy as np
from pathlib import Path

np.random.seed(42)

REGIONS  = ["North", "South", "East", "West"]
PRODUCTS = ["Widget A", "Widget B", "Gadget X", "Gadget Y", "Service Pro"]
STATUSES = ["completed", "pending", "refunded"]

rows = []
for year in [2024, 2025]:
    for month in range(1, 13):
        n = np.random.randint(80, 150)
        for _ in range(n):
            rows.append({
                "order_id":   f"ORD-{year}{month:02d}-{np.random.randint(10000,99999)}",
                "order_date": pd.Timestamp(year=year, month=month,
                                           day=np.random.randint(1, 28)),
                "year":       year,
                "month":      month,
                "region":     np.random.choice(REGIONS),
                "product":    np.random.choice(PRODUCTS),
                "quantity":   int(np.random.randint(1, 20)),
                "unit_price": round(float(np.random.uniform(10, 500)), 2),
                "status":     np.random.choice(STATUSES, p=[0.75, 0.15, 0.10]),
                "sales_rep":  f"Rep-{np.random.randint(1, 10)}",
            })

df = pd.DataFrame(rows)
df["revenue"] = (df["quantity"] * df["unit_price"]).round(2)

out = Path("parquet_output")
out.mkdir(exist_ok=True)

# One parquet file per month — mirrors real-world monthly drops
for (year, month), grp in df.groupby(["year", "month"]):
    path = out / f"sales_{year}_{month:02d}.parquet"
    grp.to_parquet(path, index=False, coerce_timestamps="us", allow_truncated_timestamps=True)
    print(f"  Written {len(grp):>4} rows → {path.name}")

print(f"\nTotal rows: {len(df):,}")
print("\nNext step: upload parquet_output/ to your Databricks Volume")
print("  /Volumes/<catalog>/<schema>/raw_data/sales/")
