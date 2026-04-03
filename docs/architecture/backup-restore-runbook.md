# Backup and Restore Runbook

## Scope

- PostgreSQL primary data
- Uploaded files (`/data/uploads` for local backend; object storage for S3 backend)

## Ownership

- Primary owner: Platform/on-call engineer
- Backup cadence owner: Infrastructure
- Restore drill owner: Release manager

## Backup plan

1. Database
   - Nightly `pg_dump` backup.
   - Weekly full snapshot retention.
2. File storage
   - Local: snapshot `data/` volume.
   - S3: enable bucket versioning + lifecycle retention.

## Restore drill checklist

1. Restore database to clean environment.
2. Restore file storage snapshot/version.
3. Run API and worker.
4. Validate:
   - `GET /health` is healthy,
   - existing resources load,
   - search returns expected chunks.
5. Record whether this was a drill or an incident rollback invoked from
   [`production-runbook.md`](production-runbook.md) rollback flow.

## Restore drill evidence (required)

Record every drill with the following minimum evidence:

- Date/time (UTC)
- Operator
- Backup source identifier (db dump id, storage snapshot/version id)
- Restore duration (start/end)
- Validation command outputs (`/health`, sample resource fetch, sample search query)
- Outcome (`pass`/`fail`) and follow-up actions

Template:

```text
Drill date (UTC):
Operator:
DB backup id:
Storage snapshot/version:
Restore started:
Restore completed:
Validation evidence:
Outcome:
Follow-up:
```

## RPO / RTO targets (initial)

- RPO: 24 hours
- RTO: 4 hours
