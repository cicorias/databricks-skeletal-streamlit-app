"""
app.py  —  Streamlit POC (Databricks Apps with OBO auth)
Run inside a Databricks App:
  streamlit run app.py
Env vars required:
  On Databricks Apps: auto-injected (DATABRICKS_HOST, CLIENT_ID/SECRET)
  Locally: DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_HTTP_PATH,
           DATABRICKS_CATALOG, DATABRICKS_SCHEMA  (via .env / 'make env')
"""
import base64
import json
import os
from datetime import datetime, timezone

import pandas as pd
import streamlit as st
try:
    from app.auth import AuthError, get_sp_config, get_user_email, get_user_token
    from app.db import query_df, T_MV_MONTHLY, T_MV_LEADER, T_WORKFLOW_AUDIT
    from app.workflow import submit, act, get_queue, get_step_trail
except ImportError:
    from auth import AuthError, get_sp_config, get_user_email, get_user_token
    from db import query_df, T_MV_MONTHLY, T_MV_LEADER, T_WORKFLOW_AUDIT
    from workflow import submit, act, get_queue, get_step_trail

# ── JWT helpers (used by Session Debug page) ─────────────────────
def _decode_jwt(token: str) -> dict:
    """Decode a JWT without signature verification (display only)."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return {"error": "Not a valid JWT (expected 3 dot-separated parts)"}

        def _b64(segment: str) -> dict:
            segment += "=" * (-len(segment) % 4)
            return json.loads(base64.urlsafe_b64decode(segment))

        return {"header": _b64(parts[0]), "payload": _b64(parts[1])}
    except Exception as exc:
        return {"error": str(exc)}


def _format_epoch(epoch: int | float) -> str:
    """Convert an epoch timestamp to a human-readable UTC string."""
    try:
        dt = datetime.fromtimestamp(epoch, tz=timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    except (TypeError, ValueError, OSError):
        return str(epoch)


# ── Volume browsing helpers (Pipeline Lineage page) ──────────────
VOLUME_BASE = os.environ.get(
    "SILVER_VOLUME_PATH",
    f"/Volumes/{os.environ.get('DATABRICKS_CATALOG', 'dev')}"
    f"/{os.environ.get('DATABRICKS_SCHEMA', 'default')}"
    f"/{os.environ.get('SILVER_VOLUME_NAME', 'silver')}",
)


def _lineage_cache() -> dict:
    """Return the per-session cache dict for lineage data."""
    if "_lineage_cache" not in st.session_state:
        st.session_state["_lineage_cache"] = {}
    return st.session_state["_lineage_cache"]


def _list_subdirs(path: str) -> list[str]:
    """List subdirectory names under the given Volumes path (session-cached)."""
    cache = _lineage_cache()
    key = f"dirs:{path}"
    if key not in cache:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient(config=get_sp_config())
        cache[key] = sorted(
            e.name for e in w.files.list_directory_contents(path)
            if e.is_directory
        )
    return cache[key]


def _read_json_file(path: str) -> dict | list:
    """Read and parse a JSON file from Volumes (session-cached)."""
    cache = _lineage_cache()
    key = f"json:{path}"
    if key not in cache:
        from databricks.sdk import WorkspaceClient
        w = WorkspaceClient(config=get_sp_config())
        resp = w.files.download(path)
        cache[key] = json.loads(resp.contents.read())
    return cache[key]


def _render_lineage_html(data: dict) -> None:
    """Render pipeline lineage audit JSON as a styled HTML dashboard."""

    status = data.get("overall_status", "UNKNOWN")
    pass_count = data.get("pass_count", 0)
    fail_count = data.get("fail_count", 0)
    step = data.get("step", "")
    job_folder = data.get("job_folder", "")

    # ── Status banner ────────────────────────────────────────────
    _STYLE = {
        "PASS": ("#4caf50", "#0d3b0d"),
        "WARN": ("#ff9800", "#3b2e0d"),
        "FAIL": ("#f44336", "#3b0d0d"),
    }
    fg, bg = _STYLE.get(status, ("#aaa", "#2d2d2d"))

    st.markdown(
        f'<div style="display:flex;align-items:center;gap:16px;padding:12px 20px;'
        f'background:{bg};border-left:4px solid {fg};border-radius:6px;margin-bottom:16px;">'
        f'<span style="font-size:1.4rem;font-weight:700;color:{fg};">{status}</span>'
        f'<span style="color:#ccc;">Step: <b>{step}</b></span>'
        f'<span style="color:#ccc;margin-left:auto;">'
        f"✅&nbsp;{pass_count} passed &nbsp;&nbsp; ❌&nbsp;{fail_count} failed"
        f"</span></div>",
        unsafe_allow_html=True,
    )

    if job_folder:
        st.caption(f"Job folder: `{job_folder}`")

    # ── Section summary cards ────────────────────────────────────
    _SECTIONS = [
        ("📊 Source", "source"),
        ("⚖️ OOB Check", "oob_check"),
        ("📋 Working Tab", "working_tab"),
        ("📦 Load Tab", "load_tab"),
        ("📤 Upload Tab", "upload_tab"),
    ]

    cols = st.columns(len(_SECTIONS))
    for col, (title, key) in zip(cols, _SECTIONS):
        section = data.get(key)
        if not section or not isinstance(section, dict):
            continue
        with col:
            rows_html = ""
            for k, v in section.items():
                label = k.replace("_", " ").replace("gl ", "GL ").title()
                if isinstance(v, bool):
                    val_str = '<span style="color:#4caf50;">✅</span>' if v else '<span style="color:#f44336;">❌</span>'
                elif isinstance(v, float):
                    val_str = f"{v:,.2f}"
                elif isinstance(v, int):
                    val_str = f"{v:,}"
                else:
                    val_str = str(v)
                rows_html += (
                    f'<tr>'
                    f'<td style="padding:3px 6px;color:#999;font-size:.78rem;">{label}</td>'
                    f'<td style="padding:3px 6px;text-align:right;font-size:.78rem;">{val_str}</td>'
                    f'</tr>'
                )
            st.markdown(
                f'<div style="background:#1a1a2e;border-radius:8px;padding:10px;height:100%;">'
                f'<div style="font-weight:600;color:#ccc;font-size:.85rem;margin-bottom:6px;">{title}</div>'
                f'<table style="width:100%;">{rows_html}</table>'
                f'</div>',
                unsafe_allow_html=True,
            )

    st.divider()

    # ── Tick & Tie table ─────────────────────────────────────────
    ties = data.get("tick_and_tie", [])
    if ties:
        st.subheader("Tick & Tie Checks")
        rows_html = ""
        for t in ties:
            passed = t.get("ties", False)
            icon = "✅" if passed else "❌"
            row_bg = "#0d1f0d" if passed else "#2a0f0f"
            rows_html += (
                f'<tr style="background:{row_bg};">'
                f'<td style="padding:8px 12px;font-family:monospace;font-weight:600;">{t.get("ref", "")}</td>'
                f'<td style="padding:8px 12px;">{t.get("description", "")}</td>'
                f'<td style="padding:8px 12px;text-align:center;font-size:1.2rem;">{icon}</td>'
                f'</tr>'
            )

        st.markdown(
            '<table style="width:100%;border-collapse:collapse;border-radius:8px;overflow:hidden;">'
            '<thead><tr style="background:#1a1a2e;">'
            '<th style="padding:10px 12px;text-align:left;color:#aaa;width:80px;">Ref</th>'
            '<th style="padding:10px 12px;text-align:left;color:#aaa;">Description</th>'
            '<th style="padding:10px 12px;text-align:center;color:#aaa;width:80px;">Ties</th>'
            f'</tr></thead><tbody>{rows_html}</tbody></table>',
            unsafe_allow_html=True,
        )

    # ── Raw JSON in expander ─────────────────────────────────────
    with st.expander("📄 Raw JSON"):
        st.json(data)




def main():
    # ── Page config ──────────────────────────────────────────────────
    st.set_page_config(
        page_title="Sales Review Portal",
        page_icon="📊",
        layout="wide",
    )

    # ── Minimal custom CSS ────────────────────────────────────────────
    st.markdown("""
    <style>
      [data-testid="stSidebar"] { background: #0f1117; }
      .step-badge {
          display: inline-block; padding: 2px 10px; border-radius: 12px;
          font-size: 0.75rem; font-weight: 600; margin: 2px;
      }
      .badge-pending  { background:#2d2d2d; color:#aaa; }
      .badge-approved { background:#0d3b0d; color:#4caf50; }
      .badge-rejected { background:#3b0d0d; color:#f44336; }
    </style>
    """, unsafe_allow_html=True)


    # ── Sidebar — user identity from Databricks Apps headers ──────────
    with st.sidebar:
        st.title("📊 Sales Portal")
        st.divider()
        try:
            user = get_user_email()
        except AuthError as e:
            st.error(str(e))
            st.stop()
        st.markdown(f"**{user}**")
        role  = st.selectbox("Your role", ["manager", "finance", "director", "submitter"], key="sidebar_role")
        st.divider()
        page  = st.radio("Navigate", ["📈 Dashboard", "📋 Review Queue", "📜 Audit Log", "📁 Pipeline Lineage", "🔍 Session Debug"])


    # ════════════════════════════════════════════════════════════════════
    # PAGE 1 — DASHBOARD  (reads from materialized views)
    # ════════════════════════════════════════════════════════════════════
    if page == "📈 Dashboard":
        st.title("Sales Dashboard")
        st.caption("Data served from **materialized views** via Serverless SQL Warehouse — no Spark, pure Photon.")

        # ── Filters
        col1, col2, col3 = st.columns(3)
        years    = query_df(f"SELECT DISTINCT year FROM {T_MV_MONTHLY} ORDER BY year DESC")
        regions  = query_df(f"SELECT DISTINCT region FROM {T_MV_MONTHLY} ORDER BY region")
        products = query_df(f"SELECT DISTINCT product FROM {T_MV_MONTHLY} ORDER BY product")

        sel_year    = col1.selectbox("Year",    years["year"].tolist(), key="dash_year")
        sel_region  = col2.multiselect("Region", regions["region"].tolist(), default=regions["region"].tolist())
        sel_product = col3.multiselect("Product", products["product"].tolist(), default=products["product"].tolist())

        if not sel_region or not sel_product:
            st.warning("Select at least one region and product.")
            st.stop()

        # ── KPIs
        kpi_df = query_df(
            """
            SELECT
                SUM(total_revenue)      AS revenue,
                SUM(order_count)        AS orders,
                SUM(completed_revenue)  AS completed,
                SUM(refunded_revenue)   AS refunded
            FROM {tbl}
            WHERE year = ?
              AND region IN ({r})
              AND product IN ({p})
            """.format(
                tbl=T_MV_MONTHLY,
                r=",".join(["?"] * len(sel_region)),
                p=",".join(["?"] * len(sel_product)),
            ),
            [sel_year] + sel_region + sel_product,
        ).iloc[0]

        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Total Revenue",    f"${kpi_df['revenue']:,.0f}")
        k2.metric("Total Orders",     f"{kpi_df['orders']:,.0f}")
        k3.metric("Completed Rev",    f"${kpi_df['completed']:,.0f}")
        k4.metric("Refunded Rev",     f"${kpi_df['refunded']:,.0f}")

        st.divider()

        # ── Monthly trend
        trend_df = query_df(
            """
            SELECT month, SUM(total_revenue) AS revenue, SUM(order_count) AS orders
            FROM {tbl}
            WHERE year = ? AND region IN ({r}) AND product IN ({p})
            GROUP BY month ORDER BY month
            """.format(
                tbl=T_MV_MONTHLY,
                r=",".join(["?"] * len(sel_region)),
                p=",".join(["?"] * len(sel_product)),
            ),
            [sel_year] + sel_region + sel_product,
        )

        left, right = st.columns(2)
        with left:
            st.subheader("Monthly Revenue")
            st.bar_chart(trend_df.set_index("month")["revenue"])
        with right:
            st.subheader("Monthly Orders")
            st.bar_chart(trend_df.set_index("month")["orders"])

        st.divider()

        # ── Region breakdown
        st.subheader("Revenue by Region × Product")
        pivot_df = query_df(
            """
            SELECT region, product, SUM(total_revenue) AS revenue
            FROM {tbl}
            WHERE year = ? AND region IN ({r}) AND product IN ({p})
            GROUP BY region, product
            """.format(
                tbl=T_MV_MONTHLY,
                r=",".join(["?"] * len(sel_region)),
                p=",".join(["?"] * len(sel_product)),
            ),
            [sel_year] + sel_region + sel_product,
        )
        st.dataframe(
            pivot_df.pivot(index="region", columns="product", values="revenue").fillna(0).style.format("${:,.0f}"),
            use_container_width=True,
        )

        # ── Rep leaderboard
        st.divider()
        st.subheader("🏆 Rep Leaderboard")
        sel_month = st.slider("Month", 1, 12, 1)
        lb_df = query_df(
            f"SELECT rank, sales_rep, orders, revenue FROM {T_MV_LEADER} WHERE year = ? AND month = ? ORDER BY rank",
            [sel_year, sel_month],
        )
        st.dataframe(lb_df, use_container_width=True, hide_index=True)

        # ── Submit a report for approval
        st.divider()
        st.subheader("Submit Month for Approval")
        sub_month = st.selectbox("Month to submit", list(range(1, 13)), format_func=lambda m: f"{sel_year}-{m:02d}", key="submit_month")
        if st.button("📤 Submit for Review", type="primary"):
            ref = f"{sel_year}-{sub_month:02d}"
            wf_id = submit(record_ref=ref, submitted_by=user)
            st.success(f"Submitted! Workflow ID: **{wf_id}**")


    # ════════════════════════════════════════════════════════════════════
    # PAGE 2 — REVIEW QUEUE
    # ════════════════════════════════════════════════════════════════════
    elif page == "📋 Review Queue":
        st.title(f"Review Queue — {role.title()}")
        st.caption(f"Showing items awaiting **{role}** approval.")

        queue_df = get_queue(role)

        if queue_df.empty:
            st.info("✅ Nothing in your queue right now.")
        else:
            st.write(f"**{len(queue_df)} item(s) pending your review**")

            for _, item in queue_df.iterrows():
                with st.expander(f"📄 {item['record_ref']}  —  submitted by {item['submitted_by']}", expanded=True):

                    # Step trail
                    trail = get_step_trail(item["workflow_id"])
                    step_cols = st.columns(len(trail))
                    icons = {"pending": "⏳", "approved": "✅", "rejected": "❌"}
                    badge_cls = {"pending": "badge-pending", "approved": "badge-approved", "rejected": "badge-rejected"}
                    for i, (_, s) in enumerate(trail.iterrows()):
                        cls = badge_cls[s["status"]]
                        step_cols[i].markdown(
                            f'<span class="step-badge {cls}">{icons[s["status"]]} {s["role"].title()}</span>',
                            unsafe_allow_html=True,
                        )
                        if s["reviewer"]:
                            step_cols[i].caption(s["reviewer"])

                    st.caption(f"Step {item['current_step']} of {item['total_steps']}  •  ID: {item['workflow_id']}")

                    # Quick data preview from materialized view
                    parts = item["record_ref"].split("-")  # e.g. "2024-03"
                    if len(parts) == 2:
                        preview = query_df(
                            f"""
                            SELECT region, product, SUM(order_count) AS orders, SUM(total_revenue) AS revenue
                            FROM {T_MV_MONTHLY} WHERE year = ? AND month = ?
                            GROUP BY region, product ORDER BY revenue DESC
                            """,
                            [int(parts[0]), int(parts[1])],
                        )
                        st.dataframe(preview, use_container_width=True, hide_index=True)

                    comments = st.text_area("Comments (optional)", key=f"c_{item['workflow_id']}")
                    a_col, r_col, _ = st.columns([1, 1, 4])

                    if a_col.button("✅ Approve", key=f"a_{item['workflow_id']}", type="primary"):
                        act(item["workflow_id"], user, "approved", comments)
                        st.success("Approved — queue refreshed.")
                        st.rerun()

                    if r_col.button("❌ Reject", key=f"r_{item['workflow_id']}"):
                        act(item["workflow_id"], user, "rejected", comments)
                        st.warning("Rejected.")
                        st.rerun()


    # ════════════════════════════════════════════════════════════════════
    # PAGE 3 — AUDIT LOG
    # ════════════════════════════════════════════════════════════════════
    elif page == "📜 Audit Log":
        st.title("Audit Log")
        st.caption("Full trail of every workflow action — sourced from Delta CDF.")

        audit_df = query_df(f"SELECT * FROM {T_WORKFLOW_AUDIT} ORDER BY created_at DESC LIMIT 200")

        if audit_df.empty:
            st.info("No workflow history yet.")
        else:
            status_filter = st.multiselect(
                "Filter by workflow status",
                ["in_review", "approved", "rejected"],
                default=["in_review", "approved", "rejected"],
            )
            filtered = audit_df[audit_df["workflow_status"].isin(status_filter)]
            st.dataframe(filtered, use_container_width=True, hide_index=True)
            st.caption(f"{len(filtered)} rows shown")


    # ════════════════════════════════════════════════════════════════════
    # PAGE 4 — PIPELINE LINEAGE VIEWER
    # ════════════════════════════════════════════════════════════════════
    elif page == "📁 Pipeline Lineage":
        st.title("📁 Pipeline Lineage Viewer")
        st.caption("Browse pipeline audit artifacts stored in Unity Catalog Volumes.")

        if st.button("🔄 Refresh listings"):
            st.session_state["_lineage_cache"] = {}

        # ── Reporting Period ─────────────────────────────────────────
        _MONTH_NAMES = [
            "January", "February", "March", "April", "May", "June",
            "July", "August", "September", "October", "November", "December",
        ]

        try:
            periods = _list_subdirs(VOLUME_BASE)
        except Exception as exc:
            st.error(f"Cannot list `{VOLUME_BASE}`: {exc}")
            st.stop()

        if not periods:
            st.warning(f"No folders found in `{VOLUME_BASE}`.")
            st.stop()

        # Parse YYYY-MM folder names into year → [month_num] map
        period_map: dict[str, list[int]] = {}
        for p in periods:
            parts = p.split("-")
            if len(parts) == 2:
                period_map.setdefault(parts[0], []).append(int(parts[1]))

        years = sorted(period_map.keys(), reverse=True)
        if not years:
            st.warning("No valid YYYY-MM folders found.")
            st.stop()

        # Default to prior month relative to (today + 7 days)
        from datetime import timedelta
        _ref_date = datetime.now(timezone.utc) + timedelta(days=7)
        if _ref_date.month == 1:
            _def_year, _def_month = str(_ref_date.year - 1), 12
        else:
            _def_year, _def_month = str(_ref_date.year), _ref_date.month - 1

        _def_year_idx = years.index(_def_year) if _def_year in years else 0

        st.markdown(
            '<div style="border:1px solid #444;border-radius:8px;padding:16px 20px;margin-bottom:16px;">'
            '<div style="color:#999;font-size:.8rem;font-variant:small-caps;margin-bottom:10px;">'
            "reporting period</div>",
            unsafe_allow_html=True,
        )
        col_lbl, col_mo, col_yr, col_btn = st.columns([2, 2, 1.5, 2])
        with col_lbl:
            st.markdown('<div style="padding-top:8px;">Month / Year</div>', unsafe_allow_html=True)
        with col_yr:
            sel_year = st.selectbox("Year", years, index=_def_year_idx, key="lineage_year", label_visibility="collapsed")
        with col_mo:
            avail_months = sorted(period_map.get(sel_year, []))
            month_opts = [_MONTH_NAMES[m - 1] for m in avail_months]
            _def_mo_idx = avail_months.index(_def_month) if sel_year == _def_year and _def_month in avail_months else 0
            sel_month_name = st.selectbox("Month", month_opts, index=_def_mo_idx, key="lineage_month", label_visibility="collapsed")
            sel_month_num = avail_months[month_opts.index(sel_month_name)]
        with col_btn:
            load_clicked = st.button("Load period", type="primary", key="lineage_load")
        st.markdown("</div>", unsafe_allow_html=True)

        sel_period = f"{sel_year}-{sel_month_num:02d}"

        if load_clicked:
            st.session_state["lineage_loaded_period"] = sel_period

        loaded_period = st.session_state.get("lineage_loaded_period")
        if not loaded_period:
            st.info("Select a reporting period and click **Load period** to continue.")
            st.stop()

        # ── Picker 2: Business Code ──────────────────────────────────
        biz_path = f"{VOLUME_BASE}/{loaded_period}"
        try:
            biz_codes = _list_subdirs(biz_path)
        except Exception as exc:
            st.error(f"Cannot list `{biz_path}`: {exc}")
            st.stop()

        if not biz_codes:
            st.warning(f"No subfolders found in `{biz_path}`.")
            st.stop()

        sel_biz = st.selectbox("🏢 Business Code", biz_codes, key="lineage_biz")

        # ── Picker 3: Job Run ID ─────────────────────────────────────
        run_path = f"{biz_path}/{sel_biz}"
        try:
            run_ids = _list_subdirs(run_path)
            run_ids.sort(reverse=True)
        except Exception as exc:
            st.error(f"Cannot list `{run_path}`: {exc}")
            st.stop()

        if not run_ids:
            st.warning(f"No subfolders found in `{run_path}`.")
            st.stop()

        sel_run = st.selectbox("🔧 Job Run ID", run_ids, key="lineage_run")

        # ── Display sales-check.json ─────────────────────────────────
        st.divider()
        file_path = f"{run_path}/{sel_run}/sales-check.json"
        st.subheader("`sales-check.json`")
        st.caption(f"Full path: `{file_path}`")

        try:
            data = _read_json_file(file_path)
            _render_lineage_html(data)
        except Exception as exc:
            st.error(f"Error reading JSON file: {exc}")


    # ════════════════════════════════════════════════════════════════════
    # PAGE 5 — SESSION DEBUG
    # ════════════════════════════════════════════════════════════════════
    elif page == "🔍 Session Debug":
        st.title("🔍 Session Debug")
        st.caption("Inspect environment, request headers, and decoded tokens for troubleshooting auth and role claims.")

        # ── helper to render a decoded JWT ────────────────────────────
        def _render_token(label: str, token: str) -> None:
            decoded = _decode_jwt(token)
            if "error" in decoded:
                st.warning(f"Could not decode {label}: {decoded['error']}")
                st.code(token, language=None)
                return

            payload = decoded["payload"]

            # Highlight roles / scopes at the top
            claim_keys = ("roles", "wids", "groups", "scp", "xms_cc")
            roles_claims = {k: payload[k] for k in claim_keys if k in payload}
            if roles_claims:
                st.markdown("**🛡️ Roles & Scopes**")
                st.json(roles_claims)

            col_h, col_p = st.columns(2)
            with col_h:
                st.markdown("**JWT Header**")
                st.json(decoded["header"])
            with col_p:
                st.markdown("**JWT Payload**")
                annotated = dict(payload)
                for ts_key in ("exp", "iat", "nbf"):
                    if ts_key in annotated:
                        annotated[f"_{ts_key}_utc"] = _format_epoch(annotated[ts_key])
                st.json(annotated)

            with st.expander("Raw token"):
                st.code(token, language=None)

        # ── Environment Variables ─────────────────────────────────────
        st.subheader("🌍 Environment Variables")
        _ENV_PREFIXES = ("DATABRICKS_", "CLIENT_", "AZURE_", "APP_", "TABLE_")
        _SENSITIVE_WORDS = ("SECRET", "PASSWORD")
        env_vars = {k: v for k, v in sorted(os.environ.items()) if k.startswith(_ENV_PREFIXES)}
        if env_vars:
            masked = {}
            for k, v in env_vars.items():
                if any(s in k.upper() for s in _SENSITIVE_WORDS):
                    masked[k] = v[:8] + "…" + v[-4:] if len(v) > 16 else "••••"
                else:
                    masked[k] = v
            st.dataframe(
                pd.DataFrame(list(masked.items()), columns=["Variable", "Value"]),
                use_container_width=True, hide_index=True,
            )
        else:
            st.info("No matching environment variables found.")

        st.divider()

        # ── Request Headers ───────────────────────────────────────────
        st.subheader("📨 Request Headers")
        try:
            raw_headers = dict(st.context.headers.items())
            if raw_headers:
                st.json(raw_headers)
            else:
                st.info("No request headers available.")
        except Exception as exc:
            st.warning(f"Could not read request headers: {exc}")

        st.divider()

        # ── Current User (SCIM) ──────────────────────────────────────
        st.subheader("👤 Current User (SCIM)")
        try:
            _user_token = get_user_token()
            from databricks.sdk import WorkspaceClient
            w = WorkspaceClient(token=_user_token, auth_type="pat")
            current_user = w.current_user.me()
            st.write(
                f"**User ID:** {current_user.id}  \n"
                f"**Username:** {current_user.user_name}  \n"
                f"**Display Name:** {current_user.display_name}  \n"
                f"**Active:** {current_user.active}  \n"
                f"**Groups:** {len(current_user.groups) if current_user.groups else 0} groups  \n"
                f"**Entitlements:** {len(current_user.entitlements) if current_user.entitlements else 0} entitlements"
            )

            # Show group membership with Entra/external origin
            # Try SP first, then OBO — both need workspace-admin to read SCIM Groups
            if current_user.groups:
                st.markdown("**👥 Group Membership**")
                _group_clients = [w]
                try:
                    sp_cfg = get_sp_config()
                    _group_clients.insert(0, WorkspaceClient(config=sp_cfg))
                except Exception:
                    pass

                def _resolve_group(group_id: str) -> dict | None:
                    for client in _group_clients:
                        try:
                            return client.groups.get(group_id)
                        except Exception:
                            continue
                    return None

                group_data = []
                resolve_failed = False
                for g in current_user.groups:
                    gd = _resolve_group(g.value)
                    if gd:
                        group_data.append({
                            "Group": gd.display_name,
                            "Origin": "Entra ID (external)" if gd.external_id else "Workspace (internal)",
                            "Entra Object ID": gd.external_id or "—",
                            "Databricks ID": gd.id,
                            "Membership": g.type or "direct",
                        })
                    else:
                        resolve_failed = True
                        group_data.append({
                            "Group": g.display or "—",
                            "Origin": "—",
                            "Entra Object ID": "—",
                            "Databricks ID": g.value or "—",
                            "Membership": g.type or "—",
                        })
                st.dataframe(pd.DataFrame(group_data), use_container_width=True, hide_index=True)
                if resolve_failed:
                    st.caption(
                        "⚠️ Origin could not be resolved — the app's SP needs "
                        "**workspace-admin** or an account-level role to read SCIM Groups."
                    )
            with st.expander("Full SCIM response"):
                st.json(current_user.as_dict())
        except AuthError as exc:
            st.warning(f"User token not available: {exc}")
        except Exception as exc:
            st.error(f"Error fetching current user: {exc}")

        st.divider()

        # ── User Token (OBO) ─────────────────────────────────────────
        st.subheader("🔑 User Token (OBO)")
        try:
            user_tkn = get_user_token()
            _render_token("User token", user_tkn)
        except AuthError as exc:
            st.warning(f"User token not available: {exc}")
        except Exception as exc:
            st.error(f"Error retrieving user token: {exc}")

        st.divider()

        # ── Service Principal Token ──────────────────────────────────
        st.subheader("🔐 Service Principal Token")
        try:
            sp_cfg = get_sp_config()
            sp_headers = sp_cfg.authenticate()
            sp_auth_val = sp_headers.get("Authorization", "")
            sp_tkn = sp_auth_val.removeprefix("Bearer ").strip() if sp_auth_val else ""
            if sp_tkn:
                _render_token("SP token", sp_tkn)
            else:
                st.info("SP authentication did not return a Bearer token.")
        except Exception as exc:
            st.error(f"Error retrieving SP token: {exc}")

        st.divider()

        # ── App SP Permissions (from app-resources.json.tpl) ─────────
        st.subheader("🛡️ App SP Permissions")
        st.caption("Permissions granted to the app's service principal via `meta/app-resources.json.tpl`.")

        _catalog = os.environ.get("DATABRICKS_CATALOG", "dev")
        _schema = os.environ.get("DATABRICKS_SCHEMA", "default")
        _silver_vol = os.environ.get("SILVER_VOLUME_NAME", "silver")
        _perm_rows = [
            {"Resource": "sql-warehouse", "Type": "SQL Warehouse", "Securable": "(warehouse ID)", "Permission": "CAN_USE"},
            {"Resource": "mv-monthly-summary", "Type": "TABLE", "Securable": f"{_catalog}.{_schema}.mv_monthly_summary", "Permission": "SELECT"},
            {"Resource": "mv-rep-leaderboard", "Type": "TABLE", "Securable": f"{_catalog}.{_schema}.mv_rep_leaderboard", "Permission": "SELECT"},
            {"Resource": "workflow-table", "Type": "TABLE", "Securable": f"{_catalog}.{_schema}.workflow", "Permission": "MODIFY"},
            {"Resource": "workflow-steps", "Type": "TABLE", "Securable": f"{_catalog}.{_schema}.workflow_steps", "Permission": "MODIFY"},
            {"Resource": "workflow-config", "Type": "TABLE", "Securable": f"{_catalog}.{_schema}.workflow_config", "Permission": "SELECT"},
            {"Resource": "workflow-audit", "Type": "TABLE", "Securable": f"{_catalog}.{_schema}.vw_workflow_audit", "Permission": "SELECT"},
            {"Resource": "silver-volume", "Type": "VOLUME", "Securable": f"{_catalog}.{_schema}.{_silver_vol}", "Permission": "WRITE_VOLUME"},
        ]
        st.dataframe(
            pd.DataFrame(_perm_rows),
            use_container_width=True,
            hide_index=True,
        )

        st.divider()

        # ── Volume Write / Read Test ─────────────────────────────────
        st.subheader("📝 Volume Write / Read Test")
        st.caption(f"Write a timestamped message to `{VOLUME_BASE}` then read it back to verify WRITE_VOLUME permission.")

        if st.button("Run write → read test", key="vol_test_btn"):
            _test_path = f"{VOLUME_BASE}/_debug_write_test.txt"
            _ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
            _msg = f"write-test ok | ts={_ts}"
            try:
                from databricks.sdk import WorkspaceClient
                _w = WorkspaceClient(config=get_sp_config())

                # Write
                import io
                _w.files.upload(_test_path, io.BytesIO(_msg.encode()), overwrite=True)
                st.success(f"✅ **Write** succeeded → `{_test_path}`")

                # Read back
                _resp = _w.files.download(_test_path)
                _read_back = _resp.contents.read().decode()
                if _read_back == _msg:
                    st.success(f"✅ **Read** matches — `{_read_back}`")
                else:
                    st.warning(f"⚠️ Read-back mismatch:\n  wrote: `{_msg}`\n  read:  `{_read_back}`")
            except Exception as exc:
                st.error(f"❌ Volume write/read test failed: {exc}")


if __name__ == '__main__':
    main()