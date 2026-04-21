"""
app.py  —  Streamlit POC (Databricks Apps with OBO auth)
Run inside a Databricks App:
  streamlit run app.py
Env vars required:
  On Databricks Apps: auto-injected (DATABRICKS_HOST, CLIENT_ID/SECRET)
  Locally: DATABRICKS_HOST, DATABRICKS_TOKEN, DATABRICKS_HTTP_PATH,
           DATABRICKS_CATALOG, DATABRICKS_SCHEMA  (via .env / 'make env')
"""
import streamlit as st
import pandas as pd
try:
    from app.auth import AuthError, get_user_email
    from app.db import query_df, T_MV_MONTHLY, T_MV_LEADER, T_WORKFLOW_AUDIT
    from app.workflow import submit, act, get_queue, get_step_trail
except ImportError:
    from auth import AuthError, get_user_email
    from db import query_df, T_MV_MONTHLY, T_MV_LEADER, T_WORKFLOW_AUDIT
    from workflow import submit, act, get_queue, get_step_trail

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
    role  = st.selectbox("Your role", ["manager", "finance", "director", "submitter"])
    st.divider()
    page  = st.radio("Navigate", ["📈 Dashboard", "📋 Review Queue", "📜 Audit Log"])


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

    sel_year    = col1.selectbox("Year",    years["year"].tolist())
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
    sub_month = st.selectbox("Month to submit", list(range(1, 13)), format_func=lambda m: f"{sel_year}-{m:02d}")
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
