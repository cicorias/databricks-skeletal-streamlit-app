"""
workflow.py — submit / approve / reject helpers.

Reads use OBO (query_df) so warehouse ACLs apply to the real user.
Writes use SP (execute_as_sp) since the SP owns the workflow tables;
the real user identity is recorded in row data for auditability.
"""
from __future__ import annotations

import uuid

try:
    from app.db import execute_as_sp, query_df, T_WORKFLOW, T_WORKFLOW_STEPS, T_WORKFLOW_CONFIG
except ImportError:
    from db import execute_as_sp, query_df, T_WORKFLOW, T_WORKFLOW_STEPS, T_WORKFLOW_CONFIG


def submit(record_ref: str, submitted_by: str, workflow_type: str = "monthly_report") -> str:
    steps_df   = query_df(
        f"SELECT step, role FROM {T_WORKFLOW_CONFIG} WHERE workflow_type = ? ORDER BY step",
        [workflow_type],
    )
    workflow_id = str(uuid.uuid4())[:8].upper()

    execute_as_sp(
        f"""
        INSERT INTO {T_WORKFLOW} (workflow_id, record_ref, current_step, total_steps,
                              status, submitted_by)
        VALUES (?, ?, 1, ?, 'in_review', ?)
        """,
        [workflow_id, record_ref, len(steps_df), submitted_by],
    )

    for _, row in steps_df.iterrows():
        execute_as_sp(
            f"INSERT INTO {T_WORKFLOW_STEPS} (workflow_id, step, role, status) VALUES (?, ?, ?, 'pending')",
            [workflow_id, int(row["step"]), row["role"]],
        )

    return workflow_id


def act(workflow_id: str, reviewer: str, decision: str, comments: str) -> None:
    """decision: 'approved' | 'rejected'"""
    wf = query_df(f"SELECT current_step, total_steps FROM {T_WORKFLOW} WHERE workflow_id = ?",
                  [workflow_id]).iloc[0]
    step = int(wf["current_step"])
    total = int(wf["total_steps"])

    execute_as_sp(
        f"""
        UPDATE {T_WORKFLOW_STEPS}
        SET status = ?, reviewer = ?, comments = ?, acted_at = current_timestamp()
        WHERE workflow_id = ? AND step = ?
        """,
        [decision, reviewer, comments, workflow_id, step],
    )

    if decision == "rejected":
        execute_as_sp(
            f"UPDATE {T_WORKFLOW} SET status = 'rejected', updated_at = current_timestamp() WHERE workflow_id = ?",
            [workflow_id],
        )
    else:
        next_step = step + 1
        if next_step > total:
            execute_as_sp(
                f"UPDATE {T_WORKFLOW} SET status = 'approved', current_step = ?, updated_at = current_timestamp() WHERE workflow_id = ?",
                [next_step, workflow_id],
            )
        else:
            execute_as_sp(
                f"UPDATE {T_WORKFLOW} SET current_step = ?, updated_at = current_timestamp() WHERE workflow_id = ?",
                [next_step, workflow_id],
            )


def get_queue(role: str) -> "pd.DataFrame":
    return query_df(
        f"""
        SELECT w.workflow_id, w.record_ref, w.current_step, w.total_steps,
               w.submitted_by, w.created_at
        FROM {T_WORKFLOW} w
        JOIN {T_WORKFLOW_STEPS} ws
          ON w.workflow_id = ws.workflow_id AND w.current_step = ws.step
        WHERE ws.role = ? AND ws.status = 'pending' AND w.status = 'in_review'
        ORDER BY w.created_at ASC
        """,
        [role],
    )


def get_step_trail(workflow_id: str) -> "pd.DataFrame":
    return query_df(
        f"SELECT step, role, status, reviewer, comments, acted_at FROM {T_WORKFLOW_STEPS} WHERE workflow_id = ? ORDER BY step",
        [workflow_id],
    )
