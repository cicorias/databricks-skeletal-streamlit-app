{
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
    }
  ]
}
