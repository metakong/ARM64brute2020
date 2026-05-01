# SOP_02_PocketBase_Bus

## Rule
Agents are forbidden from executing `DROP TABLE` or `DELETE` commands via SQLite. Only `INSERT` or `UPDATE` with an `is_archived` boolean flag.

## Implementation Details
- Use soft-deletion patterns.
- Ensure all tables have an `is_archived` column (Boolean).
- Update `is_archived` to `true` instead of deleting rows.
- Filter queries to exclude archived records by default.
