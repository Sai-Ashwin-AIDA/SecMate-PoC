# Local Document Agent → SecMate: Phase 2 implementation blueprint

**Status:** planning only; implementation has not been performed.
**Reviewed checkpoint:** `2aa9563`, branch `Sai`, clean single worktree.
**Authority:** the user's Phase 2 planning assignment and subsequent decisions.
**Builder detail:** §§8.1–8.10 provide implementation contracts and work packets;
§9.1 provides a concrete test inventory. Read these together with the scope and
stop rules, not as permission to implement later phases.

> Implement Phase 2 only when the user separately assigns this document to a
> builder. Deliver the results record and STOP for human acceptance. This document
> does not implement a worker gateway or authorize continuing into another phase.

## 1. Authority, acceptance and builder instructions

The user has now explicitly accepted Phase 1 and reported these manual results:
missing/wrong bearer tokens returned **401**; authenticated metadata returned the
three expected capabilities with `readiness.ready: true`; Ctrl+C returned
immediately to PowerShell. These are **human-reported observations**, not a new
builder-run demonstration. The exact metadata contract-version value was not
separately pasted; verify it explicitly in the Phase 2 connection check.

The Phase 1 results and BUILD_STATUS still contain their historical pending
acceptance/manual-check dispositions. Preserve them; this document records the
subsequent conversation without rewriting earlier evidence. The recorded
190-pass/one-skip gate remains historical until actually rerun.

Builder requirements:

1. Confirm root, branch, worktrees, HEAD and initial changes. Preserve concurrent
   work; never switch/reset branches or stage/commit/push. Confirm the intended
   integration branch before editing runtime code; do not modify frozen Ashwin.
2. Read this document, Phase 1 results/integration blueprint, and the focused
   source map below. Recheck only boundaries that changed since this checkpoint.
3. Ask the user about **every unresolved doubt, including minor ambiguities**,
   before choosing an interpretation. State the uncertainty and narrow
   recommendation; batch independent questions. Do not re-ask settled decisions.
4. Stop on material conflicts with installed APIs, storage, existing readers or
   Phase 1. Do not silently broaden contracts, change adapter semantics, research
   frameworks broadly, redesign authentication, or introduce dependencies.
5. Use isolated offline tests first. Record actual commands, exits, failures,
   skips and limitations; no pre-filled passing results.
6. The user has allowed live calls if testing requires them, without another
   permission question. **No model call is necessary for Phase 2**, whose connector
   only retrieves metadata. This allowance does not expand scope into attacks,
   Judge calls, worker execution, live demonstrations or remote deployment.
   Ask about genuinely unresolved safety/content/destination choices, not about
   repeating an already granted testing permission.

## 2. Goal and confirmed decisions

Deliver a bounded **SecMate API-owned connected-target registry** and minimal
onboarding page. The Targets page gains **Onboard target**, opening a short page
with target name, endpoint URL, distinct adapter connection token and optional
description. Save first; then explicitly check the saved connection.

Confirmed:

- Use `secmate-agent-http-v1` as implemented, initially for the document agent.
  No arbitrary API discovery, tool-schema entry or synthetic imitation.
- Fetch capabilities and configured identity through authenticated, **non-inference**
  metadata. Never request provider keys, roots, model overrides or internal IDs.
- Keep both synthetic targets and their existing projections/readers intact:
  `synthetic-socmate-tier1` and `secmate.synthetic-chatmate.fresh.v1`.
- Browser clients never retrieve a stored token. Clear the token input after
  successful save; use server-side credentials for explicit checks.
- SecMate API remains loopback-only under the user's **Windows account**.
  Reuse `_require_local_confirmed_request`: exact trusted-Origin validation and
  `X-SecMate-Local-Run: confirmed`. CORS/preview login are not backend authentication.
  This does not protect against malicious local processes under that account.
- Protect tokens using **user-scoped Windows DPAPI**, encrypted blobs in the
  API-owned SQLite registry. No plaintext token column, custom cryptography or
  decryption key beside the database. Ask before changing mechanisms/dependencies.
- Targets may have configurable HTTPS URLs and optional reverse-proxy base paths.
  Valid TLS and explicit server-owned destination approval are mandatory before
  contacting an endpoint or sending a token. Plain HTTP is allowed only for
  explicitly approved same-machine development destinations.
- Initially approved development base URL: **`http://127.0.0.1:7310`**.
  No remote host/deployment has been chosen. Remote hosting remains unverified.
  An unapproved URL may be saved but must not be contacted.
- Save success, compatible authenticated connectivity, endpoint-reported inference
  readiness and live usability are separate states. **No connected registration
  is assessment-ready in Phase 2**, even if metadata says inference-ready.

The separately running adapter keeps its own provider credentials and Harbor-only
input/create-only output. Its listener, retry policy, session/run ownership,
deduplication, cancellation, retention and evidence semantics remain unchanged.

## 3. Focused source map and verified starting point

| Path | Reuse / exact relevance |
|---|---|
| `Documents/LOCAL_DOCUMENT_AGENT_SECMATE_PHASE1_RESULTS.md` | Actual offline gate, limitations, observed filesystem evidence and historical handover. |
| `Documents/LOCAL_DOCUMENT_AGENT_SECMATE_INTEGRATION_BLUEPRINT.md` | Fixed adapter contract and exclusions. |
| `local-document-agent/src/local_document_agent/http_contracts.py` | `Metadata`, `Identity`, `Readiness`, `Capability`, `Limits`, contract constant; mirror this wire boundary, not the assistant implementation. |
| `.../http_adapter.py`, `http_config.py`, `http_cli.py` | Authenticated metadata has no provider construction/body reads; current listener and fixed roots. Read-only in Phase 2. |
| `apps/api/src/secmate_api/target_projection.py` | Strict `target-projection-v1` models hardcode the two synthetic identities and `selectable: true`; do not stretch these models to pretend connected targets are executable. |
| `apps/api/src/secmate_api/main.py` | Existing `/api/v1/targets` GETs, local confirmation/origin guard, CORS, error conventions and idempotency middleware. |
| `apps/api/src/secmate_api/config.py` | `DATA_ROOT`/`SECMATE_API_DATA_ROOT`; imports currently load API-local dotenv. Do not load real dotenv during tests. |
| `apps/api/src/secmate_api/run_store.py` | SQLite transaction/connection/rollback patterns. Reuse patterns, not run tables or evidence migrations. |
| `apps/api/src/secmate_api/contracts.py` | Existing assessment target admission; do not broaden it for registry IDs. |
| `apps/api/tests/test_target_projection.py`, `tests/conftest.py` | Exact two-target/read-only tests; collection-time storage isolation. |
| `apps/web/src/ModulePages.tsx` | Actual `TargetsPage`, cards, synthetic detail dialog, search/query-ID behavior; old unused `OnboardTargetDialog` uses browser-local lifecycle storage and is NOT this onboarding flow. |
| `apps/web/src/targetProjectionService.ts` | Keep existing synthetic GET client/types unchanged; compose display with a separate registry client. |
| `apps/web/src/App.tsx` | Lazy routes, authenticated shell, login return routing and PageBoundary patterns. |
| `apps/web/src/platformService.ts` | Historical browser-local platform state; never store new tokens or registry authority here. |
| `apps/web/src/LoginPage.tsx`, `ModulePages.tsx` forms | Existing labels, submit/loading/error patterns; no new form framework. |
| `apps/web/src/DeepTeamAssessmentPanel.tsx` | Catalog-based synthetic assessment selection; leave execution/selection unchanged. |
| `apps/web/src/TargetsPage.test.tsx`, `targetProjectionService.test.ts`, `App.routeLoading.test.tsx`, `ModulePages.test.tsx` | Synthetic rendering, legacy detail compatibility, focus/deep links, routing and regression coverage. |
| `apps/web/src/styles.css`, `testSetup.ts`, `package.json` | Reuse layout/accessibility/test patterns and installed tooling. |
| `apps/api/pyproject.toml`, `apps/web/package.json` and existing locks | API already has httpx/FastAPI; stdlib sqlite3/ctypes suffice for registry/DPAPI. Preserve dependencies. |
| `Documents/TRD-4.md`, “Execution and tests” | Required sandboxed API import/test driver; avoid live data/controller/job recovery. |

No code/tests were executed for this planning assignment. Only this blueprint is
created. There is no existing approved target-secret vault in the inspected API.

## 4. Exact scope and exclusions

Allowed implementation paths:

- New small API modules: `connected_target_contracts.py`,
  `connected_target_store.py`, `connection_secrets.py`, `target_connection.py`,
  `connected_targets.py`; integrate their routes narrowly in `main.py`.
- Corresponding API tests and a small sandboxed test driver if needed.
- New frontend `connectedTargetService.ts`, `TargetOnboardingPage.tsx`,
  `ConnectedTargetPage.tsx`, tests; narrowly update Targets composition, App routing
  and existing styles. Equivalent small factoring is fine; ask if uncertain.
- API example configuration/startup documentation for destination approval,
  Windows account/DPAPI operation, and necessary focused test instructions.
- Builder-created `Documents/LOCAL_DOCUMENT_AGENT_SECMATE_PHASE2_RESULTS.md`.

Do not implement worker gateways, invocation/poll/cancel forwarding, attacks,
Judge/Critic integration, report/evidence changes, assessment selection for
connected targets, scheduler/jobs, catalogue changes, live demonstrations,
remote deployment/reverse proxies, domain purchase or Phase 3 instructions.
Do not alter the adapter, its dependencies, CLI, prompt/tools/provider behavior,
runtime data or listener. No deletion/export endpoint, automatic refresh/check,
automatic token rotation, browser persistence of tokens or full registry CRUD.
Preserve old browser-local readers/dialogs and saved evidence; do not migrate
them into this registry or invoke history reset/cleanup.

## 5. Storage and credential lifecycle

Use a separate versioned database beneath API `DATA_ROOT`, for example
`connected-targets/registry.sqlite3`, not `control.sqlite3` or the job ledger.
Use stdlib SQLite transactions, parameterized SQL, rollback and bounded reads;
fail closed on unsupported/corrupt schemas. No database creation on import.
Max **32 registrations**, unique canonical endpoint URL; capacity returns 503,
duplicate endpoint returns 409 without replacing the original credential.
Do not evict records. Missing/corrupt storage is not an empty successful registry.
Normal list/get operations are read-only; an absent, never-created registry may
return an empty list without initializing a database.

Separate public registration/check rows from private credential rows:

- Registration: generated `connected-<uuid>` ID, name, description, canonical base
  URL, UTC created/updated times, connection revision starting at 1.
- Private row: target ID, storage format/version, user-scoped DPAPI ciphertext
  BLOB. Never persist plaintext, token hashes/fingerprints or raw request bodies.
- Last check: revision, approval-policy fingerprint, checked-at time, outcome/
  safe code and bounded validated public metadata snapshot. Keep only latest;
  this is configuration status, not assessment evidence or immutable attestation.

DPAPI requirements:

1. Use Windows `CryptProtectData`/`CryptUnprotectData` with **current-user scope**,
   UI forbidden, and standard ctypes declarations/Windows allocation cleanup.
   Do not use machine scope or invent encryption/optional-entropy key storage.
2. Encrypt before committing a registration/credential replacement. Public and
   private rows commit atomically; encryption/storage failure leaves no partial
   successful registration. Use SecretStr/equivalent repr suppression in memory.
3. Decrypt only for an approved explicit connection check, into bounded transient
   API memory. Never pass credentials through argv, subprocesses, jobs, environment
   variables, URL parameters, browser storage or run/evidence payloads.
4. Supply the recovered value only in the outbound `Authorization: Bearer ...`
   header. Release references promptly; do not claim guaranteed Python memory
   zeroization. No token logging, even at debug level.
5. On DPAPI/key/account failure, do not contact the target. Report
   `CREDENTIAL_UNAVAILABLE`, retain registration/ciphertext, invalidate connectivity
   and require deliberate credential replacement. Never fall back to plaintext,
   silently clear the record, rotate secrets or mark it recoverable.
6. Same-account restarts should recover credentials; another Windows account or
   machine may not. Normal registry exports do not exist in Phase 2. Copying the
   database alone is not a portable secret backup; account/profile/key recovery
   is OS-managed and may require token re-entry. Preserve encrypted backups, WAL/
   SHM and database access permissions as sensitive operator-owned material.
7. Confirm the actual API process uses the user's intended Windows account before
   manual verification; do not print account secrets/SIDs or change service
   identity/ACLs automatically. Require an operator-controlled local directory
   with appropriate permissions; encryption is not protection from that account.
8. Non-Windows production use is unsupported for this selected secret mechanism.
   Public registry reads can still work; credential writes/checks fail safely.
   Mocking DPAPI in portable tests is not OS-backed protection evidence.

Do not add cryptography/keyring packages or choose Credential Manager instead
without asking the user. No decryption key is supplied through frontend or config.

## 6. Destination policy and metadata-only connector

### Server-owned approval

Add explicit API-server configuration `SECMATE_TARGET_ALLOWED_DESTINATIONS`
containing a JSON array of approved canonical **base URLs**, not arbitrary regex
or wildcard hosts. Blank defaults to deny all. Example, containing no secret:

```dotenv
SECMATE_TARGET_ALLOWED_DESTINATIONS=["http://127.0.0.1:7310"]
```

Treat this as an explicit operator-managed development entry, not a hardcoded
localhost-only connector. An approval matches the entire scheme, hostname/IP,
effective port and base path. Configuration changes take effect on controlled
API restart; do not hot-reload around active jobs. Browser inputs/headers may
never approve destinations or override networking policy.

HTTPS supports approved DNS names or IPs, valid certificate/hostname checks and
optional base paths. HTTP requires an exact server-approved same-machine
loopback destination; never permit remote plaintext HTTP. Reject userinfo, query,
fragment, protocol-relative URLs, malformed ports/hosts, control characters,
backslashes, ambiguous/encoded traversal or path components that alter routing.
Normalize host/scheme/default ports and a trailing slash consistently before
uniqueness/approval comparison; preserve case-sensitive base-path meaning.
Never infer an endpoint from adapter-provided links.

No remote host is approved yet. Before a remote check, the operator must confirm
the exact destination and deployment arrangement and add its server-owned approval.
Do not buy/deploy/contact anything or silently permit a private network, cloud
metadata service, local management port, wildcard DNS or alternate host.
For DNS endpoints, prevent resolution/rebinding from bypassing the approved
destination: validate resolved addresses and bind the actual connection to the
validated destination while preserving TLS hostname/SNI verification. Ask and
stop if this cannot be achieved with the existing HTTP stack; do not disable TLS
or silently replace the URL with an IP. Host approval alone is not a full SSRF
sandbox; document the trusted-operator boundary and tested DNS policy.

### Exact outbound operation

- Validate stored URL and current approval **before decrypting** or opening a
  socket. An unapproved saved registration returns `DESTINATION_NOT_APPROVED`,
  with no DNS/network/token transmission.
- One authenticated **GET** to `<base-path>/v1/metadata`; root base URL therefore
  maps to `/v1/metadata`. Append without dropping the proxy base path.
- Use existing httpx with `trust_env=False`, `follow_redirects=False`, TLS
  verification enabled, no cookies and no automatic retries. No shell/subprocess.
- Bound the entire operation to **5 seconds**, streamed decoded response to
  **32 KiB**, and permit only **one active check per API instance**; another gets
  409 `CONNECTION_CHECK_BUSY`, not a queued job. Always close response/client.
- Check admission/URL/credential recovery do not invoke providers, tools or workers.
  No POST to adapter `/v1/runs`, polling or cancellation endpoints exists here.
- Validate JSON/types/unknown fields against the actual Phase 1 Metadata shape
  in independent API wire models; do not import the Python 3.12 assistant or load
  its `.env` into SecMate. Enforce bounded strings/arrays, canonical instance UUID,
  exact `secmate-agent-http-v1`, `agent_kind: local-document-agent`, exact three
  unique capability names, fresh-session/single-slot limits and valid readiness.
  Stop on a material schema mismatch rather than loosening Phase 1.
- Preserve endpoint-reported configured/observed distinctions and coverage gaps.
  Do not hardcode all capabilities as simulated/proposals or treat real creation
  as approval-gated. Render metadata as untrusted text, never HTML.
- Persist/project only validated public fields. Reject a response containing the
  connection token in any projected text; errors must not echo raw upstream
  bodies, headers, exceptions, certificate details or submitted secrets.
- Metadata from an authenticated endpoint is self-reported, not attestation,
  independent certification, live execution or security-test success.

## 7. Fixed API contract and UX

Keep existing synthetic `/api/v1/targets` and `/targets/{id}` responses/models
unchanged. Add a separate namespace **`/api/v1/connected-targets`** with strict
Pydantic request/public-response models (`extra="forbid"`, no type coercion).
Use existing detail/error conventions with an additional safe stable `code`.
No body/validation error may include rejected input or token content.

| Operation | Contract |
|---|---|
| `GET /connected-targets` | 200 bounded public list, deterministic created-time/ID order; no network/decryption. |
| `POST /connected-targets` | Body `{name, endpoint_url, connection_token, description?}`; 201 public detail only after atomic encrypted save. Does not check connection. |
| `GET /connected-targets/{id}` | 200 public detail or safe 404; no network/decryption. |
| `POST /connected-targets/{id}/connection-check` | No body; local guard required; one bounded metadata check using saved credentials/current approval. 200 public detail for settled connection success or failure, never a fabricated registration error. |
| `POST /connected-targets/{id}/connection` | Body `{expected_connection_revision, endpoint_url?, connection_token?}`, at least one actual connection field; local guard required. Atomic replacement, increment revision, invalidate previous check/metadata/readiness. 200 public detail. |

Bounds: name 1–100 nonblank characters, optional description at most 1000,
URL at most 2048, connection token 1–4096 ASCII characters without whitespace,
distinct in meaning from a provider key. The API cannot prove an opaque token
differs from an unseen provider key; never fetch that key to compare it.
Trim name/description for display only; do not silently rewrite token bytes.
Bound credential-bearing inbound bodies to **16 KiB** before JSON parsing.
Missing fields, malformed JSON, extras/types/invalid values → safe 422;
excess body → 413; guard failure → 403; unknown ID → 404; duplicate URL/revision
conflict → 409; capacity/storage/DPAPI write unavailability → 503.

Check failure codes distinguish at least `DESTINATION_NOT_APPROVED`,
`CREDENTIAL_UNAVAILABLE`, `AUTHENTICATION_FAILED`, `CONNECTION_UNREACHABLE`,
`CONNECTION_TIMEOUT`, `TLS_FAILED`, `REDIRECT_REJECTED`, `METADATA_TOO_LARGE`,
`CONTRACT_INCOMPATIBLE`, `INVALID_METADATA`, `UPSTREAM_HTTP_ERROR`.
No HTTP 401 from an agent is misrepresented as a SecMate-login failure.
Connectivity failure must not delete registration or overwrite a credential.

Do not add these secret-bearing routes to the existing job RequestCache/
idempotency action machinery, which is for run evidence. Unique endpoint
constraints prevent duplicate creation without storing request bodies/tokens.
Concurrent checks/edits use connection-revision comparison: stale results cannot
overwrite a newer connection. If the revision changes during a check, discard its
result and return 409 `CONNECTION_CHANGED`; do not retry. Abort before sending if
a change is observed before the outbound operation.

### Public projection

Use `schema_version: "connected-target-registration-v1"`, generated ID/name/
description/base URL/times, `kind: "CONNECTED_AGENT"`, `synthetic: false`,
`selectable: false`, and `assessment_ready: false`.
Include connection revision; `credential_state: "STORED" | "UNAVAILABLE"` (STORED
means encrypted material exists, not that recovery was demonstrated); current
destination approval; connection status `NOT_CHECKED | CONNECTED | FAILED`,
last-check time, safe failure code, compatible contract version and bounded
validated metadata or null. Never return token/ciphertext/private storage paths.

Expose configured inference readiness as `true | false | null` with safe reasons;
null when unchecked/invalidated/failed. Live usability is always
`NOT_VERIFIED_IN_PHASE2`; execution support is `WORKER_GATEWAY_NOT_IMPLEMENTED`.
Last successful metadata can be retained internally after a failed check, but
must not be presented as current connectivity/readiness. Invalidated policy/
connection revision makes current state NOT_CHECKED with no current metadata.
Instance IDs are metadata observations, not stable SecMate registration IDs.
An adapter restart never triggers resubmission or execution.

### Minimal UI

1. Add **Onboard target** in the existing Targets toolbar → `/targets/onboard`,
   using the existing authenticated shell, lazy route and page-error boundary.
2. Four fields only: **Target name**, **Endpoint URL**, **Connection token**
   (`type=password`, no reveal/default/token autofill persistence), optional
   **Description**. Explain that this is not the provider key and that saving
   does not send a model request. No schemas, IDs, paths or model/provider inputs.
3. **Save registration** disables duplicate submits; validation/storage failures
   are actionable but sanitized. Clear token after success and on unmount; never
   put it in local/session storage, URL/history state, analytics or notifications.
   On save failure do not automatically retry; let the user deliberately resubmit.
4. On successful save navigate to `/targets/connected/{id}`. Show **Not checked**,
   **Connected**, or **Connection failed**, last check time, destination approval,
   and an explicit **Check connection** button. No automatic check on save, mount,
   navigation, polling, list/get or page refresh.
5. Detail also separates “Configured inference readiness: Yes / No / Unknown”
   from “Live execution: Not verified” and “Assessments unavailable: worker gateway
   not implemented.” “Connected” means a compatible authenticated metadata check
   succeeded at the recorded time, not continuous availability.
6. Display reported capabilities/configured identity only after validation. Say
   “Configured model,” not “Observed model”; show real create-only local file and
   unsent-draft effects accurately. No “synthetic test system” chip for this agent.
7. Provide a small **Change connection** flow using the same endpoint/token
   controls and revision contract; blank token means retain existing encrypted
   credential, never an empty replacement. A deliberately entered replacement
   is required when recovery fails. Any submitted connection change invalidates
   prior connectivity, even when the endpoint text happens to be unchanged.
8. Compose both API lists in the Targets display with one search/grid and a
   discriminated view model; keep synthetic cards/detail/query links unchanged.
   A registry failure must not hide working synthetic targets; show its separate
   error/retry state without pretending there are no synthetic targets.
   Connected cards navigate to their detail route, not the synthetic-only dialog.
9. Preserve existing deep links, focus/keyboard behavior, mobile layout, legacy
   projection compatibility and old browser-local data/readers. Do not revive
   the old browser-only onboarding dialog or remove it as unrelated cleanup.
10. Do not insert connected targets into DeepTeam catalog/selectors, start controls
    or manual assessment flows. UI absence is not the only gate: existing API
    execution admission must continue rejecting connected registration IDs.

## 8. Ordered implementation steps

1. **Preflight:** confirm assignment/branch/acceptance evidence, preserve initial
   changes, inspect mapped boundaries. Confirm Windows process account and current
   allowed destinations without reading/printing credentials or saved evidence.
2. **Contracts/storage:** implement independent public/private models, bounded
   separate registry and user-scoped DPAPI boundary with injectable test doubles.
   Verify no plaintext persistence/serialization or import-time writes.
3. **Connector/policy:** implement canonical base URL approval, strict bounded
   metadata client, no redirects/proxies/retries/inference, TLS and DNS policy.
   If actual destination/account policy differs, ask before proceeding.
4. **API:** add registry routes/local guard, safe errors, atomic replacement/
   invalidation and revision-safe check settlement. Keep historical projections
   and all execution/job/evidence contracts unchanged.
5. **UI:** wire button, page/routes, separate client, saved detail/check/change
   states and combined display using existing patterns. Never broaden selection.
6. **Offline gate:** run focused tests below, then sandboxed API suite and frontend
   suite/build. Regress Phase 1 unchanged if its environment is available; retain
   honest skips. Ask about missing tools/conflicts rather than reinstalling pins.
7. **Manual verification/results:** perform bounded approved local metadata-only
   checks as needed; record exactly who observed what. No model call is needed.
   Write results, hand back checklist and STOP.

### 8.1 Dependency direction and module responsibilities

Implement these as small independently testable boundaries. Names below are
the planned names, not proof those files already exist. Do not create a generic
integration/plugin framework, dependency-injection container or new package.

| Module | Owns | Must not own |
|---|---|---|
| `connected_target_contracts.py` | Strict create/replace/public DTOs, independently declared metadata wire DTOs, bounded safe errors and status enums | Environment loading, token decryption, network access, worker imports |
| `connection_secrets.py` | A small `SecretProtector` interface and its user-scoped Windows DPAPI implementation | SQL, HTTP, browser state, application-wide logging configuration |
| `connected_target_store.py` | Versioned SQLite creation/read/write, uniqueness/capacity, private credential lookup, connection revision and check persistence | DPAPI native calls, endpoint HTTP requests, run/evidence database migrations |
| `target_connection.py` | URL normalization, approval policy, resolved-destination admission, bounded HTTPX client, metadata validation, check outcome | Target registration writes, attack generation, provider SDKs, browser behavior |
| `connected_targets.py` | Guarded route orchestration, bounded request parsing, service-level atomicity, safe public projection and revision-safe check settlement | Secret-bearing global job receipts, assessment admission changes |
| `main.py` integration | Include the new router/services while retaining existing application lifespan and guard | Rewriting synthetic routes, starting another API, replacing the existing coordinator |

Suggested narrow interfaces:

```text
SecretProtector.protect(secret_bytes: bytes) -> bytes
SecretProtector.unprotect(ciphertext: bytes) -> bytes

RegistryStore.list_public_rows() -> bounded rows
RegistryStore.get_public_row(target_id) -> row | None
RegistryStore.create(registration, ciphertext, secret_format) -> saved row
RegistryStore.replace_connection(target_id, expected_revision, changes) -> saved row
RegistryStore.read_check_material(target_id) -> private immutable snapshot
RegistryStore.settle_check(target_id, expected_revision, check_outcome) -> saved row

normalize_base_url(text) -> canonical base URL
DestinationPolicy.authorize(canonical_url) -> approved destination | safe rejection
MetadataClient.check(approved_destination, token) -> validated metadata | safe failure
```

The store may use separate private dataclasses for `read_check_material`;
never return that type from a FastAPI route or serialize it with a public DTO.
Its credential field must be excluded from repr as well as JSON. Pass encrypted
bytes to the store, not a whole create DTO containing a plaintext token.

Construct services without opening a database or reading documents. Supply the
data root, protector, policy and HTTP transport through trusted Python injection
for tests. Browser request fields must not select a protector, transport, file
location, allowlist, timeout, fake response or provider. Production always uses
the real configured boundaries.

Avoid circular imports: the new router must not import `main` to reach its guard.
Pass the existing guard as a callable/dependency when including the router, or
use equivalent small factoring after checking it does not change old behavior.
The guard is currently declared after CORS setup in `main.py`; place router
registration accordingly. No CORS expansion is needed for the proposed GET/POST
routes or the existing confirmation header.

### 8.2 Database schema, connections and transaction boundaries

Use a new schema version **1** for the registry only. The following describes
the intended logical schema; additional indexes/constraints may be used without
inventing a new lifecycle. Do not store duplicate raw request/response envelopes.

```sql
CREATE TABLE registrations (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    endpoint_url TEXT NOT NULL UNIQUE,
    connection_revision INTEGER NOT NULL CHECK (connection_revision >= 1),
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE connection_credentials (
    target_id TEXT PRIMARY KEY REFERENCES registrations(id),
    secret_format TEXT NOT NULL,
    ciphertext BLOB NOT NULL,
    credential_state TEXT NOT NULL
        CHECK (credential_state IN ('STORED', 'UNAVAILABLE'))
);

CREATE TABLE connection_checks (
    target_id TEXT PRIMARY KEY REFERENCES registrations(id),
    connection_revision INTEGER NOT NULL CHECK (connection_revision >= 1),
    policy_fingerprint TEXT NOT NULL,
    checked_at TEXT NOT NULL,
    outcome TEXT NOT NULL CHECK (outcome IN ('CONNECTED', 'FAILED')),
    error_code TEXT,
    metadata_json TEXT
);
```

Use fixed `secret_format: "windows-dpapi-user-v1"`; the schema version and secret
format have different meanings. One identifies database shape, the other the
credential envelope. `metadata_json` is validated public metadata only.
`error_code` is an allowlisted application code, not upstream exception text.
Safe messages can be derived from the code at projection time rather than
persisted as arbitrary strings. Do not store token lengths/last characters,
credential fingerprints, raw headers or exception dumps.

Store UUID-based IDs as `connected-` plus a canonical lowercase hyphenated UUID.
Use UTC ISO-8601 timestamps consistently. Order list responses by `created_at`
ascending, then `id` ascending, independent of SQLite's incidental row order.
No foreign key points into run/history/job databases.

Connection rules:

- Open writers explicitly with foreign keys enabled and the same local
  transaction/rollback discipline used by existing storage. WAL/FULL synchronous
  durability is suitable; do not apply run-store migrations or audit triggers.
- Use `BEGIN IMMEDIATE` for capacity/uniqueness/create and revision replacement.
  Check the 32-row bound **inside** that transaction, not only in the route.
- Normal list/detail reads must not initialize schema, change journal mode,
  perform migrations or materialize JSON sidecars. Use a read-only connection
  for an existing database; close every cursor/connection deterministically.
- Handle “never initialized” separately from “expected database unavailable.”
  If a dedicated registry directory exists but its database is missing, or schema
  tables are partially present, do not silently rebuild it and report an empty
  registry. Return a safe storage-unavailable result and ask before recovery.
  Tests should cover the genuinely pristine path separately.
- A fresh explicitly requested write may initialize schema in its own dedicated
  directory and transaction. Do not adopt an arbitrary pre-existing SQLite file.
  Unsupported `user_version`, malformed rows, missing credential rows and invalid
  metadata fail closed, without printing paths or silently repairing data.
- SQLite busy/permission/I/O errors become `REGISTRY_UNAVAILABLE`, not unbounded
  retries. Do not hold a transaction open during DPAPI or network operations.
- Repository ignores already cover `apps/api/data`; tests must confirm new real
  state is beneath the configured ignored API data root, never a tracked example.

**Create transaction:** validate input and URL → protect token → open transaction
→ enforce duplicate URL and capacity → insert registration and private credential
→ commit → construct safe public DTO. A duplicate or failed insert cannot replace
an existing credential. All input plaintext must stay out of SQL parameters.
If response delivery is lost after commit, a repeat create returns duplicate
endpoint rather than a second record; it must not overwrite the credential.
The UI can refresh the list to reconcile this case without resending automatically.

**Replacement transaction:** validate body/ID/revision → protect a supplied new
token outside the transaction → begin → compare expected revision → enforce URL
uniqueness → update only submitted connection fields → increment revision and
updated time → replace ciphertext only if explicitly supplied → delete the
previous check row → commit. No failed validation, DPAPI failure, stale revision
or endpoint conflict may partially change the registration or token.

Omitting the token retains the ciphertext and its credential state; it does not
repair an unavailable credential. A valid supplied replacement sets credential
state back to STORED. Empty/null token is invalid API input; the UI omits the
field when its replacement input is blank. Credential-only replacement
increments the revision even if the operator happens to enter identical bytes;
do not decrypt/hash an old token merely to compare it.
Once credential state is UNAVAILABLE, further checks must report that state
without repeatedly attempting native recovery; only a deliberate successful
credential replacement clears it. An endpoint-only change is not credential
recovery and must not clear UNAVAILABLE.

**Check settlement transaction:** reread the target under the expected revision,
then atomically save the latest outcome/validated metadata and credential state
if recovery failed. If the revision no longer matches, write nothing and return
`CONNECTION_CHANGED`. Do not leave a “Connected” row from the old revision.
There is no append-only check history, retained raw HTTP response or run record.

### 8.3 Concrete request and public-response examples

All endpoint paths in examples below are relative to `/api/v1`. These are
documentation fixtures; never use the sample connection token in production.
All mutations/checks use the existing local confirmation/origin guard.

Create request:

```json
{
  "name": "Harbor document assistant",
  "endpoint_url": "http://127.0.0.1:7310",
  "connection_token": "offline-documentation-token-not-for-production",
  "description": "Connected document agent; metadata-only onboarding."
}
```

Create returns **201**, `Cache-Control: no-store`, with this public shape:

```json
{
  "schema_version": "connected-target-registration-v1",
  "id": "connected-11111111-1111-4111-8111-111111111111",
  "kind": "CONNECTED_AGENT",
  "synthetic": false,
  "selectable": false,
  "assessment_ready": false,
  "name": "Harbor document assistant",
  "description": "Connected document agent; metadata-only onboarding.",
  "endpoint_url": "http://127.0.0.1:7310",
  "connection_revision": 1,
  "created_at": "2026-11-20T12:00:00+00:00",
  "updated_at": "2026-11-20T12:00:00+00:00",
  "credential_state": "STORED",
  "destination_approved": true,
  "connection_status": "NOT_CHECKED",
  "last_checked_at": null,
  "connection_error": null,
  "contract_version": null,
  "metadata": null,
  "inference_ready": null,
  "inference_reasons": [],
  "live_usability": "NOT_VERIFIED_IN_PHASE2",
  "execution_support": "WORKER_GATEWAY_NOT_IMPLEMENTED"
}
```

The list may reuse this same bounded public DTO to avoid summary/detail drift.
It must never return raw SQLite rows. Detail/get/create/change/check all use the
same public field semantics. `destination_approved` is computed from current
server policy, not a browser-supplied boolean or a saved historical approval.

An explicit successful check changes `connection_status` to CONNECTED,
`last_checked_at` to the check timestamp and `contract_version` to the exact
validated contract. `metadata` contains the independently validated Phase 1
Metadata object, not arbitrary upstream JSON. Set `inference_ready` and
`inference_reasons` from that object's readiness. All execution-admission flags
remain false/unavailable. No request field sets those flags.

A settled failed check returns **200** with the registration preserved,
`connection_status: "FAILED"`, current `last_checked_at`, `metadata: null`,
`contract_version: null`, `inference_ready: null`, empty inference reasons and,
for example:

```json
{
  "connection_error": {
    "code": "AUTHENTICATION_FAILED",
    "message": "The target rejected the saved connection credential."
  }
}
```

This fragment shows the changing field, not the whole detail response.
Validation/admission/storage failures that prevent check execution/settlement
use the route's non-200 error contract rather than pretending to save a result:

```json
{
  "code": "CONNECTION_CHANGED",
  "detail": "The connection changed during this check. Review the saved configuration."
}
```

Use this safe `{code, detail}` shape for new route-level errors, without changing
the error shape of unrelated existing APIs. A field-error list is not required;
if added for usability, it may contain only allowlisted field names and static
codes/messages, never Pydantic's rejected `input` or raw validator context.

Replacement example, credential only:

```json
{
  "expected_connection_revision": 1,
  "connection_token": "offline-replacement-token-not-for-production"
}
```

Success returns revision 2 and the NOT_CHECKED/null readiness shape. The previous
check timestamp/metadata are not current evidence after a replacement.
`expected_connection_revision` must be an actual integer, not `"1"` or `true`.
No PUT/PATCH/DELETE or generic arbitrary-field update route is added.

An absent description becomes null; a deliberately blank/whitespace-only
description may normalize to null. Name is nonblank after display trimming.
String encodings must be valid Unicode/UTF-8, not lone surrogates. Bounds apply
before accepting oversized inputs, not after truncating them.

### 8.4 Native DPAPI implementation checklist

The protector's import must work without loading a DLL or requiring credentials;
initialize the native Windows boundary lazily. Tests can inject a fake protector,
but production must not select it via an environment flag or request field.

For a real Windows call:

1. Declare native `DATA_BLOB` with a Windows DWORD byte length and pointer to
   unsigned bytes. Keep Python-owned input buffers alive until the call finishes.
2. Use `WinDLL`/equivalent standard Windows FFI with explicit `argtypes`,
   `restype` and error handling for `CryptProtectData`, `CryptUnprotectData` and
   `LocalFree`; do not rely on implicit pointer-width conversions.
3. Use `CRYPTPROTECT_UI_FORBIDDEN` (`0x1`) and **do not** set
   `CRYPTPROTECT_LOCAL_MACHINE` (`0x4`). Pass no custom key/entropy and no prompt.
   Use a fixed nonsecret description or none.
4. Protect the exact ASCII token bytes. The ciphertext is opaque native output,
   not a JSON base64 plaintext wrapper. A database BLOB is preferred to avoid
   encoding ambiguity. Apply a reasonable bounded ciphertext ceiling, such as
   64 KiB, so corrupt records are rejected before recovery.
5. On unprotect, validate recovered byte count and the original ASCII/nonwhitespace
   token bounds before constructing an HTTP header. Invalid bytes are
   CREDENTIAL_UNAVAILABLE, never replacement characters or stripped input.
6. Copy native output only after success, then free every OS-allocated output in
   `finally`, including error paths where allocation occurred. Do not leak native
   pointers through repr/errors. If requesting an output description on unprotect,
   free that allocation too; avoiding that output is simpler.
7. Use safe typed internal failures without token/blob, Win32 diagnostic prose,
   current-user details or stack dumps. Route-level messages are static.
8. A fake protector used by persistence tests must not merely return its plaintext
   input as “ciphertext.” Use an opaque in-memory lookup fixture or equivalent so
   the test genuinely detects accidental SQL plaintext persistence. Such a fake
   still proves wiring only; label it explicitly.
9. On Windows, run the real temporary fake-token roundtrip as a distinct test.
   Reconstruct the protector/store before recovery to avoid proving only an
   in-memory cache. Never call native recovery on the user's real database.

Do not claim “tokens never enter the browser”: operators necessarily type a token
and POST it once to SecMate. The guarantee is write-only API handling and no
subsequent return/persistence in browser-managed storage. Do not claim DPAPI
protects tokens from code already executing as the same Windows user.

### 8.5 URL normalization, approval and remote-support boundaries

Keep parsing pure and deterministic; tests must exercise it without sockets.
Canonicalization runs identically on submitted URLs and server approval entries.
Use a real URL parser plus explicit rejection rules, not string-prefix matching.

Required examples:

| Input / configured approval | Required interpretation |
|---|---|
| `http://127.0.0.1:7310` vs same URL with one trailing slash | Same approved root base URL |
| `https://agent.example.invalid/adapter` | Representable remote base URL; not approved/contacted by this example |
| Approved `/adapter` vs submitted `/adapter-other` | Different destinations; prefix is not permission |
| Approved `/Adapter` vs submitted `/adapter` | Different case-sensitive base paths |
| HTTPS default port omitted vs `:443` | Same effective HTTPS destination after canonicalization |
| HTTP `:7310` vs `:7311` | Different approved destinations |
| `http://127.0.0.1:7310@elsewhere.example.invalid` | Reject userinfo; never treat as loopback |
| `https://host.example.invalid?x=1` or `#fragment` | Reject even if a hostname is otherwise approved |
| Base path `/proxy/agent` | Request `/proxy/agent/v1/metadata`, not root `/v1/metadata` |
| Base URL already ending `/v1/metadata` | Do not silently discover/strip paths; explain that the field expects the adapter base URL |

Do not accept a metadata `status_path`, `cancel_path`, arbitrary URL or redirect
Location as another allowed destination. Phase 2 never uses run receipt paths.
`example.invalid` examples are documentation/offline fixtures, not live hosts.

Approval order:

```text
strict URL parsing and canonicalization
    → exact current server policy match
    → classify allowed same-machine HTTP or verified-TLS HTTPS
    → for DNS: resolve/admit/bind actual destination using the approved policy
    → recover credential only when an outbound check can proceed
    → one GET at that same canonical destination
```

Exact approval must be evaluated before DNS. Fail closed on malformed server
approval JSON; never interpret an invalid setting as unrestricted networking.
Normalize/deduplicate approved entries deterministically. A fingerprint is SHA-256
over canonical, sorted nonsecret policy entries and relevant policy version;
it is not a token hash, attestation or browser-provided value.

The five-second deadline includes DNS/network work. DNS/TLS/IP verification
must not secretly use a second unvalidated hostname resolution or lose TLS SNI.
Do not “solve” address binding by disabling verification, accepting all resolved
private addresses or changing the certificate hostname. Do not assume HTTPX
MockTransport proves DNS binding or certificate verification: add tests at the
chosen transport/resolver boundary and document their actual coverage.

**Known implementation decision gate:** the current blueprint does not select a
custom DNS-pinning transport or approve remote private-address ranges. The
builder must inspect only the existing HTTPX/transport extension boundary, then
ask the user about the narrow mechanism/policy before implementing a choice if
the approved safeguards cannot be met directly. Do not add packages, use
undocumented internals or describe remote support as verified to avoid this gate.
It is acceptable to record remote verification BLOCKED while keeping the local
approved development path testable, but do not call the full planned HTTPS
connector complete if required policy behavior is not implemented/tested.

IPv6 literals, IDNA hostnames, unusual escaped base paths and custom trust stores
are not permission to invent new defaults. Ask if their treatment is unclear or
needed for the actual operator-approved destination. Ordinary ASCII DNS names,
IPv4 HTTPS origins and straightforward reverse-proxy base paths must not be
rejected merely because development currently uses loopback.

### 8.6 Metadata parsing and compatibility rules

Validate the **consumer wire contract**, not a Python constructor with producer
defaults. All fields emitted by Phase 1 and relied on by the connector must be
required on receipt; missing `contract_version` must not default into success.
For JSON arrays, use strict list fields in independent API wire models or
another correct JSON-mode boundary. Do not reject valid Phase 1 JSON merely
because its Python-side producer uses tuples internally.

| Metadata group | Validate and retain | Do not infer |
|---|---|---|
| Top level | Required contract/kind, display/app/adapter versions, instance UUID, identity/readiness/capabilities/session/limits/coverage; unknown fields forbidden | An assessment target profile or execution gateway |
| Identity | Bounded configured provider/model strings; the current contract's observed fields are null; bounded explanatory observation | That the configured model was contacted or is available |
| Readiness | Actual boolean `ready`, bounded list of safe code/message objects; reject wrong types | Connectivity failure merely because readiness is false |
| Capabilities | Exactly one each of search/read/create; valid bounded type lists, effect/scope strings | Full tool schemas, approval traces or actual completed operations |
| Session and limits | Actual values with strict numeric types, fixed one-slot/fresh-run contract and valid current upper bounds | Shared campaign token accounting or increased agent limits |
| Coverage | Bounded supplied/unavailable lists; retain current observation limitations | Full arguments, call IDs, model-call usage or streaming events |

Read the actual field names in `http_contracts.py`; do not approximate them from
the human-readable table above. Declare bounded consumer strings/arrays so a
32-KiB response cannot fill a database with arbitrary nested shapes. The exact
existing legitimate metadata must validate, including false readiness, null
observed identity and default tool limits. Do not require the default configured
budget values when the adapter validly uses lower/different approved values.

Response pipeline:

1. Admit HTTP status without logging body/headers. Map 401/403 safely; reject
   redirects, non-200 status or an incompatible response format.
2. Read a streamed decoded body with an incremental 32-KiB ceiling. Do not call
   an unbounded `.json()`/`.read()` first or trust Content-Length alone.
3. Decode strict UTF-8 and reject malformed JSON, duplicate object keys,
   non-object roots, invalid Unicode and excess nesting with a static error.
4. Validate required fields, unknown keys, strict types/bounds and compatibility.
   Compare the contract version explicitly before recording connectivity.
5. Check projected text for credential echo using only the transient token;
   reject without retaining the echoed body or diagnostic. Never add the token
   to a global redaction registry, hash ledger or persistent cache.
6. Produce one validated public metadata object or one safe check failure;
   release response/client/token references in all cases. Unknown exceptions
   become safe failures without retry or a traceback-bearing API response.

Do not parse capability `effect` prose to synthesize worker permissions. The
known contract and UI labels describe real read/create-only behavior, while
the endpoint's metadata remains self-reported and unverified execution.

### 8.7 Check lifecycle, concurrency and failure precedence

Connection checks are request-owned bounded operations, not queued durable jobs.
The HTTP request returns its settled public detail or a safe route-level error.
There is no new polling/SSE endpoint, background checker or persistent CHECKING
state. “Checking…” is transient frontend state while this request is pending.

Use one API-instance check slot. Acquire without waiting/queueing: on one event
loop, do the free-slot test and assignment without an intervening await.
Keep strong ownership until response/client cleanup finishes. A busy rejection
does not decrypt, resolve, contact or modify a target. The check slot is unrelated
to the adapter's inference slot and existing worker controller lock.

Orchestration pseudocode:

```text
require local confirmation and exact permitted Origin
reject any nonempty check body; validate target ID
read existing registration or return 404
acquire single check slot or return 409 CONNECTION_CHECK_BUSY
try:
    snapshot target revision and encrypted material
    apply current destination approval before DNS/decryption
    if unapproved: form safe failed check outcome without network/decryption
    else:
        apply resolved-destination/TLS admission
        decrypt and validate token, or form CREDENTIAL_UNAVAILABLE
        if still admitted/current: bounded metadata GET and validation
    settle outcome only if target revision and policy still match snapshot
    return fresh safe public detail
finally:
    close outbound resources and release check ownership
```

There must be no long-running SQLite write lock during that pseudocode's network
work. If target/policy changes are observed before transmission, abort before
transmission. A request already sent before a concurrent replacement cannot be
“unsent”; revision comparison prevents its result becoming current. Record this
normal concurrency limitation without pretending credential replacement cancels
an already issued metadata GET. It must never issue a second request.

| Event | Persistent/current effect |
|---|---|
| Save succeeds | Registration exists; NOT_CHECKED; no metadata/readiness; no outbound call |
| Approved metadata validates, readiness true | CONNECTED; inference_ready true; assessments still unavailable |
| Approved metadata validates, readiness false | CONNECTED; inference_ready false with endpoint-reported reasons |
| Wrong token / unreachable / malformed metadata | FAILED; current metadata/readiness null; credential retained unless recovery failed |
| DPAPI recovery fails | FAILED + credential UNAVAILABLE; no outbound request; replacement required |
| Destination unapproved | FAILED + DESTINATION_NOT_APPROVED after explicit check; no DNS/decryption/network |
| Connection replacement succeeds | Revision increments; current check/metadata/readiness invalidated |
| Policy fingerprint changes after restart | Current projection NOT_CHECKED/null; old check is not re-certified |
| Check result is stale on settlement | 409 CONNECTION_CHANGED; no stale write or retry |
| Save/check result cannot be committed | 503 REGISTRY_UNAVAILABLE; do not return a successful saved/connected claim |
| Client disconnect/cancellation | Cleanup owned HTTP resources; no new call/retry; do not fabricate a new completed check |

After a canceled recheck, an older saved outcome may remain visible with its
original time; it is not evidence the canceled attempt succeeded. A canceled
first check leaves NOT_CHECKED unless a truthful failure outcome was committed.
No credential-bearing request is automatically replayed because a browser lost
its response.

Use request cleanup and existing application shutdown patterns without disturbing
worker coordination. Do not add unbounded threads for DPAPI/DNS that outlive a
check and can later send credentials. If the installed networking boundary makes
the five-second cooperative deadline or cleanup ownership uncertain, stop and
ask; report the limitation rather than claiming hard OS-call preemption.

Route-level error precedence should be deterministic: guard and body/ID
validation → record existence/storage availability → check slot → destination/
credential/network outcome → revision-safe persistence. Test competing failures
so a malformed/unauthorized request cannot use the connector as an outbound probe.

### 8.8 Frontend implementation map and interaction details

`connectedTargetService.ts` owns only the new API namespace. Follow the existing
`VITE_API_BASE_URL ?? "/api/v1"` pattern, encode IDs, use `cache: "no-store"` and
support AbortSignal. Provide `list`, `get`, `create`, `checkConnection` and
`replaceConnection` methods. Send confirmation header on all new POSTs; the
browser supplies its actual Origin rather than a fabricated authorization value.
Do not attach the adapter bearer token to ordinary API GETs or browser calls to
the agent. Only the create/replacement JSON request temporarily contains it.

Service error handling consumes safe `code/detail` from SecMate and a static
fallback if parsing fails. Never turn arbitrary upstream response text or the
submitted request body into an Error/toast/log. Do not use the existing model
diagnostics/generation service to perform a connection check.

Keep frontend types separate:

```text
CreateConnectedTargetInput       // contains transient connection_token
ReplaceConnectedTargetInput      // optional transient replacement token
ConnectedTargetRegistration      // public DTO; no token/ciphertext fields
TargetsDisplayItem =
    { source: "synthetic", value: existing TargetSummary }
  | { source: "connected", value: ConnectedTargetRegistration }
```

Do not change `TargetSummary.synthetic: true` into a loose boolean and hope
synthetic-only rendering still works. Branch on the display discriminator.
Synthetic cards retain existing dialogs and `?id=...` links. Connected cards use
their new route and clear “Connected agent” identity, even before connectivity
has been checked. “Connected agent” is its kind, not a claim its latest check passed.

Targets page loading:

- Load existing synthetic projections and registry independently, with separate
  loading/errors and abort ownership; one failure must not discard the other.
- Count/search only the records actually available; show an explicit partial-data
  notice rather than a misleading complete inventory if one source failed.
- Preserve original synthetic ordering, then use deterministic registry ordering.
  A synthetic ID and a connected ID must not collide in React keys or routing.
- Onboard target remains reachable when registry list loading fails, but saving
  may truthfully fail if storage is unavailable. Do not substitute browser-local
  storage to “make it work offline.”

`App.tsx`: add lazy routes for `/targets/onboard` and
`/targets/connected/:targetId` in the existing authenticated Targets shell, before
the catch-all. Preserve RequireLogin/returnTo behavior. Do not invent a nested
standalone layout or a second BrowserRouter.

`TargetOnboardingPage.tsx`:

- Use a semantic form with labels, required attributes and inline static errors.
  `type="url"` is a usability hint; server parsing remains authoritative.
- Use `autoComplete="new-password"` for the token where appropriate; do not add
  a reveal button, token preview, remember-token checkbox or value in markup
  beyond the controlled input itself.
- Keep only transient token state. Successful save clears it **before**
  navigation. Unmount removes component references; do not promise browser
  autofill/memory can be cryptographically erased.
- Disable repeated submit while pending. Field edits/cancel/navigation abort
  pending UI ownership safely, but do not claim a server commit was undone.
- Show “Save registration,” not “Connect and assess.” On 409 duplicate explain
  the endpoint is already registered; refresh/open its public record deliberately.
- Provide “Back to Targets.” Do not auto-save drafts, send analytics or include
  form content in a notification/event payload.

`ConnectedTargetPage.tsx`:

- Fetch safe detail on route/ID changes only. Abort obsolete requests; prevent a
  late response for another ID/revision from replacing the current page.
- Show status, last check time and the four separate registration/connectivity/
  readiness/live states. The primary action is “Check connection,” disabled
  while pending. A failed check is rendered from the returned detail, not as
  removal of the target or a failed registration.
- If destination is unapproved, explain server approval is required; no UI action
  changes approval. Keep error code/message visible without a raw technical dump.
- Capabilities appear only when current validated metadata exists. Prefer compact
  read/create-only, file-type and logical-scope presentation over the raw JSON.
  Distinguish unknown from zero tools and unavailable usage from measured zero.
- Change connection can be a small inline panel using current endpoint and blank
  password input; never prefill a stored token. Submit the loaded revision.
  On stale revision, refetch public detail and require deliberate resubmission.
- Preserve a visible assessments-unavailable explanation; do not offer a disabled
  “Start assessment” implying this phase implemented an execution path.

Use existing classes/components for buttons, errors, toolbar and panels.
Add only necessary scoped CSS, no global theme overhaul. Verify labels,
focus after navigation/error, keyboard form submission, pending announcements
(`role=status`), errors (`role=alert`) and narrow-screen stacking. No new UI library.

### 8.9 Implementation work packets and exit criteria

Work serially through these packets; small focused tests are preferable to
writing the whole stack and then discovering contract incompatibilities.

| Packet | Deliverable | Exit evidence before moving on |
|---|---|---|
| A: Preflight/decisions | Confirmed source boundaries, branch, data isolation, existing dependencies, account and policy questions | No unresolved material design choice silently selected; existing files/changes inventoried |
| B: Contract-only | DTOs, pure canonicalization and static errors | Strict types/extras/bounds and documented JSON examples validate without network/storage |
| C: Secret boundary | Lazy native DPAPI + injectable interface | Fake isolation tests and Windows temporary-token native test; no token-bearing repr/errors |
| D: Registry | Version-1 separate schema/create/read/replacement | Atomicity/capacity/uniqueness/revision/recovery tests; no evidence/run-store writes |
| E: Metadata checker | Approved bounded request, wire validation, outcomes | Exact HTTPX boundary tests, no-retry/redirect/proxy/decryption-before-approval protections |
| F: API orchestration | Guarded new routes, public projection, slot/revision settlement | In-process HTTP tests traverse real registry + mocked connector; old projection tests unchanged |
| G: Frontend | Service, page/routes, safe detail/change, combined Targets list | Routing/forms/status/token handling and synthetic compatibility tests pass |
| H: Regression/manual | Full isolated API/frontend/build; bounded local metadata observation | Actual commands/outcomes/limitations recorded, never substituted by source inspection |
| I: Handover | Phase 2 results with unresolved carried checks and human table | Concise changed-file/outcome/blocker/checklist handover; explicit STOP |

Do not make each packet a separate new blueprint/status document. Use this
assignment and the one required results file. If a blocker prevents a packet,
report its exact question and which later packets depend on it; do not implement
another phase to work around the blocker.

### 8.10 Explicit decision gates and no-silent-default rules

These items are not grounds to reinterpret confirmed choices:

| Situation | Required builder action |
|---|---|
| Current branch differs or existing code has already started a registry | Inspect only the affected changes; ask how to preserve/integrate them before editing |
| Actual API process is a service/different Windows account | Ask before implementing/decrypting under a different identity; no machine-scoped DPAPI fallback |
| Real DPAPI API/permissions fail | Record failing temporary-token check safely; ask before changing mechanism or ACLs |
| DNS binding/private-address policy is unresolved | Present the narrow HTTPX-boundary choice and limitations; stop the affected remote connector work |
| Endpoint change would reuse a credential at a different approved destination | Before enabling that path, confirm whether the user requires token re-entry; recommend deliberate re-entry for a changed destination rather than silently forwarding the old credential |
| New dependency or existing version change appears necessary | Explain exact package/version/reason; obtain approval before installing/changing locks |
| Existing metadata differs from checked-in Phase 1 schema | Record compatible/incompatible observation; ask before changing either contract |
| Existing API test suite cannot run without real configuration or jobs | Repair test isolation narrowly or ask; never execute against saved data to get a green count |
| Runtime or storage already contains records | Do not overwrite/reset/import/clean them; use temporary tests and ask about any proposed migration |
| Required manual check conflicts with an active worker/listener | Do not kill/reload/replace it; ask for a safe testing window or report NOT RUN |

In particular, the prior omitted-token replacement rule describes retained
credentials for the existing destination. Whether it may carry a credential to
a **different** destination is an explicit pending user decision, not blanket
permission to send an old token to every approved host. The minimal four-field
create form and save-then-check UX remain confirmed.

## 9. Focused offline verification

Use temporary database roots, fake tokens, mocked HTTP transport and DPAPI
injection. Block provider traffic, worker launch and raw secret logging.
Never load real `.env`, decrypt existing secrets or touch development run data.

Required coverage:

1. Empty/create/list/get durability, max 32, duplicate endpoint conflict,
   transaction rollback, concurrent create, unsupported/corrupt schema, private/
   public separation. Successful save initiates no network operation.
2. Fake secret absent from SQLite/WAL/SHM raw bytes, public DTOs, JSON, validation
   errors, logs, exports/history/report paths, browser storage and process args.
   DPAPI failures remain unavailable; no plaintext fallback or accidental overwrite.
3. Windows-only real current-user DPAPI roundtrip of a harmless fake token under
   temporary storage, reconstruction/restart recovery and malformed ciphertext
   failure. Do not claim cross-account denial from a mock; document it as an
   OS assumption unless independently exercised without changing identities.
4. Every mutation/check rejects missing confirmation/untrusted Origin before
   writes, decryption or outbound requests. Test exact origin matching, body
   bounds and rejected-field redaction, including exception/upstream echo markers.
5. Endpoint cases: approved root/path HTTPS, approved development HTTP, unapproved
   saved destinations, nonlocal plaintext HTTP, credentials/query/fragment,
   malformed/encoded routing, alternate ports/paths/hosts, IPv6 syntax if supported,
   proxy environment variables, redirect to same/other host and TLS failures.
   Verify correct base-path append, no token to any unapproved/redirected address,
   and documented resolved-address/rebinding protections.
6. Real HTTPX boundary with MockTransport: exact GET/path/header and no retries;
   valid actual Phase 1 metadata fixture, contract/type/extra/capability mismatches,
   invalid UUID, readiness false, timeout, 401/403, other HTTP errors, chunked/
   oversized decoded response and hostile metadata. No provider/tool/run calls.
7. Saved/connected/readiness/live-unverified states are independent. Failed/
   invalidated checks never preserve a misleading current readiness. Revision or
   policy changes prevent stale results from overwriting new configuration.
   Concurrent check gets busy without a queue; responses/clients always close.
8. Existing two-target projection tests still pass unchanged. No run DB/history/
   job/worker/provider side effects; arbitrary connected IDs remain inadmissible
   to execution. Snapshot harmless pre-existing evidence in a sandbox and verify
   registry operations cannot alter its bytes.
9. Frontend: button routing/login return path, four inputs only, save/clear/
   navigate, explicit check only, all error/loading/readiness states, deliberate
   replacement, no token echo/storage and no automatic fetch to target hosts.
   Browser calls only SecMate; the API calls the agent.
10. Targets combined-list/search counts, partial registry outage, both existing
    synthetic cards/details, old projection shapes/deep links/focus/mobile
    structure. Update only obsolete “no onboarding button” assertions narrowly;
    retain their prohibition on accidental runtime/smoke calls.
11. Full frontend tests/build and sandboxed API regression gate; retain actual
    Phase 1 symlink skip and all unchanged SDK/tool/CLI regression results honestly.

### 9.1 Concrete test files, fixtures and assertions

The filenames below are proposed implementation locations. Combine closely
related cases if that better matches existing tests; do not generate a numbered
acceptance artifact per assertion. Parameterize meaningful invalid cases.

| Test file / boundary | Minimum concrete assertions |
|---|---|
| `apps/api/tests/test_connected_target_contracts.py` | Create/replace examples, missing/unknown fields, `"1"`/`true` revision rejection, blank/oversized/invalid-Unicode token/name/URL, null-vs-omitted token, exact public literals |
| `.../test_connection_secrets.py` | Lazy import, fake protector no-plaintext guarantee, real Windows protect/recover/reconstructed instance, corrupt/oversized blob, safe OS errors, unavailable platform |
| `.../test_connected_target_store.py` | New root, read-only empty behavior, create/reopen, SQL raw-byte token absence, 32/33 capacity, duplicate normalized endpoint, concurrent creates, expected-revision conflict, rollback, missing/corrupt/unsupported schema |
| `.../test_target_connection.py` | URL/approval/base-path/DNS/TLS policy, no decryption on unapproved destination, exact header/GET, no proxies/retries/redirects, full metadata fixture validation, stream/deadline cleanup |
| `.../test_connected_targets.py` | Guard/body/admission error ordering, safe create/list/get/change/check DTOs, real temporary SQLite + fake protector + injected HTTPX transport, concurrency and stale result prevention |
| `apps/web/src/connectedTargetService.test.ts` | Paths/encoded IDs, confirmation headers on POST only, absent token on GET, exact create/change bodies, no-store and safe error fallback |
| `.../TargetOnboardingPage.test.tsx` | Four fields only, POST once, token clear/navigation, static validation, duplicate/server errors, no storage/analytics, no target contact or check on save |
| `.../ConnectedTargetPage.test.tsx` | Not checked/Connected/Failed, independent readiness false/unknown, explicit check once, unapproved/DPAPI errors, safe replacement/revision conflict, no automatic check |
| Existing Targets/routing tests | Both synthetic records preserved, registry partial failure, connected kind/detail route, login return path, search count, legacy query links/accessibility/mobile structure |

Reusable safe fixtures:

- `registry_root`: a new TemporaryDirectory/pytest `tmp_path`, never API data.
- `fake_protector`: opaque ciphertext mapping; counts protect/unprotect calls and
  supports deliberate unavailable errors without native identities.
- `actual_metadata_json`: complete fictional Phase 1 wire fixture verified
  against its checked-in field semantics, with all required keys and no real
  environment/keys/paths. Variants flip readiness or corrupt one field at a time.
- `recording_transport`: HTTPX MockTransport capturing URL/method/headers in test
  memory only. Assert the bearer token exactly at this trusted test boundary;
  never print the captured headers or include them in a failing snapshot.
- `held_metadata_response`: asyncio events holding a check long enough to submit
  another check or connection replacement; no sleeps/poll loops for synchronization.
- `network_forbidden`: fails all unexpected provider/raw network paths while
  allowing only the explicit mock boundary; use the established narrow Windows
  asyncio socketpair exception if a test loop requires it.
- `forbidden_runtime`: monkeypatch worker/job launch, provider clients and adapter
  run endpoints to fail if onboarding invokes them. Preserve existing projection
  test blocking patterns instead of creating permissive fakes.

Important race sequences:

1. Start check at revision 1; hold mocked HTTP before completion; replace token
   or endpoint to revision 2; release response. Old check returns
   CONNECTION_CHANGED, cannot restore old metadata/readiness or ciphertext.
2. Hold one check; request a second check. Second gets busy with zero additional
   HTTP or DPAPI calls; after first cleanup a new deliberate check can proceed.
3. Concurrent duplicate creates reach the same database. Exactly one succeeds;
   the other is duplicate/conflict; only one registration/private row exists.
4. Force protect failure, insert failure and commit failure separately. Each
   returns failure with original data intact and no successful response claim.
5. Drop the client response after a committed save in a test. Refresh finds the
   record; repeat save does not replace its token or create a second registration.
6. Reconstruct services with a changed nonsecret allowlist. Previous success
   projects as NOT_CHECKED/null until a new explicit approved check; mere GET
   cannot decrypt/connect or silently approve the old endpoint.

Secret-exclusion checks must include a marker in a rejected token and a separate
marker echoed in hostile metadata/exception text. Assert absence from response
content, response headers, caplog/captured console, database/WAL/SHM bytes and
browser storage. Tests should fail before reaching a real network if the marker
would be sent to an unapproved or redirected destination. Avoid assertion helpers
that dump secret-bearing objects when those tests fail.

### 9.2 Verification ledger the builder must maintain

Record each actual gate in the results file with these columns:

| Gate | Exact command and cwd | Exit | Counts/time | Isolation/mock boundary | Limitations |
|---|---|---|---|---|---|
| Focused contracts/DPAPI/store | Builder fills after execution | NOT RUN | — | Temporary root; fake/native separately labeled | Pending |
| Focused HTTP/connector/projection | Builder fills after execution | NOT RUN | — | In-process API + explicit HTTP mock | Pending |
| Focused frontend | Builder fills after execution | NOT RUN | — | Mocked SecMate API only | Pending |
| Full API/frontend/build | Builder fills after execution | NOT RUN | — | Established sandbox driver | Pending |
| Unchanged Phase 1 regression | Builder fills after execution | NOT RUN | — | App-local offline environment | Existing symlink limitation |
| Local listening metadata-only onboarding | Builder/human fills after observation | NOT RUN | — | Real local listener, no model request | Not live model usability |

This table is a template, not evidence. Include the first failed attempt and its
fix/rerun, not only the final green result. Report missing worker environments,
DPAPI privileges/platform or DNS-policy blockers explicitly. Do not install/
reconfigure dependencies merely to improve a count.

### Test commands and isolation

Frontend from `apps/web` (no installation implied):

```powershell
npm test -- --run --maxWorkers=4
npm run build
```

API: use its existing `.venv/Scripts/python.exe` and a small explicit test driver,
following TRD-4's sandbox outline. **Before importing config/main**, block
`dotenv.load_dotenv`, remove inherited provider credentials in the test process,
select a fresh `SECMATE_API_DATA_ROOT`, sandbox `config.API_ROOT`, and preserve
the documented real worker-path references only for existing mocked/catalog
regressions. Tests must not start live workers/providers during registry checks.
Do not invoke a casual API pytest against real data or assume conftest alone
prevents API-local dotenv loading. Driver should support focused registry/
projection tests first, then `pytest -q --tb=short -p no:cacheprovider` for the
full suite; record exact actual invocations in results.

The driver must control **collection order**, not just install a fixture that
runs after application imports. A concrete safe implementation sequence is:

1. Start a fresh process using the API interpreter, not the document-agent or
   worker interpreter. Resolve repository/worker paths without reading saved data.
2. Create an owned temporary workspace and data root outside development state.
   Keep its context alive through pytest and cleanup. Do not delete/reuse any
   directory not owned by that context.
3. Enter a patch of `dotenv.load_dotenv` returning false **before** importing
   `secmate_api.config` or any application/execution module. Remove inherited
   provider secrets from this process without reading/printing their values.
4. Set the temporary `SECMATE_API_DATA_ROOT` and a test-owned nonsecret destination
   policy; do not inherit real approval configuration or real connection tokens.
5. Install initialization early enough that, after pytest loads initial
   conftest files but **before test-module collection**, the environment and
   `config.DATA_ROOT` point to the same selected temporary root. For example,
   a small driver plugin's `pytest_configure` hook can select that root, import
   the patched config and set `config.API_ROOT` to a temporary app directory.
   Existing conftest also assigns DATA_ROOT during collection; do not leave a
   mismatch between the environment tests inspect and the root modules actually use.
6. Only after the sandbox config is selected, import/point catalog and existing
   deepteam run modules to the real worker source/interpreter **paths** as TRD-4
   requires. Clear the catalog cache at that boundary; do not start a worker.
7. New registry services must receive the temporary data root and fake protector/
   HTTP transport explicitly. Do not rely on real Windows secrets or reload
   production modules to change configuration mid-test.
8. Run focused new tests plus `test_target_projection.py`; then run the complete
   API suite in a fresh isolated driver invocation. Retain appropriate original
   mocks/fixtures for the older worker-protocol regressions.
9. Record the concrete driver location and invocation, pytest arguments, exact
   selected test set/counts and any isolation exceptions. A driver that imports
   main before patching config is not an acceptable gate.
10. On teardown close only driver-owned connections/temporary files and restore
    process patches. No `maintenance.py`, history epoch reset or development
    controller reconciliation is a test-cleanup mechanism.

The outline above is not a new test driver already delivered by this planning
document. Verify the current pytest hook/fixture order during implementation;
ask if existing test initialization materially differs. Do not weaken a failing
storage-side-effect test by pointing its assertions at a different empty root.

Phase 1 app, if rerun, uses its own unchanged environment:

```powershell
# cwd local-document-agent; existing app-local uv/cache/Python settings
$env:UV_NO_ENV_FILE = "1"
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
.\.tools\bin\uv.exe run --frozen --no-sync pytest --basetemp=.cache/pytest-phase2-regression
.\.tools\bin\uv.exe lock --check --offline
.\.tools\bin\uv.exe pip check --python .venv/Scripts/python.exe
```

Do not regenerate locks/install dependencies to make a command convenient.
Missing environments or incompatible test assumptions require a question and
an honest BLOCKED/NOT RUN record, not a fabricated replacement gate.

## 10. Carried Phase 1 checks and manual verification

| Check | Current disposition / Phase 2 handling |
|---|---|
| Phase 1 human acceptance | **ACCEPTED in subsequent conversation**; old results remain historical. |
| Listening/authentication/metadata and idle Ctrl+C | **HUMAN-REPORTED PASS**; exact contract constant should be explicitly checked by Phase 2. Idle stop is not active-run cleanup evidence. |
| Actual Windows symlink fixture | **SKIPPED: privilege unavailable**. Carry limitation; do not change host privileges/Developer Mode. |
| Real model-backed HTTP summary/report/draft, provenance and duplicate replay | **NOT RUN**. Carry as live-usability gap; offline mocked tests are not a substitute for a live observation. Not required for metadata-only onboarding. |
| Real active-run cancellation/cleanup/deadline behavior | **NOT RUN live**; offline Phase 1 tests only. Do not start runs to claim this passed during onboarding. |
| CLI live usability / builder workflow demonstrations | User-reported CLI responses; builder live demonstrations remain unrecorded. No new claim. |
| Remote HTTPS/reverse proxy deployment | **NOT CHOSEN / NOT VERIFIED**. Connector tests do not deploy or certify a host. |
| Other operating systems/adversarial filesystem races/model accuracy | Uncertified limitations, not silently promoted to passing checks. |

Do not turn carried checks into worker execution or a required live-demonstration
workstream. If a needed Phase 2 test reveals a Phase 1 defect, stop and ask for
the narrow correction scope rather than altering the adapter here.

Human checklist after offline implementation:

1. Review changed paths, dependency diff (expected none), DPAPI/current-user
   assumptions, result distinctions, destination rules and carried limitations.
2. Confirm API runs loopback-only under the intended Windows user and operator
   storage permissions are appropriate. Privately configure the server approval
   for `http://127.0.0.1:7310`; retain both applications' independent provider
   settings. Never print tokens or pass them through startup arguments.
3. Manually start unchanged adapter and SecMate in deliberate terminals, without
   resetting evidence or replacing existing listeners. Do not auto-reload active
   jobs. Existing dependencies are used; do not reinstall the adapter stack.
4. Open Targets; verify both synthetic cards/details still work. Onboard one
   uniquely named connected agent with the four-field form. Saving alone must
   produce “Not checked,” clear token, navigate to saved detail and invoke no
   target/model operation.
5. Explicitly check connection: compatible authenticated metadata → Connected;
   readiness displayed separately; live usability unverified and assessments
   unavailable. Verify three capabilities and exact contract version.
6. Restart API under the same user after ensuring no active jobs; list/detail
   remains saved and token never reappears. Explicit recheck exercises recovery;
   no auto-check on restart/page load. Do not restart as another user to test it.
7. In isolated offline tests, demonstrate unavailable DPAPI and deliberate
   replacement/invalidation. Do not corrupt actual stored credentials for a demo.
8. Save an unapproved HTTPS destination using a fake token only; check must fail
   before DNS/socket/decryption. No remote host is contacted. Prefer this as an
   offline fixture unless a real saved test registration is explicitly desired.
9. Review browser/server output for absence of token/private state; do not share
   a HAR/request dump that contains the credential-bearing save request. UI token
   entry necessarily exists transiently in browser memory and the API request.
10. Record actual observations and accept Phase 2 or list corrections. No worker
    gateway, assessment execution or next-phase work follows automatically.

### 10.1 Builder manual run sheet after implementation

Use this run sheet only after the corresponding implementation/offline tests
exist. It is not a statement that these new routes currently exist or passed.
The browser onboarding flow is the primary manual check; direct API probes are
optional diagnostics, not a replacement for UI verification.

**Preparation**

- Confirm the chosen branch and that no saved assessment/job is active before
  restarting SecMate. Do not close another person's process to obtain a port.
- Existing adapter environment remains app-local. Privately provide its bearer
  token using the existing setup; keep provider configuration unchanged.
- Operator explicitly adds only the approved development destination to API
  configuration. Keep the API bound to `127.0.0.1:8000` and Vite on its existing
  permitted origin. Do not add a LAN origin or bind `0.0.0.0`.
- Keep two deliberate terminals, one for the adapter and one for SecMate's
  existing documented dev command. New code must not auto-launch the adapter.
- Confirm API and registry storage operate as the intended Windows account.
  The builder need only record “confirmed intended user account,” not publish
  a personal username, SID or profile path.

**Observed browser sequence**

| Step | Action | Expected visible / side-effect result |
|---|---|---|
| M1 | Open Targets | Two unchanged synthetic cards; existing detail dialogs still open/close normally |
| M2 | Choose Onboard target | Short four-field page inside Targets shell, not the old browser-local dialog |
| M3 | Save a unique registration for the development adapter | Saved detail; Not checked; no capabilities presented as current; no target request |
| M4 | Inspect browser state without dumping requests | No stored token in local/session storage or navigation state; password input gone/blank |
| M5 | Explicit Check connection | Checking indicator; then Connected with check time, exact compatible contract and three capabilities |
| M6 | Review readiness/status labels | Configured readiness separate; live execution unverified; assessments unavailable |
| M7 | Refresh detail and navigate away/back | Safe stored record loads; no automatic target check/inference |
| M8 | Reopen Targets/search | Connected kind present alongside both synthetic cards; counts/search correct |
| M9 | Safely restart API under same user, with no active jobs | Registration remains; explicit recheck can recover protected token; token never returned |
| M10 | Stop deliberately started services | Normal operator shutdown; no cleanup/reset of saved data |

Do not deliberately use the user's real wrong token, corrupt production
ciphertext or submit a different host to test leakage. Error/rotation/race/
unapproved-destination cases belong in temporary offline fixtures unless the
operator deliberately chooses a separate harmless manual registration.

**Optional safe direct API checks**

After implementation and startup, these are one-line PowerShell commands.
They contain no actual adapter credential and cause no inference:

```powershell
$api = "http://127.0.0.1:8000/api/v1"
$synthetic = Invoke-RestMethod -Method Get -Uri "$api/targets"
$synthetic | Select-Object id,name,synthetic,selectable
$registrations = Invoke-RestMethod -Method Get -Uri "$api/connected-targets"
$registrations | Select-Object id,name,connection_status,inference_ready,assessment_ready
```

Expected synthetic IDs remain the existing pair. Read-only registry commands
must not decrypt or contact the adapter. Do not pipe private database rows or
request bodies to the terminal to “show encryption worked.”

To deliberately recheck an already saved ID copied from the public list:

```powershell
$targetId = Read-Host "Existing connected registration ID"
$checked = Invoke-RestMethod -Method Post -Uri "$api/connected-targets/$targetId/connection-check" -Headers @{"X-SecMate-Local-Run"="confirmed"}
$checked | Select-Object id,connection_status,last_checked_at,contract_version,inference_ready,assessment_ready
Remove-Variable checked,targetId,registrations,synthetic,api -ErrorAction SilentlyContinue
```

This passes no connection token in a command, URL, process argument or browser
response. It relies on the API's saved DPAPI credential and approved destination.
A missing Origin in this local PowerShell request is governed by the existing
local guard's behavior, not a fabricated claim of browser authentication.
Never use these management API probes against a LAN/public API deployment.

Record expected vs actual result, observer (builder/human), timestamp, check ID/
registration ID if useful and safe error codes. Do not record tokens or full
HTTP request traces. A listening metadata check is not a live inference test;
the carried Phase 1 model-backed gaps remain unless separately actually observed.

## 11. Required results record and stop gate

The builder creates **`Documents/LOCAL_DOCUMENT_AGENT_SECMATE_PHASE2_RESULTS.md`**
after doing the work, not during planning. If it already exists, read and ask
before altering its disposition; append corrections, never replace prior evidence.

Required sections:

1. Actual branch/checkpoint/worktrees, initial changes, authority and scope.
2. User questions/answers; confirmed Windows API account and storage/destination
   decisions, without secrets or personal identifiers.
3. Changed files/contracts/config examples, migration/version strategy and
   preservation of synthetic/historical readers and evidence.
4. DPAPI evidence, token flow/exclusion tests, restart/re-entry/backup limitations,
   destination/TLS/DNS policy and any unresolved implementation conflicts.
5. Exact commands/exits/counts/skips, failed attempts/fixes and mocked-versus-real
   boundaries. No historical count promoted to a newly executed result.
6. Actual UI/manual metadata observations, storage/revision/isolation evidence and
   unchanged assessment admission. Distinguish saved, connected, readiness and
   live-unverified statuses.
7. Carried Phase 1 checks with their actual disposition; remote hosting and live
   model usability NOT VERIFIED unless an actual relevant observation exists.
8. Remaining blockers/limitations, exact startup/check instructions and checklist.
9. Human review table:

| Gate | Initial disposition |
|---|---|
| Phase 1 human acceptance | Accepted by user; subsequent reported metadata-only checks recorded above |
| Builder Phase 2 offline checks | NOT RUN until executed |
| Real Windows DPAPI temporary-token check | NOT RUN until executed; mocks alone insufficient |
| Human review of Phase 2 code/results | PENDING |
| Human manual onboarding/metadata check | PENDING / NOT RUN |
| Live model-backed HTTP usability | NOT VERIFIED; carried Phase 1 gap |
| Worker gateway / assessment readiness | NOT IMPLEMENTED IN PHASE 2 |
| Remote hosting deployment | NOT CHOSEN / NOT VERIFIED |
| Human acceptance of Phase 2 / next-phase permission | PENDING / NOT GRANTED |

**Completion:** bounded registry, protected credentials and minimal metadata-only
onboarding are implemented and honestly verified; two synthetic targets, old
readers and evidence remain intact; results exist; control returns to the human.
Registration is not assessment readiness. **STOP for explicit review/acceptance.
Do not implement or write Phase 3 instructions.**
