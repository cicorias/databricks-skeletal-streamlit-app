# ADR-001 — Frontend versions: React 18 vs 19, TypeScript 5 vs 6

| Field | Value |
|---|---|
| **Status** | Proposed |
| **Date** | 2026-05-04 |
| **Scope** | `flaskapp/` (Flask + React Sales Dashboard on Databricks Apps) |
| **Supersedes** | — |
| **Superseded by** | — |

## 1. Context

`flaskapp/package.json` was committed in a single commit (`d92cac3 adding react app`) with no rationale message. The pinned versions are:

| Package | Pinned | npm `latest` (today) |
|---|---|---|
| `react` | `^18.3.1` | `19.2.5` |
| `react-dom` | `^18.3.1` | `19.2.5` |
| `@types/react` | `^18.3.3` | `19.2.14` |
| `@types/react-dom` | `^18.3.0` | `19.2.3` |
| `recharts` | `^2.12.7` | `3.8.1` |
| `typescript` | `^5.5.4` | `6.0.3` |
| `vite` | `^5.4.1` | `8.0.10` |
| `@vitejs/plugin-react` | `^4.3.1` | `6.0.1` |

There is no commit message, README section, or session record explaining why these specific versions were chosen. This ADR records the inferred original rationale and evaluates whether to upgrade to React 19 + TypeScript 6 now.

The frontend lives at `flaskapp/frontend/` and is built by Databricks Apps' platform `npm install` + `npm run build` step at deploy time (per Databricks Apps platform docs and repo convention; the platform sets `NODE_ENV=production`, so all build-time deps must live under `dependencies`, which is already correct in `package.json`).

## 2. Inferred original rationale

### React 18.3.1 (specifically — not 18.0/18.1/18.2 and not 19.x)

- The **18.3 line is the React 19 "bridge" release**: it emits dev-mode deprecation warnings for every API React 19 will remove. Picking 18.3 over 18.2 indicates the author was deliberately staging for a future 19 jump rather than just "any 18.x".
- **Recharts 2.12 had no stable React 19 support** at scaffold time (open issue [recharts/recharts#4558]; only an alpha 2.13 line; full peer-`react ^19` support landed in Recharts 3.x). React 18 was the last fully-compatible major for the chart library actually used by `frontend/src/components/MonthlyChart.tsx`.
- Jumping straight to React 19 would have forced a simultaneous Recharts 2 → 3 jump, doubling the migration blast radius for what is otherwise a small read-only dashboard.

### TypeScript 5.5.4 (not 5.6/5.7/5.8 and not TS 6)

- TypeScript 6.0 had not yet shipped (its release was 2026-03-23, after this scaffold).
- TypeScript 5.5 was a mature point release in the 5.x line and is well understood by Vite 5, which transpiles TS via esbuild — the `typescript` package itself is only used for `tsc --noEmit` typecheck.
- No TS 5.6+ feature was needed for this app, and pinning the lowest-still-current minor reduces churn from patch updates.

### Vite 5.4 + `@vitejs/plugin-react` 4.3

- Vite 5.4 is the stable line that pairs with React 18 and has peer support back to React 17.
- `@vitejs/plugin-react` 4.3.1 peer-`vite ^4.2 || ^5.0` (verified live against the npm registry) and pre-dates Vite 6/7/8 — matches Vite 5.

### Node 20+ (per `flaskapp/README.md`)

- Required floor for Vite 5 engines (`^18 || >=20`).
- Compatible with the Databricks Apps Node runtime (Node 22 LTS / 24 LTS as of 2026 per platform docs).

### Decision (recorded retroactively)

Pin to React 18.3 + TS 5.5 + Recharts 2.12 + Vite 5.4 to (a) match Recharts 2.x peer constraint, (b) stage for a future React 19 jump via 18.3's deprecation-warning bridge, (c) keep the toolchain at a single mature stable line as of the scaffold date, (d) honor the Databricks Apps platform's Node 20+ requirement.

This is a sensible choice. Nothing about the original pins was wrong.

## 3. Codebase audit for upgrade feasibility

The Flask app frontend is **idiomatic React 18.3 with no React-19-incompatible patterns**, verified by inspection of `flaskapp/frontend/src/`:

| Concern | Status |
|---|---|
| `ReactDOM.render` (removed in 19) | Not used. `main.tsx` already uses `ReactDOM.createRoot(...)`. ✅ |
| `ReactDOM.hydrate` (removed in 19) | Not used. ✅ |
| `findDOMNode` (removed in 19) | Not used. ✅ |
| `forwardRef` (deprecated in 19) | Not used. ✅ |
| `defaultProps` on function components (removed in 19) | Not used. ✅ |
| `propTypes` (deprecated in 19) | Not used. ✅ |
| `useFormState` (renamed `useActionState` in 19) | Not used (no forms). ✅ |
| `.ref` as element attribute (now a prop in 19) | Not used. ✅ |
| `<React.StrictMode>` already on | Yes, in `main.tsx`. ✅ |
| `useEffect` cleanup pattern | Yes (`cancelled` flag in `App.tsx` effects). ✅ |
| Recharts API surface used | Only stable core primitives in `MonthlyChart.tsx`: `Bar`, `BarChart`, `CartesianGrid`, `ResponsiveContainer`, `Tooltip`, `XAxis`, `YAxis`. All present and stable in Recharts 3.x. ✅ |

`frontend/tsconfig.json` is also already TS-6-shaped:

| TS 6 breaking change | Our state |
|---|---|
| ES5/ES3 `target` removed | We use `target: "ES2022"`. ✅ |
| `moduleResolution: "classic"` removed | We use `"bundler"`. ✅ |
| `strict: true` is now the default | We already set it explicitly. ✅ |
| Removed flags: `--downlevelIteration`, `--noImplicitUseStrict`, `--suppressImplicitAnyIndexErrors` | None present. ✅ |

**Verdict: LOW migration risk for both React 19 and TS 6.** The codebase looks like it was written with React 19 in mind, even though it pins 18.3.

## 4. Upgrade tiers

Three candidate upgrade tiers, each fully characterized below.

### Tier 1 — Conservative

Bump only the React stack, types, Recharts, and TypeScript. Keep Vite 5.4 and `@vitejs/plugin-react` 4.3.

| Package | From | To |
|---|---|---|
| `react` | `^18.3.1` | `^19.2.5` |
| `react-dom` | `^18.3.1` | `^19.2.5` |
| `@types/react` | `^18.3.3` | `^19.2.14` |
| `@types/react-dom` | `^18.3.0` | `^19.2.3` |
| `recharts` | `^2.12.7` | `^3.8.1` |
| `typescript` | `^5.5.4` | `^6.0.3` |
| `vite` | `^5.4.1` | unchanged |
| `@vitejs/plugin-react` | `^4.3.1` | unchanged (or sub-bump to `^4.5.0` for post-React-19 fixes) |

**Known issues / dep-support gaps for Tier 1:**

1. **`@vitejs/plugin-react` 4.3.1 pre-dates React 19 stable.** It will *function* (Vite uses esbuild for transformation, and React 19's `react/jsx-runtime` is forward-compatible) but its HMR adapter and Fast Refresh boundary detection were improved in 4.4+. *Recommended sub-bump within this tier:* `^4.5.0` (still vite ^5 compatible).
2. **Vite 5.4 has no documented incompatibility with React 19.** Vite is framework-agnostic at runtime; the React-specific work is in the plugin.
3. **Recharts 3 is a major bump from 2.12.** APIs we use (`Bar`, `BarChart`, `CartesianGrid`, `ResponsiveContainer`, `Tooltip`, `XAxis`, `YAxis`) are unchanged in shape, but Recharts 3 tightened generic prop typing. **Expect 0–2 TS errors in `MonthlyChart.tsx`** during typecheck; should be one-line fixes.
4. **TS 6 stricter-by-default flags only kick in for *new* tsconfigs.** Our tsconfig already explicitly sets `strict: true`, so this doesn't change behavior.

### Tier 2 — Moderate

Tier 1 + bump `@vitejs/plugin-react` to the latest line that still supports Vite 5.

| Package | From | To |
|---|---|---|
| (Tier 1 changes) | | |
| `vite` | `^5.4.1` | `^5.4.20` (latest 5.x patch) |
| `@vitejs/plugin-react` | `^4.3.1` | `^5.0.3` |

**Known issues / dep-support gaps for Tier 2:**

1. `@vitejs/plugin-react` 5.0.x peer is `vite ^4.2 || ^5 || ^6 || ^7` — works on Vite 5. ✅
2. **The user-suggested combination "plugin-react 6.x on Vite 5" is not installable.** `@vitejs/plugin-react` 6.0.x peer is `vite ^8` only (verified live against the npm registry). npm would either error or, with `--legacy-peer-deps`, install but break at HMR runtime. Tier 2 therefore caps at `plugin-react 5.0.x`.
3. Bumping plugin-react across a major (4 → 5) is generally drop-in for app code (the plugin API surface used in `vite.config.ts` doesn't change), but you should re-run `make build-frontend` to confirm no new warnings.
4. All Tier 1 caveats still apply.

### Tier 3 — Aggressive

Tier 2 + bump Vite to the latest major and plugin-react to the matching latest.

| Package | From | To |
|---|---|---|
| (Tier 1 changes) | | |
| `vite` | `^5.4.1` | `^8.0.10` |
| `@vitejs/plugin-react` | `^4.3.1` | `^6.0.1` |

**Known issues / dep-support gaps for Tier 3:**

1. **Vite 8 engines: `node ^20.19.0 || >=22.12.0`.** The current `flaskapp/README.md` says "Node 20+" — that needs to be tightened, otherwise developers on Node 20.0–20.18 will see install errors. The deployed Databricks Apps platform itself runs Node 22 LTS / 24 LTS so the deployed-app side is unaffected; this is a local-dev concern.
2. **Cumulative breaking changes Vite 5 → 8** (no single migration guide exists — only sequential 5→6, 6→7, 7→8 documents):
   - Vite 6 dropped Node 18 LTS, switched to a new dev-server architecture (Environments API), and changed how `import.meta.env` types are exposed.
   - Vite 7 dropped some legacy rollup options.
   - Vite 8 requires Node 20.19+.
3. `flaskapp/frontend/vite.config.ts` is small (proxy config + `react()` plugin call). It should port without changes but needs verification with `make build-frontend`.
4. **plugin-react 6.x** changes JSX runtime detection to assume React 17+ automatic JSX runtime exclusively. We already use that (`jsx: "react-jsx"` in tsconfig), so no source changes needed.
5. **Documentation gap:** the upstream Vite 8 release notes do not have a comprehensive "migrating from 5.x" section — only point migration guides per major. Migration is well-specified but spread across three documents.
6. **Recommended addition to `package.json`:**
   ```json
   "engines": { "node": "^20.19.0 || >=22.12.0" }
   ```
   …both for local-dev clarity and to fail-fast on incompatible Node versions.
7. All Tier 1 + Tier 2 caveats still apply.

## 5. Scoring

Each tier is scored on six dimensions (1 = worst, 5 = best). "Risk" and "Effort" are inverted so higher = better in all dimensions, making the totals directly comparable. Recommendation = highest weighted total.

| Dimension | Weight | Tier 1 (Conservative) | Tier 2 (Moderate) | Tier 3 (Aggressive) |
|---|---:|:---:|:---:|:---:|
| **Migration risk** (5 = lowest risk) | 3 | 5 | 4 | 3 |
| **Engineering effort** (5 = lowest effort) | 2 | 5 | 4 | 2 |
| **Answers user's question** (React 18→19 / TS 5→6) | 3 | 5 | 5 | 5 |
| **Future-proofing of toolchain** | 2 | 3 | 4 | 5 |
| **Dep-support cleanliness** (5 = no known gaps) | 2 | 4 | 5 | 3 |
| **Documentation quality of upstream upgrade path** | 1 | 5 | 4 | 2 |
| **Weighted total** (max 65) | | **58** | **57** | **49** |
| **Unweighted total** (max 30) | | **27** | **26** | **20** |

### Per-tier rationale for individual scores

**Tier 1 — Conservative (58/65)**
- Risk **5/5**: only changes the libraries the user actually asked about. Zero changes to the build toolchain, zero changes to source for the React migration (audit shows no incompatible patterns).
- Effort **5/5**: ~6 lines of `package.json` edits + one `npm install` + one `make typecheck`. Worst case 1–2 fixes in `MonthlyChart.tsx` for Recharts 3 prop generics.
- User-question **5/5**: directly resolves React 18 vs 19 and TS 5 vs 6.
- Future-proofing **3/5**: still on Vite 5 line and `plugin-react 4.x`, both of which will eventually need bumping.
- Dep-support **4/5**: one minor gap — `plugin-react 4.3.1` pre-dates React 19 stable. The optional sub-bump to `^4.5.0` raises this to 5/5.
- Doc quality **5/5**: React 19 migration guide is comprehensive, TS 6 release notes are complete, Recharts 3 migration guide is published.

**Tier 2 — Moderate (57/65)**
- Risk **4/5**: adds a plugin-react major bump (4 → 5) on top of Tier 1.
- Effort **4/5**: one extra line bump + one extra build verification.
- User-question **5/5**: same as Tier 1.
- Future-proofing **4/5**: brings the plugin into a line that supports Vite 6/7 too (cheaper future Vite bump).
- Dep-support **5/5**: `plugin-react 5.0.x` peer-supports Vite 4–7, no known incompatibility with React 19.
- Doc quality **4/5**: plugin-react 4 → 5 changelog is shorter and less commented than the React/TS docs.

**Tier 3 — Aggressive (49/65)**
- Risk **3/5**: cumulative Vite 5 → 6 → 7 → 8 changes plus plugin-react 4 → 6 increase the surface area materially.
- Effort **2/5**: requires Node version bump for local dev, README update, possible `vite.config.ts` adjustments, and three sequential migration-guide reviews.
- User-question **5/5**: same as Tier 1.
- Future-proofing **5/5**: fully modern toolchain.
- Dep-support **3/5**: needs explicit `engines` field added; current README's Node 20+ floor is too loose.
- Doc quality **2/5**: no consolidated 5→8 guide; three separate point-release migration documents to chase.

### Recommendation

**Tier 1 (sub-bump variant: `@vitejs/plugin-react ^4.5.0`).** This wins on the weighted score and isolates the React-major / TS-major migration from independent Vite-toolchain modernization, which keeps blame small if anything breaks post-deploy.

Tier 2 is a close second (only 1 point behind on the weighted scale) and is a reasonable choice if "stay-on-Vite-5-but-modernize-the-plugin" feels worth the small extra effort.

Tier 3 should be deferred to a follow-up ADR (proposed: ADR-002), so its risk doesn't pollute the React 18→19 / TS 5→6 work.

## 6. Decision

*To be ratified by the operator at plan exit.*

Default proposed: **Tier 1 with sub-bump** (`react ^19.2.5`, `react-dom ^19.2.5`, `@types/react ^19.2.14`, `@types/react-dom ^19.2.3`, `recharts ^3.8.1`, `typescript ^6.0.3`, `@vitejs/plugin-react ^4.5.0`; Vite unchanged at `^5.4.1`).

## 7. Consequences

- The build pipeline gains the React 19 compiler optimizations and TS 6's stricter-by-default behaviors (no-op for us since strict is already on).
- `package-lock.json` will regenerate; it will be re-committed.
- Future ADRs will track Vite 5 → 8 migration (Tier 3) if/when desired.
- `flaskapp/README.md` will be updated to cross-link this ADR.
- Databricks Apps' deploy step (`npm install` + `npm run build`) will build against Node 22+ on the platform; the new versions are all known-compatible with that runtime per the npm registry's `engines` fields.

## 8. References

- React 19 upgrade guide: https://react.dev/blog/2024/04/25/react-19-upgrade-guide
- TypeScript 6.0 release notes: https://www.typescriptlang.org/docs/handbook/release-notes/typescript-6-0.html
- Recharts React 19 support tracker: https://github.com/recharts/recharts/issues/4558
- Databricks Apps configuration: https://docs.databricks.com/aws/en/dev-tools/databricks-apps/app-runtime
- Live npm peer-dep matrix queried in this ADR: see Section 4 tables.
