---
baseline_commit: 4fc16290663c47acd605ca16d81d72f00818cf84
---

<!--
  Story context created 2026-07-15 by create-story (ultimate context engine).
  Sources: epics.md §Epic 4 / Story 4.1 (:1584-1627); prd.md FR-13 (:327-338), FR-06 (:213-214),
  NFR-05 (:573), NFR-17 (:595), DR-11 (:486), §7.3 (:549-552), §9 (:601); addendum.md §3.2 (:157);
  ARCHITECTURE-SPINE.md AD-15 (:151-155) + capability map (:396); api-contracts.md §4.7 (:206-213),
  §2 error codes (:81-83); erd.md §2.1 SUPPORTING_DOCUMENT (:238-247), §4.2 (:362); BRD FR-13/NFR-05;
  story files 3-4, 3-5; the 2026-07-15 code review of stories 3-1..3-5; live working tree.
  ⚠️ The working tree is DIRTY with ALL of Epic 3 plus the 2026-07-15 code-review fixes,
  UNCOMMITTED, atop 4fc1629. Build on top of it. Do not revert or commit any of it.
-->

# Story 4.1: Attach a Supporting Document

Status: done

## Story

As an Employee,
I want to attach the document my leave type requires,
So that my request carries its evidence and can be decided.

## Orientation: what this story actually is

**The first file upload in the codebase, Phase 3's opening story, and the PRD is blunt about
Phase 3:** "the part of the specification most likely to go undelivered, and calling it 'in
scope' does not make it safe" (prd.md:526). Everything around the upload already exists;
the upload itself exists nowhere:

| Need | Current state |
|---|---|
| `requires_supporting_document` flag | ✅ Fully plumbed since 2.1: column (`models.py:138`, `0003:54`), CRUD (`leave_types.py` service+api, PATCHable at `api/v1/leave_types.py:133`), frontend create/edit checkboxes + " · document required" badge (`LeaveTypesPage.tsx:379,561,439`). **Read by NOTHING on the request path — enforced nowhere.** Grep `requires_supporting_document` in `services/leave_requests.py`: zero hits. This story writes the first consumer. |
| Error codes | ✅ Reserved in api-contracts §2 (:81-83): `SUPPORTING_DOCUMENT_REQUIRED` 400, `UNSUPPORTED_FILE_TYPE` 400, `FILE_TOO_LARGE` 400. ❌ Not yet in `domain/vocabulary.py` or `main.py::CODE_TO_STATUS` — this story adds all three (a SANCTIONED `main.py` edit: "Later stories add their codes here beside their vocabulary", `main.py:45-48`). |
| Multipart parsing | ❌ `python-multipart` is NOT a dependency (`backend/pyproject.toml:16-33` has plain `fastapi`, not `fastapi[standard]`). FastAPI's `File`/`UploadFile`/form parsing raises without it. Zero `UploadFile` usage exists — no precedent to copy. |
| Frontend FormData | ✅ `api/client.ts:116-123` anticipates THIS story by name: a `FormData` body is never labelled JSON, the browser sets the multipart boundary. `apiFetch(path, {method:'POST', body: formData})` works today. |
| Storage volume | ❌ `docker-compose.yml:146` defers it by name: "the documents volume (Story 4.1)". No setting, no mount, no directory. |
| The scoped locate for GET | ✅ 2.7's `GET /leave-requests/<id>` already resolves actor role → scope (self/reports/all) and 404s byte-identically on a miss. The document GET re-applies exactly that. |
| Schema | ❌ `supporting_document` does not exist. Migration `0013` (head is `0012_notification`). |

**What this story must NOT contain:** anything under `/reports/` or CSV (Story 4.2's), any
audit row (an upload is not a state transition — AD-8, SM-4 stays exactly 14), any
notification (the three-kind set is "settled, twice over" — `vocabulary.py:345`), any new
frontend CSS, virus scanning, document deletion, versioning, or multi-file support (PRD §6:
"any feature not named in the specification is out of scope").

## Acceptance Criteria

*(From epics.md:1590-1627 verbatim, clauses compressed.)*

1. **Given** a database migrated by this story, **when** the schema is inspected, **then**
   `supporting_document` carries `leave_request_id` with `UNIQUE (leave_request_id)`, a
   `storage_name`, an `original_filename` and a `content_type`, **and** it carries no
   `size_bytes`, because size is validated before the bytes are written and no requirement
   reads it afterwards (ERD §2.1).
2. **Given** an upload to `POST /api/v1/leave-requests/<id>/document`, **when** it is neither
   PDF, JPG/JPEG nor PNG, or exceeds 5 MB, **then** the response is `400` with
   `UNSUPPORTED_FILE_TYPE` or `FILE_TOO_LARGE`, **and** both checks ran **before any bytes
   were written** to the volume (`FR-13`, `AD-15`).
3. **Given** an accepted upload, **when** it is stored, **then** it is written to a volume
   outside the web root under a server-generated UUID name, **and** the client-supplied
   filename is persisted as a data column and is never used as a path component (`NFR-05`,
   `AD-15`).
4. **Given** a Leave Type whose `requires_supporting_document` is true, **when** an Employee
   submits a Leave Request for it without a document, **then** the response is `400` with
   `SUPPORTING_DOCUMENT_REQUIRED`, **and** Story 2.6's submission service is the one place
   this is enforced (`FR-13`). *(Safe to arrive last: EL, CL and FL seed with the flag
   false — an Admin who set it true beforehand created a requirement that was configurable
   but unenforced, "a deliberate act, not a latent gap", PRD §7.3.)*
5. **Given** the applicant, the applicant's Manager, or an Admin, **when** they call
   `GET /api/v1/leave-requests/<id>/document`, **then** the document is streamed by an
   authorized endpoint that re-applies `AD-10`'s scope, **and** any other Employee receives
   `404`, and no static route maps to the storage volume (`FR-13`, `AD-15`).
6. **Given** the React application and a Leave Type requiring a document, **when** an
   Employee fills the request form, **then** an upload control is presented, and a rejected
   file states why (`NFR-17`).

## 🚨 Landmines. Read all ten before writing a line.

### Landmine 1 — AC4 as written is a dead end, and Open Decision #1 is how this story escapes it. Read it FIRST.

`POST /leave-requests/<id>/document` needs an existing request id. AC4 refuses a
document-requiring submission that has no document. There is no draft state (vocabulary is
exactly PENDING/APPROVED/REJECTED/CANCELLED) and no unattached-upload endpoint in the
contract. Implemented naively, **a document-requiring Leave Type can never be requested at
all**: submit → 400, upload → no id, forever. Both the architecture extraction and the
requirements extraction flagged this independently. The resolution is Open Decision #1
(multipart-capable submission). Do not invent a draft status, do not add an unlisted
endpoint, and do not ship the dead end silently.

### Landmine 2 — The proxy 413s a 5 MB upload before FastAPI ever runs.

`proxy/nginx.conf` sets no `client_max_body_size`, so nginx's **1 MB default** applies to
`location /api/v1` — through the deployed stack (`:8443`), every legal 5 MB upload dies as
a bare nginx `413`, outside the error envelope, with every backend test green. Set
`client_max_body_size 6m;` in the `/api/v1` location (margin over 5 MB for the multipart
framing). `frontend/nginx.conf` proxies nothing to the API (the `web` container serves the
bundle only) — the proxy is the one place. The Vite dev server imposes no body limit.

### Landmine 3 — `python-multipart` must be added, pinned, BEFORE any `File`/`UploadFile` param exists.

`backend/pyproject.toml` pins everything `==` ("not floors. Do not upgrade them"). Add
`python-multipart==0.0.32` (current stable, released 2026-06-04) to the same list. Without
it, FastAPI raises at route-definition time — the app fails to import, every test errors.
The api Docker image must be rebuilt (`docker compose build api`) or the deployed container
keeps the old dependency set while host-side pytest (which installs from pyproject into
`.venv`) passes.

### Landmine 4 — The submission endpoint is the most-pinned surface in the app. The JSON path must survive byte-identical.

Open Decision #1 makes `POST /leave-requests` content-type-branching. Existing tests pin:
framework 422 (bare `{"detail": …}`, never the envelope) for malformed bodies; the 366-day
span cap via `_assert_span_within_bound`; every domain refusal code; 201 shape. The
multipart branch is ADDITIVE — the JSON branch must reproduce FastAPI's current semantics
exactly (see OD#1's sketch: `SubmitRequest.model_validate` + re-raise as
`RequestValidationError(exc.errors())`). The existing submit test files are the regression
pin; run them before touching anything else and keep them green with ZERO test edits.

### Landmine 5 — Guard files this story legitimately touches, and the ones it must not.

- `test_scope_matrix.py::_SCOPE_REGISTRY` — BOTH new endpoints carry a path param and MUST
  be registered: `("POST", "/api/v1/leave-requests/{request_id}/document")` →
  `frozenset({Scope.SELF})`; `("GET", …)` → `frozenset({Scope.SELF, Scope.REPORTS, Scope.ALL})`
  (api-contracts §4.7: POST role any/scope self; GET role any/scope self+reports+all).
- `test_migrations_insert_nothing.py:112` — the expected-chain list is LITERAL filenames;
  append `0013_supporting_document.py` or the suite fails.
- `test_scoped_getters.py` — any `get_`/`list_` function in `repositories/` must take
  `actor` (`_ACTOR_PARAM_NAMES`, `:149`) or be EXEMPTed with a rationale. The document
  getter takes `actor` and applies the scope predicate in SQL (belt-and-braces — see Task 5).
- `test_vocabulary_literals.py` — the three new codes are declared ONCE in
  `domain/vocabulary.py` + `__all__`, literal nowhere else in `app/`/`seed/`. Every new
  `.py` under `app/` is scanned automatically (+1 parametrized case per file).
- SM-4 (`test_audit_entries.py:527`, `len(rows) == 14`): an upload writes NO audit row.
  `insert_audit_entry` call sites stay exactly 6.
- `test_model_migration_agreement.py` (`alembic check`): the ORM model must match `0013`
  byte-for-byte, including the UNIQUE constraint's name.

### Landmine 6 — "Before any bytes were written" means the VOLUME, and Starlette's spool is not the volume.

Starlette buffers `UploadFile` into its own `SpooledTemporaryFile` during parsing — that is
the framework's scratch space, not "the volume", and AC2 is not about it. The pin is:
validate declared content type FIRST, then size by reading the stream with a hard cap
(never trust `Content-Length` — it is client-supplied), and only after BOTH pass, open a
file under `{documents_dir}/{storage_name}`. The refusal tests assert the volume directory
gained no entry. 5 MB in memory is safe (`5_242_880 + 1` byte read cap).

### Landmine 7 — `UNIQUE (leave_request_id)` will 500 on the second upload unless the service decides first.

The constraint (erd.md §4.2:362) is the AD-5 backstop, never the gate. A second `POST` that
reaches the INSERT raises `IntegrityError` → raw 500. Open Decision #2 settles the
semantics (attach-or-replace while PENDING); whatever lands, the service must resolve
existing-document state under the request's row lock or an explicit SELECT before writing —
never let the constraint answer.

### Landmine 8 — The teardown order grows a new first step, and files outlive rows.

`supporting_document` FK-references `leave_request` with NO `ON DELETE` (the settled
convention — `0012:45-51`). Every integration teardown that bulk-deletes `leave_request`
must delete document rows FIRST — the exact Landmine-16 shape Story 3.4 fixed into six
fixtures for `notification`. New tests own their own document rows AND the files their
uploads wrote: unlink `{documents_dir}/{storage_name}` in the teardown (rows die with the
transaction; files do not).

### Landmine 9 — `original_filename` is DATA. It never touches a path, and it never leaves unescaped.

Persist exactly what the client sent (even `../../etc/passwd.pdf` — pin this with a test).
On GET it may appear ONLY inside a `Content-Disposition: attachment` header, RFC
5987-encoded (`filename*=UTF-8''…`); the file on disk is opened by `storage_name` (a UUID
column, `str(uuid)`, no extension) joined to the configured directory — nothing
client-supplied ever concatenates into a path. No static route, no `StaticFiles` mount,
maps to the volume.

### Landmine 10 — The frontend has no raw-bytes fetch, and the ten-key `LeaveRequestResponse` pin forbids the easy flag.

`apiFetch` (`client.ts`) parses JSON. Downloading the document needs a blob variant (new
`apiFetchBlob` beside it, same Authorization/session handling — extend `client.ts`, do not
fork it). And do NOT add `has_document` to `LeaveRequestResponse` to drive the UI — its
exact key set is pinned (3.3's ten-key pin test). The Manager's "View document" button
fetches on demand and renders a 404 as "No document attached" (Open Decision #6).

## Tasks / Subtasks

- [x] Task 1 — Dependency and infrastructure (AC2, AC3; Landmines 2, 3)
  - [x] Add `python-multipart==0.0.32` to `backend/pyproject.toml` dependencies; reinstall the venv; note the api image rebuild in the Dev Agent Record.
  - [x] Settings: add `documents_dir: Path` to `app/core/settings.py` (default: `_REPOSITORY_ROOT / "backend" / "var" / "documents"` — adjust to the file's existing root idiom); ensure-created on first write (`mkdir(parents=True, exist_ok=True)` in the service, not at import). Add to `.env.example`.
  - [x] `docker-compose.yml`: add the `documents` named volume, mount it into the api service (e.g. `/srv/documents`), set `DOCUMENTS_DIR` env; delete/adjust the "documents volume (Story 4.1) DEFERRED" comment at `:146`.
  - [x] `proxy/nginx.conf`: `client_max_body_size 6m;` inside `location /api/v1`.
- [x] Task 2 — Migration `0013_supporting_document` + model (AC1; Landmines 5, 7)
  - [x] Copy the 0012 SHAPE: docstring naming FR-13/NFR-05/AD-15, offline-mode refusal, `_quoted_role()` re-declared, no `ON DELETE` on the FK, no row inserts.
  - [x] Table: `id` UUID PK `server_default=sa.text("uuidv7()")`; `leave_request_id` UUID NOT NULL FK → `leave_request.id` with a NAMED `UNIQUE` constraint; `storage_name` `sa.Uuid()` NOT NULL; `original_filename` TEXT NOT NULL; `content_type` TEXT NOT NULL. **No `size_bytes`** (AC1 pins its absence), no timestamp (ERD names none), no `content_type` CHECK (OD#7).
  - [x] GRANT per mutability: OD#2's replace path mutates the row → `GRANT SELECT, INSERT, UPDATE` (the 0012 shape). `DELETE` withheld.
  - [x] Append `0013_supporting_document.py` to the literal chain list in `test_migrations_insert_nothing.py:112`.
  - [x] ORM model in `repositories/models.py` byte-faithful to the migration; `alembic upgrade head` on the dev DB; `alembic check` clean.
- [x] Task 3 — Vocabulary + status mapping (AC2, AC4)
  - [x] `domain/vocabulary.py`: `SUPPORTING_DOCUMENT_REQUIRED`, `UNSUPPORTED_FILE_TYPE`, `FILE_TOO_LARGE` (+ `__all__`). Also the allowlist constant `DOCUMENT_CONTENT_TYPES = ("application/pdf", "image/jpeg", "image/png")` and `DOCUMENT_MAX_BYTES = 5_242_880` if you keep them in `domain/` (they are policy, not HTTP).
  - [x] `main.py::CODE_TO_STATUS.update(...)`: all three → 400 (api-contracts §2). This `main.py` edit is sanctioned by the file's own comment.
- [x] Task 4 — Repository `repositories/supporting_document.py` (AC1, AC5; Landmine 5)
  - [x] One module per table (the 2.9 rule). `insert_supporting_document(session, *, leave_request_id, storage_name, original_filename, content_type)` — flush, not commit.
  - [x] `get_supporting_document(session, actor, *, leave_request_id, scope)` — takes `actor`, joins `leave_request` → `employee` and applies `employee_scope_predicate(scope, actor)` in SQL (belt-and-braces with the service's request locate; satisfies `test_scoped_getters` naturally). Returns columns, not the ORM entity (the `_READ_COLUMNS` idiom).
  - [x] `update_supporting_document(...)` for OD#2's replace (guarded by the service; the grant permits it).
- [x] Task 5 — Service `services/documents.py` (AC2, AC3, AC5; Landmines 6, 7, 9; OD#2, #3, #4)
  - [x] `_validate(upload) -> tuple[bytes, str]`: declared part content-type ∈ allowlist else `UNSUPPORTED_FILE_TYPE`; read stream with `DOCUMENT_MAX_BYTES + 1` cap, over → `FILE_TOO_LARGE`. Runs before any volume write. Never trusts `Content-Length`.
  - [x] `attach_document(actor, request_id, upload)`: locate the request under `Scope.SELF` (the POST grant is self-only regardless of role) → miss is byte-identical 404; enforce OD#2 (PENDING-only attach-or-replace); validate; write `{documents_dir}/{storage_name}`; insert-or-update the row; one transaction (AD-3); OD#4's write ordering (flush row → write file → commit; best-effort unlink on failure after write). No audit row, no notification.
  - [x] `get_document(actor, request_id)`: resolve scope from role exactly as 2.7's detail read does (Employee → SELF, Manager → REPORTS, Admin → ALL); fetch via the scoped getter; no row → the same byte-identical 404 (`RESOURCE_NOT_FOUND`) whether the request is out of scope, nonexistent, or documentless. Returns path + `content_type` + `original_filename` for the route to stream.
- [x] Task 6 — API `api/v1/documents.py` + registration (AC2, AC5; Landmine 5)
  - [x] `POST /leave-requests/{request_id}/document` — `get_current_employee` (role any), sync `def`, `document: UploadFile = File(...)` (read via `document.file`, the sync spool). 201 with a minimal response (`{id, original_filename, content_type}` — key set pinned by test).
  - [x] `GET /leave-requests/{request_id}/document` — `get_current_employee`; `FileResponse(path, media_type=row.content_type, content_disposition_type="attachment", filename=row.original_filename)` (Starlette RFC 5987-encodes `filename*`; verify the header in a test).
  - [x] Register the router in `api/v1/router.py`; add BOTH `_SCOPE_REGISTRY` entries.
- [x] Task 7 — The submission gate + multipart submission (AC4; Landmines 1, 4; OD#1)
  - [x] `services/leave_requests.submit_leave_request` gains keyword-only `document: <UploadDoc dataclass> | None = None` (the service must not import FastAPI types — pass bytes+metadata the api layer extracted, contract 1). Gate placement: after the pure range refusals, before any lock — `leave_type_repo.get_leave_type(...)`, if `requires_supporting_document` and `document is None` → `DomainError(SUPPORTING_DOCUMENT_REQUIRED)` with `details` naming the leave type code.
  - [x] When a document rides along: validate (Task 5's `_validate`), insert the row + write the file INSIDE the submission transaction, after `insert_leave_request` flushes the id — one command, one commit; a refused submission leaves no row and no file.
  - [x] Route: implement OD#1's content-type branch preserving the JSON path byte-identically. Run the full existing submit test files untouched before and after.
- [x] Task 8 — Frontend (AC6; Landmine 10; OD#6)
  - [x] `api/documents.ts`: `uploadDocument(requestId, file)` (FormData via `apiFetch`), `fetchDocumentBlob(requestId)` (new `apiFetchBlob` in `client.ts` — same token/session-expiry handling, returns `Blob`, 404 → typed error).
  - [x] `RequestPreviewPanel.tsx`: the selected leave type is already in state and `LeaveType.requires_supporting_document` is already on the wire type — render a file `<input>` when true (zero new CSS: `emp-field`). Client-side pre-check mirrors the server allowlist/size and STATES THE REASON on rejection (NFR-17); the server remains the guard. Submit sends FormData (json fields + `document` part) when a file is present; JSON exactly as today when not. Reset clears the file with the other fields.
  - [x] `ManagerQueuePanel.tsx`: per-pending-row "View document" button → `fetchDocumentBlob` → `URL.createObjectURL` open; 404 renders inline "No document attached." (per-row error isolation — the ManagerQueuePanel:61 lesson). No eager fetch, no `LeaveRequestResponse` change.
- [x] Task 9 — Tests (`tests/integration/test_supporting_document.py` — basename is globally unique, the 3.3 lesson) (all ACs)
  - [x] MEASURE the baseline first (`pytest --collect-only -q`; it was 589 at story-writing time) and explain the final arithmetic (+N new, +3 vocabulary-literal file cases, +1 migrations-insert-nothing case, +2 scope-matrix cases, +1 scoped-getter case — verify by collecting, the 3.3/3.4 standard).
  - [x] Schema pin (AC1): columns + named UNIQUE + **absence** of `size_bytes` via `information_schema`.
  - [x] Refusals (AC2): wrong type → 400 `UNSUPPORTED_FILE_TYPE`; >5 MB (send `DOCUMENT_MAX_BYTES + 1` bytes of valid-typed payload) → 400 `FILE_TOO_LARGE`; both assert the volume directory gained no file.
  - [x] Acceptance (AC3): file lands at `{documents_dir}/{storage_name}`, `storage_name` is a UUID ≠ any part of the filename; `original_filename` persisted verbatim including a `../` traversal name; response envelope keys pinned.
  - [x] Gate (AC4): flag-true type, JSON submit without document → 400 `SUPPORTING_DOCUMENT_REQUIRED`; multipart submit WITH document → 201 AND the row+file exist AND balances moved once; multipart submit with an invalid file → 400 and NO leave_request row (the transaction is one fact).
  - [x] Scope (AC5): applicant 200; their Manager 200; Admin 200; an unrelated Employee AND an unrelated Manager → 404 byte-identical to a nonexistent id; documentless request → the same 404; streamed `Content-Type` equals the stored one; `Content-Disposition` carries the RFC 5987 filename.
  - [x] OD#2 pin: second upload while PENDING replaces (old file gone or superseded per the decision); upload to an APPROVED request refused as decided.
  - [x] Teardown: document files unlinked, document rows deleted BEFORE `leave_request` (Landmine 8), then the standard 3.4 order (notifications first, children before parents, owner engine).
  - [x] SM-4 untouched: the scripted audit scenario still counts 14; zero notification rows from any document call.
- [x] Task 10 — Verification
  - [x] Full backend suite green; `import-linter` 7/7 (`api/` imports neither `repositories/` nor `domain/` — the route gets vocabulary codes via the service's `DomainError`, and the scope-matrix entries live in the test, not the route); `alembic check` clean.
  - [x] Frontend `npm run build` + `npm run lint` clean. State plainly: there is STILL no frontend test runner — AC6 is verified by tsc + vite + oxlint + the day-count guard scan + code reading, and by nothing else.
  - [x] Through the real proxy (`:8443`): one manual 5 MB-minus-one upload succeeds (Landmine 2 is only observable here — record it in the Dev Agent Record).

## Open Decisions

### 🚨 #1 — The submission ordering contradiction. RECOMMEND: multipart-capable `POST /leave-requests`.

**The problem (Landmine 1):** upload needs an id; the gate refuses a document-requiring
submission without a document; no draft state exists. Literal implementation = a type that
can never be requested.

**Recommended resolution:** `POST /api/v1/leave-requests` accepts BOTH content types. The
§4 grant table fixes method/path/role/scope only; request schemas are code-owned (§5), so
a multipart variant of the SAME path is contract-legal — §4.7 fixes multipart only for the
document endpoint, it does not forbid it elsewhere. Sketch:

```python
@router.post("/leave-requests", status_code=201)
async def submit_leave_request(request: Request, caller: Actor = Depends(get_current_employee)) -> SubmitResponse:
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("multipart/form-data"):
        form = await request.form()                     # needs python-multipart
        body = _validate_submit(dict(form))             # same SubmitRequest, same 422 path
        upload = form.get("document")                   # UploadFile | None
    else:
        try:
            body = SubmitRequest.model_validate_json(await request.body())
        except ValidationError as exc:
            raise RequestValidationError(exc.errors())  # byte-compatible framework 422
        upload = None
    ...
```

The service gate then reads naturally: no document part on a flag-true type → 400
`SUPPORTING_DOCUMENT_REQUIRED`; a document part → validated and stored in the SAME
transaction as the request insert. `POST /<id>/document` remains the attach/replace path
for an EXISTING request (a pending request whose type's flag flipped afterwards; optional
evidence on a non-requiring type — the §4.7 grant carries no flag precondition).

**The fallback, named so nobody drifts into it silently:** enforce the gate at DECIDE
instead (submit admits, Manager's approve refuses without a document). That contradicts
AC4's literal text AND PRD FR-13's consequence ("cannot be submitted without one") — TWO
declared deviations. Only if the multipart branch proves undeliverable in budget, and then
DECLARED, never slipped.

### #2 — Second upload semantics. RECOMMEND: attach-or-replace while PENDING; refuse on a decided request.

No source defines it; `UNIQUE` alone means a raw 500 (Landmine 7). Replace-while-PENDING
needs zero new error codes and zero contract rows: the row UPDATEs in place (new
`storage_name`/`original_filename`/`content_type`; best-effort unlink of the old file), the
grant carries UPDATE. A request no longer PENDING refuses with the byte-identical 404? No —
it is in scope and exists; RECOMMEND `409` reusing the state-conflict posture with
`TRANSITION_NOT_ALLOWED` and a message naming the state ("a decided request's evidence is
frozen"). If the dev judges that code too great a semantic stretch, the alternative is a new
`DOCUMENT_LOCKED`-style code — which is an api-contracts §2 deviation and must be declared.
Pick one, pin it, declare it.

### #3 — Validation mechanics. RECOMMEND: declared part content-type + capped read.

Allowlist exactly `("application/pdf", "image/jpeg", "image/png")` against the multipart
part's declared `Content-Type` (browsers send `image/jpeg` for .jpg/.jpeg — there is no
`image/jpg`). Size: read the stream up to `5_242_880 + 1` bytes; more → `FILE_TOO_LARGE`.
No magic-byte sniffing (no requirement asks for it; adding a content-inspection dependency
is scope creep). `details` on refusal carries the offending type or the limit (the
"numbers a refusal must state" rule, api-contracts §2).

### #4 — File-write vs transaction ordering. RECOMMEND: row flush → file write → commit.

Validate wholly in memory. Inside the one transaction: flush the row, then write the file,
then commit. A file-write failure rolls the row back (no row, no file). A crash between
file write and commit leaves an ORPHAN FILE: opaque UUID name, no row points to it, no
route can reach it — harmless, logged, accepted. Cleaning orphans is deliberately out of
scope (no requirement names it); note it in the module docstring.

### #5 — GET response headers. RECOMMEND: stored `content_type` + `attachment` disposition.

`FileResponse(..., media_type=row.content_type, filename=row.original_filename,
content_disposition_type="attachment")` — Starlette emits the RFC 5987 `filename*` form for
non-ASCII. `attachment`, not `inline`: serving client-supplied bytes inline on the app's
origin is a stored-XSS-adjacent risk for a mislabelled file; download-only closes it.

### #6 — Download UI scope. RECOMMEND: Manager queue button only; applicant download deferred.

The decision screen is where evidence matters (the manager cannot decide on evidence they
cannot see — end-to-end usability, not an AC). One button per pending row, on-demand blob
fetch, 404 → "No document attached." The applicant's own history download is real but not
load-bearing; add it to `deferred-work.md` under this story rather than widening the diff.

### #7 — No `content_type` CHECK on the table. Decided: follow the ERD.

erd.md §4.2 lists exactly one constraint for `supporting_document` (the UNIQUE). The
allowlist is service-layer policy (reconcile-prd.md:65: "the enforcement rule is
service-layer"); a CHECK would be a second copy of a vocabulary that already lives in one
place. This diverges from the `notification.kind` precedent because THERE the ERD named the
CHECK; here it deliberately does not.

### #8 — `storage_name` column type. Decided: `sa.Uuid`, file named `str(uuid)`, no extension.

The ERD's logical model types it `uuid` (erd.md:112). An extension on disk would be derived
from client input (the thing AD-15 forbids in paths) and nothing needs it — the stored
`content_type` serves the stream.

## Dev Notes

### Architecture compliance

- **Contract 1 / import-linter:** `api/v1/documents.py` imports the service only; the
  service imports repositories + domain; `UploadFile` never crosses into `services/` (hand
  over `(payload: bytes, declared_type: str, original_filename: str)` — a small dataclass in
  the service module).
- **AD-3:** one transaction per command, opened in the service. The upload command locks or
  scope-locates the request row first; it touches NO balance row, so no balance lock order
  applies.
- **AD-8 / SM-4:** zero audit rows. **AD-16 kinds:** zero notifications — the three-kind set
  is settled twice over (`vocabulary.py:345`); a `DOCUMENT_UPLOADED` kind must not appear.
- **AD-10:** POST locates under `Scope.SELF` always (the §4.7 grant); GET resolves scope
  from role exactly as `GET /leave-requests/{id}` does. Every miss — nonexistent id,
  out-of-scope id, documentless request — is the one byte-identical 404.
- **AD-15:** the volume path comes only from settings + `storage_name`. No `StaticFiles`,
  no route pattern touching the directory, no client string in any path expression.
- **AD-21:** the three codes + the allowlist tuple live in `domain/vocabulary.py` once.

### The response shapes (key sets pinned by test, the house rule)

- `POST …/document` 201 → `{id, original_filename, content_type}`.
- `GET …/document` 200 → raw bytes, `Content-Type: <stored>`, `Content-Disposition:
  attachment; filename*=…`. Not JSON, not paginated — the first non-JSON 200 in the app;
  there is no envelope to pin, pin the two headers instead.
- Refusals → the standard envelope via `DomainError` (`{code, message, details}`).

### Testing requirements

- The dirty-tree baseline is 589 collected. Measure first (the 3.4/3.5 lesson — twice the
  formula undercounted; collect and explain, never derive).
- The `_World` fixture shape from `test_leave_request_submit.py:72-215`: department +
  manager + managed employee + managerless employee + admin, leave type created THROUGH the
  service (materializes balances), per-test `suffix`, owner-engine teardown. This story's
  world needs one flag-true leave type and one flag-false.
- Fixed future weekday dates with comments (`_FRI = datetime.date(2026, 8, 14)  # Friday`).
- A tiny valid payload is enough for happy paths (`b"%PDF-1.4 fake"` with
  `application/pdf` — validation is declared-type + size, not content sniffing, per OD#3).
  The >5 MB body: `b"x" * (5_242_880 + 1)`.
- Documents volume in tests: the settings default resolves host-side; the suite runs
  in-process via `TestClient`, so uploads land in the real default directory — use per-test
  unique content, assert by `storage_name`, and unlink in teardown (Landmine 8).

### Project Structure Notes

New: `backend/alembic/versions/0013_supporting_document.py`,
`backend/app/repositories/supporting_document.py`, `backend/app/services/documents.py`,
`backend/app/api/v1/documents.py`, `backend/tests/integration/test_supporting_document.py`,
`frontend/src/api/documents.ts`.
Modified: `backend/pyproject.toml`, `backend/app/core/settings.py`,
`backend/app/domain/vocabulary.py`, `backend/app/main.py`,
`backend/app/repositories/models.py`, `backend/app/services/leave_requests.py`,
`backend/app/api/v1/leave_requests.py`, `backend/app/api/v1/router.py`,
`backend/tests/test_migrations_insert_nothing.py` (chain list),
`backend/tests/test_scope_matrix.py` (registry), `frontend/src/api/client.ts`
(+`apiFetchBlob`), `frontend/src/api/index.ts`,
`frontend/src/features/leave/RequestPreviewPanel.tsx`,
`frontend/src/features/leave/ManagerQueuePanel.tsx`, `docker-compose.yml`,
`proxy/nginx.conf`, `.env.example`.
Capability map (spine :396) names `api/v1/documents` + `services/document`; the plural
`services/documents.py` follows every neighbor (`notifications`, `balances`, …).

## Previous Story Intelligence

- **The 2026-07-15 code review of 3-1..3-5 landed 13 patches on this exact tree.** Live
  rules it set that bind this story: ONE hoisted `occurred_at` per transition (the upload
  writes no instant at all — the table has no timestamp column); `queryClient.clear()` runs
  at both session boundaries, so the new `documents` query key needs NO purge wiring;
  admin-review-flag writers dedupe (irrelevant here but the pattern of "loud, not silent"
  guards — see Landmine 7 — came from it); the repo `status`/`statuses` params now raise if
  both are passed (don't pass both).
- **Declared deviations are the house currency.** 3.3 declared a test-file rename; 3.5
  declared two frontend deviations; the review ADDED an undeclared one to 3-4's record
  retroactively. If OD#1's fallback or any AC bends, DECLARE it in the Dev Agent Record.
- **Measure the baseline first.** 3.2 undercounted, 3.4's own formula undercounted by the
  auto-generated guard cases, 3.5 measured first and closed exactly. 589 now; collect
  before and after and explain every unit of the delta.
- **The dev DB bites.** 3.4's record: a polluted dev DB (orphaned pytest writers, 311k
  balance rows) made the suite red with zero code defects — and `docker exec` WITHOUT `-i`
  silently no-ops psql. If the suite goes strange, check `pg_stat_user_tables` before
  checking the code, and reset with `docker exec -i`.
- **Guard-file edits are declared, never silent.** 3.4 was the first story to legitimately
  edit `test_scope_matrix.py`; this story is the second (+2 entries) and also appends to
  the migration chain list. Name both edits in the Dev Agent Record as owned scope.

## Git Intelligence

Last commits: `4fc1629` (stories 2.9–2.12), `83096b2` (2.8), `93fdb56` (2.7), `f513244`
(2.6), `d2f2b32` (2.5). The tree is dirty with ALL of Epic 3 + the 2026-07-15 review fixes,
uncommitted, atop `4fc1629` — build on top; committing is not this story's call.

## Latest Technical Information

- `python-multipart` current stable: **0.0.32** (2026-06-04) — the pin to add. FastAPI
  0.139.0 (pinned) imports it lazily at first `File`/`Form` route definition.
- Pinned stack (do not move): fastapi 0.139.0, pydantic 2.13.4, SQLAlchemy 2.0.51, alembic
  1.18.5, psycopg 3.3.4, Python 3.13, React 19.2.7, TanStack Query 5.101.2, PostgreSQL 18.4.
- Starlette's `UploadFile.file` is a sync `SpooledTemporaryFile` — sync `def` routes read it
  without the async drift the rest of the codebase avoids; only OD#1's dual-mode submit
  route needs `async def` (for `await request.form()`).

## References

- epics.md:1584-1627 (Epic 4, Story 4.1); :489-491 (implementation notes); :1629-1667 (4.2 boundary)
- prd.md:327-338 (FR-13); :213-214 (FR-06 seeds); :549-552 (§7.3 phase gap); :573 (NFR-05); :595 (NFR-17); :526 (Phase-3 risk)
- ARCHITECTURE-SPINE.md:151-155 (AD-15); :396 (capability map); :215 (seeded flag)
- api-contracts.md:206-213 (§4.7); :81-83 (§2 codes); :37-44 (403/404 rule)
- erd.md:109-115 + :238-247 (SUPPORTING_DOCUMENT); :314 (1 → 0..1); :362 (UNIQUE); :332-339 (physical idioms)
- reconcile-prd.md:65 (service-layer enforcement), :82 (retrieval scope fully covered)
- Code: `models.py:138`; `services/leave_requests.py:301-523`; `api/v1/leave_requests.py:190-272`; `client.ts:116-123`; `proxy/nginx.conf:28-40`; `docker-compose.yml:146`; `0012_notification.py` (the migration shape); `test_scope_matrix.py:138,205`; `test_scoped_getters.py:146-149`; `test_migrations_insert_nothing.py:112`

## Dev Agent Record

### Agent Model Used

Claude Fable 5 (claude-fable-5) via Claude Code — dev-story workflow, 2026-07-15.

### Debug Log References

- Baseline MEASURED before any code: `pytest --collect-only -q` → **589** (the story's own figure held).
- Landmine 4 verified by CAPTURE-AND-DIFF, not by reading: before touching the route, ten malformed/edge
  JSON submissions were replayed against the live app and their full wire bodies recorded; after OD#1
  landed, the same script re-ran and the diff was EMPTY except the capture script's own random UUID.
  The replication required reading FastAPI 0.139's installed source: `strict_content_type` defaults to
  **True** (an absent content type is NOT parsed as JSON — raw bytes reach the model and fail as
  `model_attributes_type`), errors are `exc.errors(include_url=False)` with a `("body", …)` loc prefix,
  the empty-body error is the literal `get_missing_field_error(("body",))` dict, and a JSON decode error
  is raised BEFORE dependencies resolve — hence the route's `_reject_malformed_json_early` dependency,
  declared ahead of `get_current_employee`, which preserves even the "unauthenticated + malformed JSON
  → 422" ordering edge.
- **The proxy check earned its keep twice** (Task 10, only observable through `:8443`): (1) with
  `client_max_body_size 6m` in place, a REAL 5,242,879-byte multipart submission returned **201** through
  nginx and the round-tripped GET was byte-identical — Landmine 2 closed; (2) the FIRST live attempt
  500'd with `PermissionError: /srv/documents/...` — the api container runs as uid 10001 (`leaveflow`)
  and the fresh named volume arrived ROOT-owned. Fixed in `backend/Dockerfile`: pre-create
  `/srv/documents` chowned to the runtime user (a named volume initializes ownership from the image
  directory on first use), volume recreated. Every host-side test was green throughout — this class of
  defect is invisible to the suite, which is exactly why the story pinned the manual check.
- Dev DB left CLEAN (the 3.4 lesson): the proxy-check request/document/audit/notification rows were
  deleted via the owner engine, the consumed day restored, and the volume file removed. Host
  `backend/var/documents` is empty after teardowns.

### Completion Notes List

- **All 6 ACs met. No AC deviations.** OD#1 resolved as RECOMMENDED (multipart-capable
  `POST /leave-requests`; the gate-at-decide fallback was NOT used). OD#2 as recommended:
  attach-or-replace while PENDING; a decided request refuses with the EXISTING
  `TRANSITION_NOT_ALLOWED` 409 (no new error code, no api-contracts §2 deviation). OD#3–#8 all
  as recommended/decided in the story.
- AC1: migration `0013_supporting_document` + byte-faithful ORM model (named UNIQUE
  `supporting_document_leave_request_id_key`; NO `size_bytes` — absence pinned by exact-set
  `information_schema` test; no `content_type` CHECK per OD#7). GRANT `SELECT, INSERT, UPDATE`
  (the 0012 shape — the replace path mutates), `DELETE` withheld — pinned LIVE via
  `has_table_privilege` as the app role.
- AC2: `services/documents._validate` — declared type against `vocabulary.DOCUMENT_CONTENT_TYPES`
  FIRST, then size from the bytes actually read under the route's `DOCUMENT_MAX_BYTES + 1` capped
  read (Content-Length never consulted). Both refusal tests assert the volume gained no entry.
- AC3: `{documents_dir}/{storage_name}` with `storage_name = uuid4()`, file named `str(uuid)` with
  no extension; `original_filename` persisted VERBATIM (pinned with `../../etc/passwd.pdf`) and
  leaves only inside the RFC 5987 `Content-Disposition` (pinned with a non-ASCII filename).
- AC4: the gate lives in `submit_leave_request` (step 1c — after the pure range refusals and the
  balance-existence 404, before any lock), `details` names the leave type code. A document rides
  the SAME transaction (row flush → file write → commit, OD#4; commit-failure unlinks). An invalid
  file rolls back the ENTIRE submission — no request row, no balance move, no file (pinned).
- AC5: `GET` resolves scope from role (2.7's three-way shape, re-declared per the cancellation.py
  precedent); the scoped getter re-applies the predicate in its own SQL (belt-and-braces). FOUR
  distinct misses pinned byte-identical to the nonexistent-id 404: unrelated Employee, unrelated
  Manager, documentless request, nonexistent id. POST locate is `Scope.SELF` regardless of role —
  an Admin attaching to another's request 404s identically (pinned).
- AC6: upload control renders when the selected type's `requires_supporting_document` is true
  (zero new CSS — `emp-field`); the pre-check states the REASON on rejection (type/size, NFR-17)
  with the server remaining the guard; a picked file rides the submission as FormData; JSON stays
  byte-identical when no file is picked. Manager queue gained a per-row on-demand "View document"
  button (OD#6) — 404 renders inline "No document attached.", per-row error isolation, no eager
  fetch, and the ten-key `LeaveRequestResponse` pin untouched. Verified by tsc + vite + oxlint +
  the day-count guard scan + code reading, and by nothing else — there is STILL no frontend test
  runner.
- AD-8/AD-16 held: zero `insert_audit_entry` call sites added (still exactly 6; SM-4's scripted
  scenario still counts 14), zero notifications from any document call (pinned).
- **Test arithmetic closed exactly** (the 3.5 standard): 589 baseline + 16 new
  (`test_supporting_document.py`) + 3 vocabulary-literal cases (three new `.py` under `app/`) +
  1 migrations-chain case + 2 scope-matrix cases + 1 scoped-getter case = **612 collected,
  612 passed**. import-linter 7/7 KEPT; `alembic check` clean; frontend build + oxlint clean.
- Owned guard-file edits, declared: `test_scope_matrix.py` (+2 entries — the second story ever to
  edit it), `test_migrations_insert_nothing.py` (chain append), `test_migration_smoke.py`
  (HEAD_REVISION → 0013), `test_schema_1_2.py` (exact-table-set + `supporting_document`). The last
  two are the standing per-schema-story pins; no other test file was touched.
- ⚠️ Operational note: the api Docker image MUST be rebuilt (`docker compose build api`) — it needs
  `python-multipart==0.0.32` AND the new Dockerfile layer that pre-creates `/srv/documents` owned
  by the runtime user. Done and verified live in this session; a fresh deployment gets both from
  the Dockerfile. The `documents` named volume + `DOCUMENTS_DIR` env landed in docker-compose.yml
  (un-deferring the `:146` comment by name).
- Declared deviations (implementation details, not AC bends): (1) `store_new_document` returns
  `(document_id, path)` rather than the story sketch's bare path, so the attach command projects
  the id without a re-read; (2) `services/documents.py` re-exports `DOCUMENT_MAX_BYTES` for the
  route (the `LEAVE_STATUS_VALUES` indirection) — the cap is still declared once, in
  `domain/vocabulary.py`; (3) the Dockerfile ownership fix (above) was not in the story's file
  list — it was surfaced by the story's own mandated proxy check and is in scope as Task 1
  infrastructure.

### File List

New:
- backend/alembic/versions/0013_supporting_document.py
- backend/app/repositories/supporting_document.py
- backend/app/services/documents.py
- backend/app/api/v1/documents.py
- backend/tests/integration/test_supporting_document.py
- frontend/src/api/documents.ts

Modified:
- backend/pyproject.toml (python-multipart==0.0.32)
- backend/Dockerfile (pre-create /srv/documents owned by the runtime user — the volume-ownership fix)
- backend/app/core/settings.py (documents_dir)
- backend/app/domain/vocabulary.py (3 codes + DOCUMENT_CONTENT_TYPES/DOCUMENT_MAX_BYTES + __all__)
- backend/app/main.py (CODE_TO_STATUS: 3 × 400)
- backend/app/repositories/models.py (SupportingDocument)
- backend/app/services/leave_requests.py (document param, step-1c gate, in-transaction store, guarded commit)
- backend/app/api/v1/leave_requests.py (OD#1 dual-content-type submit + byte-identical JSON helpers)
- backend/app/api/v1/router.py (documents router)
- backend/tests/test_migrations_insert_nothing.py (chain: +0013)
- backend/tests/test_scope_matrix.py (+2 registry entries)
- backend/tests/integration/test_migration_smoke.py (HEAD_REVISION → 0013_supporting_document)
- backend/tests/integration/test_schema_1_2.py (exact table set + supporting_document)
- frontend/src/api/client.ts (toApiError factored out; apiFetchBlob)
- frontend/src/api/index.ts (exports)
- frontend/src/api/leaveRequests.ts (SubmitLeaveInput.document; FormData branch in useSubmitLeaveRequest)
- frontend/src/features/leave/RequestPreviewPanel.tsx (upload control + pre-check, AC6)
- frontend/src/features/leave/ManagerQueuePanel.tsx (ViewDocumentButton, OD#6)
- docker-compose.yml (documents volume, DOCUMENTS_DIR, un-deferred comment)
- proxy/nginx.conf (client_max_body_size 6m in /api/v1)
- .env.example (DOCUMENTS_DIR)
- .gitignore (backend/var/)

### Review Findings

Code review 2026-07-15 (Blind Hunter + Edge Case Hunter + Acceptance Auditor; no AC violations found — findings below are defects and fragilities beside the ACs).

- [x] [Review][Patch] (resolved Decision, 2026-07-15: reject) A zero-byte file satisfies `SUPPORTING_DOCUMENT_REQUIRED` and is stored. FIXED: `_validate` refuses an empty payload as `400 UNSUPPORTED_FILE_TYPE` with an "empty" message (type → empty → size order); pinned on both the attach and the multipart-submit paths (`test_zero_byte_file_is_refused_and_writes_nothing`). [backend/app/services/documents.py]
- [x] [Review][Patch] (resolved Decision, 2026-07-15: build the UI) The standalone attach/replace flow shipped with no UI caller. FIXED: `AttachDocumentControl` on every PENDING row of My Leave History — pre-check with stated reasons, imperative upload via the existing `uploadDocument`, 409/404/400 rendered inline; the shared policy constants moved to `features/leave/documentPolicy.ts` (one frontend copy). [frontend/src/features/leave/MyLeaveHistoryPanel.tsx]
- [x] [Review][Patch] Malformed multipart body escapes as a raw 500 — DISPROVEN on read: Starlette 1.3.1 converts `MultiPartException` to an in-app `HTTPException(400)` (`starlette/requests.py::_get_form`), so the path was already a framework-shaped 400. No code change; pinned by `test_malformed_multipart_is_a_400_not_a_500` so a refactor of the manual `request.form()` cannot regress it. [backend/app/api/v1/leave_requests.py]
- [x] [Review][Patch] Document GET returns a raw 500 when the row exists but the file is gone from the volume. FIXED: `get_document` existence-checks the path and a miss joins AD-10's byte-identical 404; pinned by `test_get_with_row_but_missing_file_is_the_byte_identical_404`. [backend/app/services/documents.py]
- [x] [Review][Patch] "View document" opens the tab after an `await` — popup blockers swallow it silently. FIXED: null-checked `window.open`; blocked → anchor `download` fallback (never blocked) plus an inline "Pop-up blocked — downloaded instead." note. [frontend/src/features/leave/ManagerQueuePanel.tsx]
- [x] [Review][Patch] A picked document survives a successful submit and rides the next submission. FIXED: submit `onSuccess` clears `documentFile`/`documentError`, and the native input is keyed to remount on leave-type change and submit success so its filename display never contradicts the cleared state. [frontend/src/features/leave/RequestPreviewPanel.tsx]
- [x] [Review][Patch] `multipart/form-data` detection is case-sensitive. FIXED: both the pre-auth guard and the route branch case-fold. NOTE the finding's premise was partly wrong — Starlette's own parser is exact-match lowercase and yields an EMPTY form for `Multipart/Form-Data`, so uppercase cannot fully succeed anywhere; the fix buys the truthful missing-fields 422 (what any FastAPI form route does) instead of the opaque `model_attributes_type` one. Pinned by `test_uppercase_multipart_content_type_branches_as_multipart`. [backend/app/api/v1/leave_requests.py]
- [x] [Review][Patch] Declared file content type compared exact-string against the allowlist. FIXED: `_normalize_media_type` (case-fold, strip parameters) runs before the check; the ROW and the 201 both carry the canonical form. Pinned by `test_declared_type_is_normalized_per_rfc_2045`. [backend/app/services/documents.py]
- [x] [Review][Patch] Post-commit unlink suppresses only FileNotFoundError. FIXED: `unlink_quietly` (swallows all `OSError`) at all three best-effort sites — the replace's old file, the attach commit-failure, and the submit commit-failure (where a raise would also have masked the commit error). [backend/app/services/documents.py, backend/app/services/leave_requests.py]
- [x] [Review][Defer] Attach path concurrency: two unguarded races — (a) concurrent first-attach both read `existing is None`, both INSERT, loser's commit fires the UNIQUE backstop as a raw 500 and orphans its file; (b) TOCTOU on the PENDING gate lets evidence attach to a just-decided request. Spec-compliant as written (Landmine 7 offered "row lock OR explicit SELECT" and the weaker option was taken); single-user-per-request in practice — deferred [backend/app/services/documents.py:250-283]
- [x] [Review][Defer] The "at most one byte over the limit is buffered" claim is false — `request.form()`/FastAPI spool the entire part to a SpooledTemporaryFile before the capped read; prod is bounded by nginx's 6m but the dev server/TestClient accept an arbitrarily large disk spool. Fix is a streaming guard; at minimum correct the module docstring — deferred [backend/app/services/documents.py:20]
- [x] [Review][Defer] Uploads over 6 MB get nginx's raw HTML 413 outside the envelope, and nothing pins the 5 MB<x≤6 MB window reaching `FILE_TOO_LARGE` through the proxy — documented tradeoff owned by the nginx.conf comment — deferred [proxy/nginx.conf:36]
- [x] [Review][Defer] Hardcoded 2026 dates make the suite a time bomb from 2026-08-19 (`PAST_DATE_RANGE`) — house-wide pattern (11 integration files carry `date(202…)` literals), not a 4.1 defect; fix suite-wide in one pass — deferred, pre-existing [backend/tests/integration/test_supporting_document.py:70]
- [x] [Review][Defer] `original_filename` accepted empty or arbitrarily long — `""` yields a nameless Content-Disposition download; a multi-KB name is echoed as an oversized response header. No spec bound exists; pick one when the contract next opens — deferred [backend/app/api/v1/leave_requests.py:404, backend/app/api/v1/documents.py:98]
- [x] [Review][Defer] Frontend restates the 5 MB cap and type allowlist as literals with nothing tying them to `domain/vocabulary.py` — a backend policy change silently strands the pre-check; same accepted class as the app-wide frontend status-literal copies — deferred [frontend/src/features/leave/RequestPreviewPanel.tsx:35]
- [x] [Review][Defer] A failed `path.write_bytes` (disk full mid-write) rolls the row back but leaves a partial file nothing unlinks, and the OSError escapes as a raw 500 — same accepted-orphan family as OD#4's crash window; envelope-on-500 is an app-wide gap, not this story's — deferred [backend/app/services/documents.py:214, backend/app/services/documents.py:273]

## Change Log

- 2026-07-15: Code review (Blind Hunter + Edge Case Hunter + Acceptance Auditor) — zero AC
  violations; 2 decision-needed (both resolved: zero-byte → reject under UNSUPPORTED_FILE_TYPE;
  attach UI → built now), 9 patches applied (1 disproven-on-read and pinned by test instead:
  malformed multipart was already a framework 400), 7 deferred to deferred-work.md, 7 dismissed.
  +5 integration tests (634 total passing); import-linter 7/7; tsc/oxlint/vite clean. New:
  frontend/src/features/leave/documentPolicy.ts (shared pre-check constants); AttachDocumentControl
  in MyLeaveHistoryPanel wires the OD#2 endpoint to the product. Status → done.

- 2026-07-15: Story 4.1 implemented — the first file upload in the codebase. Migration 0013 +
  SupportingDocument model; 3 new error codes + document policy in vocabulary; repository/service/api
  trio; FR-13 gate in submit_leave_request; OD#1 multipart-capable POST /leave-requests with the JSON
  branch verified byte-identical by capture-and-diff; frontend upload control + apiFetchBlob + Manager
  "View document"; nginx 6m body cap; documents volume + Dockerfile ownership fix (found live).
  16 new integration tests; 612 collected / 612 passed; import-linter 7/7; alembic check clean;
  frontend build + lint clean. Status → review.

- 2026-07-15: Story created by create-story (ultimate context engine) — three parallel
  research passes (requirements, architecture contracts, codebase reuse/guards) synthesized;
  the AC4 ordering contradiction surfaced independently by two passes and settled as OD#1.
