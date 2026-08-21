# Monitoring orchestrator snapshot

Generated at: 2026-08-18T06:00:18.949124Z
Contract version: 1
Mode: file_only
Status: degraded

## Agent rollup
- external_health: status=ok, freshness=fresh, gaps=1
- database_availability: status=ok, freshness=fresh, gaps=0
- scheduler_metrics: status=degraded, freshness=fresh, gaps=0

## Correlations
- scheduler_historical_error_states_no_recent_failures: status=degraded, agents=scheduler_metrics

## Safety boundary
- File-only/shadow-only orchestrator output; legacy alerts remain authoritative.
- The orchestrator consumes supplied sanitized snapshots and does not poll endpoints, read .env, send email, call interpretation providers, mutate state, or control processes.
- No alert may be replaced, disabled, rerouted, downgraded, or acknowledged from this output without separate approval.
