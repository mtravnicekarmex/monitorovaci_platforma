# Backlog

## SmartFuelPass Excel import replacement

- Status: explicitly deferred until the monitoring-agent roadmap has advanced
  beyond the current unfinished work; do not modify the existing interactive
  workflow meanwhile.
- Future direction: rename dashboard page `Přihlášení SmartFuelPass` to
  `Import`, let an administrator select an Excel file, parse the supported
  workbook contract, and create/update database records through the
  authenticated FastAPI boundary.
- Preserve the database-backed weekly report. Do not retry or bypass the
  paused Cloudflare/browser workflow while this item is deferred.
- Before implementation, define the accepted workbook schema, parser
  validation/error contract, idempotent database identity, preview/confirmation
  boundary, aggregate audit result, and rollback/reconciliation checks.
