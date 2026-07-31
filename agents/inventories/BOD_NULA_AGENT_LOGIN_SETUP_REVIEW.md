# Bod Nula Agent Login and Setup Review

Reviewed: 2026-07-31

Source repository: `https://github.com/mtravnicekarmex/bod-nula`

Reviewed commit: `eb201fbf01f98ba851a9af211d2ddde26f12319c`

Scope: first login, authorization verification, provider/model parameter
mapping, agent profiles, and permission setup. Other repository behavior is
outside this review.

## Observed design

### First login

The setup entry point loads and validates configuration before attempting
authentication. For Codex it first refreshes account state. If authentication
is required and no account is present, it starts the interactive ChatGPT
browser flow, waits for completion, then reads account state again. Absence of
an account after the flow is a hard failure.

For Claude the code first executes a structured authentication status check.
A valid `loggedIn: false` result is treated as an ordinary unauthenticated
state and starts interactive login. Empty or invalid status output is treated
as a verification failure instead of being silently interpreted as logged
out. A failed login exits with an error.

This makes initial authorization explicit, repeatable, and fail-closed.

### Parameter setup

The repository separates two configuration layers:

- environment mappings select concrete provider, model, and reasoning values;
- each agent profile selects symbolic `low`, `mid`, or `high` model and
  reasoning levels plus a permission profile.

Profiles are stored in agent-specific directories. They require a validated
`config.json` and non-empty `ROLE.md`; optional memory, state, shared-memory,
and principles inputs are controlled by explicit flags. Agent names,
directory identity, providers, levels, and permission profiles are validated
before a thread is created.

### Authorization

Permission profiles are explicit:

- `review` maps to read-only Codex access and read-oriented Claude tools;
- `edit` adds workspace writes;
- `full` adds unrestricted access including shell capability.

The selected provider, model, reasoning level, permission profile, role
instructions, and working directory are assembled centrally when the agent
thread is created. Tests cover the successful and failed login paths as well
as invalid or unresolved profile values.

## Patterns adopted for the supervision center

The supervision center should adopt these principles:

1. Provide a separate, explicit first-run setup command. Installation,
   authorization, offline self-test, and background execution must not be one
   opaque step.
2. Check current authorization status before starting an interactive flow.
3. Distinguish a valid unauthenticated result from a broken or unparseable
   status check.
4. Re-read and verify the authenticated identity after authorization. Fail
   closed if the expected identity or scope cannot be confirmed.
5. Make setup idempotent so rerunning it validates or repairs only the
   approved local setup.
6. Validate all non-secret configuration against a strict schema before
   network polling or model use.
7. Separate logical agent settings from concrete provider/model identifiers.
   This permits reviewed provider or model changes without altering the
   observer contract.
8. Keep role, rules, safe input contract, provider selection, and runtime
   state as distinct inputs with explicit versions.
9. Revalidate authorization on runtime startup rather than assuming that a
   successful installation remains valid forever.
10. Test logged-in, logged-out, rejected, expired, malformed-status, and
    interrupted-first-run paths.

## Required differences

The supervision center must not copy the reference design unchanged:

- An interactive personal ChatGPT or Claude login is acceptable only for an
  optional operator-owned interpretation provider, not as authentication to
  the monitored application and not as the unattended service identity.
- Access to the monitoring facade requires a dedicated non-human,
  least-privilege credential in addition to the Tailscale device identity.
- The production scheduled task must never depend on an interactive browser
  login at startup.
- Non-secret settings belong in a validated bundle-local configuration file.
  Live credentials belong in a separate ACL-restricted Windows location and
  must never be placed in the bundle, `.env`, reports, or agent state.
- The supervision runtime has one fixed `observe` permission profile. There
  is no configuration value that can elevate it to `edit`, `full`, shell,
  database, source-tree, or monitored-host write access.
- The runtime working directory is its installed bundle, not the
  `monitorovaci_platforma` project root. The complete repository is not
  transferred to the center.
- Deterministic incident state is independent of any conversational thread.
  Provider threads may be disposable and cannot be the system of record.

## Proposed setup phases

The eventual center setup should expose these reviewed phases:

1. `install` verifies the bundle manifest, creates isolated directories and
   Python environment, and runs offline tests.
2. `configure` writes only validated non-secret endpoint, polling, rule, and
   provider mappings.
3. `authorize-facade` provisions or verifies the dedicated monitoring
   credential and confirms only approved GET capabilities.
4. `authorize-interpreter` optionally performs a provider-specific
   interactive first login and verifies the resulting account. This phase is
   omitted when deterministic-only mode is selected.
5. `doctor` reports aggregate readiness for manifest, configuration,
   credentials, Tailscale path, endpoint contract, storage, and optional
   interpretation provider without printing secrets.
6. `run-test` starts foreground shadow mode. Scheduled-task registration is a
   later, separately approved phase.

No concrete installer or authorization code should be implemented until the
facade service-identity mechanism and the optional interpretation-provider
boundary are selected.
