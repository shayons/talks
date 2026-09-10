# PostgreSQL 18 local demo

The conference app now uses a dedicated PostgreSQL 18 cluster on
`127.0.0.1:5433`, managed by [`scripts/postgres18.sh`](../scripts/postgres18.sh).
The app remains on `http://localhost:8017`. Existing global PostgreSQL services
are independent of this project.

```bash
./scripts/postgres18.sh start
./scripts/postgres18.sh status
./run-demo.sh
```

Stop the project database with `./scripts/postgres18.sh stop` after stopping
the app. Starting it again preserves the catalog and conversations. Its data
and log files live under `.local/`, which is ignored by Git.

The helper checks that its binaries and data directory are PostgreSQL 18. It
creates a `coffee` database only if absent and never applies `schema.sql` or
reseeds an existing catalog. First-time schema/data initialization is a separate
step in the README. Local demo credentials are `coffee` / `coffee`; this
project-owned role can install extensions. The server binds only to loopback.

`PG18_BIN` can select an existing PostgreSQL 18 installation. `COFFEE_PG18_PORT`
and `COFFEE_PG18_LOCALE` override the helper's defaults of 5433 and
`en_US.UTF-8`. When changing the port, also explicitly set the application's
`DATABASE_URL`. The launcher preserves shell overrides; Aurora keeps its own
endpoint and default port 5432.

## Moving an existing demo

Use a logical dump and restore into a separate PostgreSQL 18 database.
Do not point PostgreSQL 18 binaries at an older major version's data directory.
The PostgreSQL [major-version upgrade guidance](https://www.postgresql.org/docs/18/upgrading.html)
describes the available migration methods.

For this small demo, the migration sequence is:

1. Verify the source database, server ownership, destination version and
   installed `vector` / `pg_trgm` extensions. The destination must be empty.
2. Create the destination database with the source encoding, collation and
   character classification locale. Locale affects generated text-search
   documents; it is part of the retrieval behavior.
3. Stop the demo app's writes. Use PostgreSQL 18's `pg_dump --format=custom`
   and retain the archive.
4. Restore into the destination with `pg_restore --single-transaction
   --exit-on-error`. For the local demo role, ownership and ACLs can be omitted;
   production role/grant migration requires its own plan.
5. Compare all table contents and sequence positions, including stored vectors
   and regenerated full-text documents. Run ANALYZE, SQL tests, and browser
   checks against the new database before completing the switch.
6. Start the app with the new connection and verify `/api/search/status`.
   Keep the old database and backup available.

## Local migration record · September 10, 2026

The existing coffee demo was copied from PostgreSQL 17.10 on port 5432 to
PostgreSQL 18.4 on port 5433, with pgvector 0.8.2 and pg_trgm 1.6. The coffee
database retains its original `en_US.UTF-8` collation and character classification.
The old PostgreSQL 17 service and database were preserved.

All ten table-content hashes and sequence positions matched after restore:
catalog, embeddings, full-text documents, three customer profiles, historical
orders, sessions, messages, tool records, approvals, and the separate 12,000-row
index experiment. No catalog reseed or conversation reset was performed.

The dump and verification manifest are in ignored `.local/backups/`.
After the switch, new writes belong to PostgreSQL 18. Returning to the old
database is a historical rollback, not synchronization of subsequent activity;
preserve or migrate new data before switching back.
