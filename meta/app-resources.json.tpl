{
  "user_api_scopes": ["sql"],
  "resources": [
    {
      "name": "sql-warehouse",
      "sql_warehouse": {
        "id": "__WAREHOUSE_ID__",
        "permission": "CAN_USE"
      }
    },
    {
      "name": "mv-monthly-summary",
      "uc_securable": {
        "securable_full_name": "__CATALOG__.__SCHEMA__.mv_monthly_summary",
        "securable_type": "TABLE",
        "permission": "SELECT"
      }
    },
    {
      "name": "mv-rep-leaderboard",
      "uc_securable": {
        "securable_full_name": "__CATALOG__.__SCHEMA__.mv_rep_leaderboard",
        "securable_type": "TABLE",
        "permission": "SELECT"
      }
    },
    {
      "name": "workflow-table",
      "uc_securable": {
        "securable_full_name": "__CATALOG__.__SCHEMA__.workflow",
        "securable_type": "TABLE",
        "permission": "MODIFY"
      }
    },
    {
      "name": "workflow-steps",
      "uc_securable": {
        "securable_full_name": "__CATALOG__.__SCHEMA__.workflow_steps",
        "securable_type": "TABLE",
        "permission": "MODIFY"
      }
    },
    {
      "name": "workflow-config",
      "uc_securable": {
        "securable_full_name": "__CATALOG__.__SCHEMA__.workflow_config",
        "securable_type": "TABLE",
        "permission": "SELECT"
      }
    },
    {
      "name": "workflow-audit",
      "uc_securable": {
        "securable_full_name": "__CATALOG__.__SCHEMA__.vw_workflow_audit",
        "securable_type": "TABLE",
        "permission": "SELECT"
      }
    },
    {
      "name": "silver-volume",
      "uc_securable": {
        "securable_full_name": "__CATALOG__.__SCHEMA__.__SILVER_VOL__",
        "securable_type": "VOLUME",
        "permission": "READ_VOLUME"
      }
    }
  ]
}
