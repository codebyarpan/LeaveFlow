---
title: "LeaveFlow — API Contracts"
module: "3 — Architecture"
status: final
created: 2026-07-10
updated: 2026-07-10
---

# LeaveFlow — API Contracts

## 0. Status of this document

FastAPI generates an OpenAPI document from the typed Pydantic models, and **that generated document is the runtime source of truth** for request and response schemas. That is the reason `D-05` selected FastAPI in the first place, and the spine deliberately defers per-endpoint schemas to it.

What this document fixes is everything the generated schema *cannot* express and two epics would otherwise decide differently: the resource surface, who may call each endpoint and with what scope, the status-code semantics, the error vocabulary, and the pagination contract. It is binding where `ARCHITECTURE-SPINE.md` is binding, and it derives from `AD-10`, `AD-16`, `AD-19`, `AD-20` and `AD-21`.

## 1. Conventions

**Base path** is `/api/v1`. Paths are plural and kebab-case.

**Authentication** is a JSON Web Token presented as `Authorization: Bearer <token>` (`FR-02`, `AD-14`). The token carries an `exp` claim with a lifetime measured in hours (`NFR-02`). A request with no token, an expired token, or a token whose signature does not verify is rejected with `401`.

**Authorization is enforced server-side, in the query** (`NFR-03`, `NFR-04`, `AD-10`). The "Scope" column below is not advisory: it is applied as a SQL predicate, never as a filter over retrieved rows.

**Status codes carry meaning** (`AD-10`):

| Code | Means |
| --- | --- |
| `400` | The request is well-formed but the domain refuses it. The body names why, with numbers. |
| `401` | No valid token. |
| `403` | The actor's **role** does not grant this endpoint, **or** the actor may *see* this resource but may not perform *this action* on it. |
| `404` | The resource does not exist **or lies outside the actor's scope**. These two are byte-identical, by requirement (`FR-03`). |
| `409` | A state conflict. The resource is no longer in the state the transition requires (`AD-4`). |

A Manager requesting a non-report's leave request receives `404`, not `403`. A `403` would disclose that the request exists.

**`403` versus `404`, settled (`G3`, 2026-07-10).** The two codes answer different questions and must not be conflated:

- **`403` — denied by role grant.** The actor's role does not grant this endpoint at all. A non-Admin calling `GET /employees`; an Employee calling `GET /dashboard/manager`; an Admin calling `POST /leave-requests/<id>/approve`. Nothing is disclosed: the endpoint's existence and its role requirement are already public in the generated OpenAPI document, so `403` leaks no fact the actor could not read from the schema.
- **`404` — outside the actor's data scope.** The actor's role grants the endpoint, but the identified row is not theirs to see. A Manager naming a non-report's Leave Request. Byte-identical to a nonexistent identifier, per `FR-03` and `AD-10`.

The distinguishing test: **does the actor's role admit them to this endpoint at all?** If no → `403`, decided before any row is read. If yes → the scope predicate runs, and a miss is `404`. `AD-10`'s 404 rule is therefore unchanged and continues to mean exactly one thing: *outside your scope*.

Every `403` carries the error code `ACTION_NOT_PERMITTED` (§2), because §2 requires every non-2xx body to carry the envelope.

**Dates** are `YYYY-MM-DD` (`AD-12`). Instants are RFC 3339 UTC. The two are never interchanged.

**Enumerated values** are `UPPER_SNAKE_CASE` and transported verbatim (`AD-21`).

**Pagination.** List endpoints accept `page` and `page_size`. The server enforces a maximum page size; a client requesting more receives the maximum, not the larger page (`NFR-11`, `FR-12`). Responses carry `items`, `page`, `page_size`, `total`.

**Filters compose.** `status`, `leave_type_id`, `date_from` and `date_to` may be applied together. Filtering never widens authorization (`FR-12`).

## 2. Error envelope

Every non-2xx response body has the same shape (`NFR-17`):

```json
{
  "code": "INSUFFICIENT_BALANCE",
  "message": "The request costs 4 leave days; 1 is available.",
  "details": { "days_requested": 4, "days_available": 1 }
}
```

`code` is machine-readable and declared once in `domain/` (`AD-21`). `message` is human-readable. `details` carries the numbers a refusal must state.

| Code | Status | Raised when |
| --- | --- | --- |
| `AUTH_FAILED` | 401 | Credentials rejected. Identical for unknown identity and wrong password (`FR-01`). |
| `TOKEN_INVALID` | 401 | Absent, expired, or unverifiable token. |
| `ACTION_NOT_PERMITTED` | 403 | The actor's role does not grant this endpoint, or grants sight of the resource but not this action (`FR-03`, `G3`). |
| `FORBIDDEN_FIELD` | 400 | `PATCH /me` carried a field other than `full_name`. `details` names the rejected fields (`FR-17`, `G5`). |
| `EMAIL_ALREADY_IN_USE` | 409 | The email address already belongs to an Employee, active or deactivated (`FR-04`, `G2`). |
| `REPORTING_CYCLE` | 400 | The manager assignment would make an Employee their own Manager, directly or transitively (`DR-12`, `G7`). |
| `INSUFFICIENT_BALANCE` | 400 | Day count exceeds Available. Names `days_requested`, `days_available`. |
| `ZERO_LEAVE_DAYS` | 400 | The range contains only weekend days and Company Holidays. |
| `SPANS_TWO_LEAVE_YEARS` | 400 | Names the boundary date (`BR-04`, `DR-6`). |
| `INVALID_DATE_RANGE` | 400 | End date precedes start date. |
| `PAST_DATE_RANGE` | 400 | The range lies wholly in the past. |
| `SUPPORTING_DOCUMENT_REQUIRED` | 400 | The Leave Type requires one (`FR-13`). |
| `UNSUPPORTED_FILE_TYPE` | 400 | Not PDF, JPG/JPEG or PNG. |
| `FILE_TOO_LARGE` | 400 | Over 5 MB. |
| `LEAVE_ALREADY_TAKEN` | 400 | Cancellation raised against leave whose dates have passed (`DR-14`). |
| `POLICY_DISPOSITION_REQUIRED` | 400 | A Leave Type change affects existing balances and no `RECALCULATE` or `PRESERVE` disposition was supplied (`FR-06`, `AD-20`). |
| `DEPARTMENT_NOT_EMPTY` | 409 | Department still has assigned Employees (`FR-05`). |
| `EMPLOYEE_HAS_PENDING_REQUESTS` | 409 | Deactivation blocked (`FR-04`, `AD-22`). |
| `EMPLOYEE_HAS_DIRECT_REPORTS` | 409 | Deactivation **or demotion below `MANAGER`** blocked while an active Employee still names them as Manager (`FR-04`, `AD-22`, `G8`). |
| `TRANSITION_NOT_ALLOWED` | 409 | The guarded update matched zero rows — someone committed first (`FR-09`, `AD-4`). |

## 3. Vocabulary

| Field | Values |
| --- | --- |
| `leave_request.status` | `PENDING`, `APPROVED`, `REJECTED`, `CANCELLED` |
| `cancellation_request.status` | `PENDING`, `APPROVED`, `REJECTED` |
| `audit_entry.subject_type` | `LEAVE_REQUEST`, `CANCELLATION_REQUEST` |
| `audit_entry.actor_type` | `EMPLOYEE`, `SYSTEM` |
| `audit_entry.reason` | `AUTO_APPROVED_NO_MANAGER` (only value currently defined) |
| `notification.kind` | `REQUEST_SUBMITTED`, `REQUEST_APPROVED`, `REQUEST_REJECTED` |
| `policy_change.disposition` | `RECALCULATE`, `PRESERVE` |
| `role` | `EMPLOYEE`, `MANAGER`, `ADMIN` |

## 4. Endpoints

Scope notation: **self** = the authenticated Employee's own rows; **reports** = rows whose Employee has `manager_id = actor`; **all** = organization-wide.

### 4.1 Identity and profile

| Method | Path | Role | Scope | Realizes |
| --- | --- | --- | --- | --- |
| `POST` | `/auth/login` | anonymous | — | `FR-01` |
| `GET` | `/me` | any | self | `FR-17` |
| `PATCH` | `/me` | any | self | `FR-17` |

`PATCH /me` accepts exactly one field: `full_name`. It refuses any attempt to alter `email`, role, department, manager, joining date, or a balance quantity (`FR-17`). The Employee's email address is their credential identity and is maintained only by an Admin, through `PATCH /employees/<id>` (`FR-04`).

### 4.2 Organization administration

| Method | Path | Role | Scope | Realizes |
| --- | --- | --- | --- | --- |
| `POST` | `/employees` | Admin | all | `FR-04` |
| `GET` | `/employees` | Admin | all | `FR-04`, `FR-12` |
| `GET` | `/employees/<id>` | Admin | all | `FR-04` |
| `PATCH` | `/employees/<id>` | Admin | all | `FR-04` |
| `POST` | `/employees/<id>/deactivate` | Admin | all | `FR-04`, `AD-22` |
| `POST` | `/departments` | Admin | all | `FR-05` |
| `GET` | `/departments` | any | all | `FR-05` |
| `PATCH` | `/departments/<id>` | Admin | all | `FR-05` |
| `DELETE` | `/departments/<id>` | Admin | all | `FR-05` |

Deactivation is refused while the Employee holds a Pending request, and while any active Employee names them as Manager (`AD-22`). An Employee is never deleted.

`POST /employees` requires the Admin to supply the Employee's initial password, hashed before persistence (`FR-04`, `NFR-01`, `AD-14`). `PATCH /employees/<id>` accepts **no** password: there is no re-issue path, and no endpoint anywhere lets an Employee change their own (`PRD §6`). No `/employees` response carries a password or a password hash. The field itself belongs to the generated OpenAPI schema, per §5; what is fixed here is the refusal and the non-disclosure, which the schema cannot express.

### 4.3 Leave policy and holidays

| Method | Path | Role | Scope | Realizes |
| --- | --- | --- | --- | --- |
| `GET` | `/leave-types` | any | all | `FR-06` |
| `POST` | `/leave-types` | Admin | all | `FR-06`, `SM-5` |
| `PATCH` | `/leave-types/<id>` | Admin | all | `FR-06`, `AD-19`, `AD-20` |
| `GET` | `/policy-changes` | Admin | all | `FR-06`, `AD-20` |
| `GET` | `/holidays` | any | all | `FR-10` |
| `POST` | `/holidays` | Admin | all | `FR-10`, `AD-19` |
| `DELETE` | `/holidays/<id>` | Admin | all | `FR-10`, `AD-19` |
| `GET` | `/admin-review-flags` | Admin | all | `FR-10`, `AD-20` |

`PATCH /leave-types/<id>` requires a `disposition` of `RECALCULATE` or `PRESERVE` whenever the change would affect existing Leave Balances; without it the request is refused with `POLICY_DISPOSITION_REQUIRED`. The choice is persisted to `policy_change` (`FR-06`, `AD-20`).

Adding or deleting a holiday, and recalculating under a policy change, both run `AD-19`'s forward check. Where a balance would go negative in any materialized Leave Year, that **Employee and Leave Type pair** is left unchanged — the same Employee's other Leave Types still proceed — and a row appears in `/admin-review-flags`. The rest of the operation still succeeds, so these endpoints return `200` with a summary rather than failing wholesale.

`/admin-review-flags` is **read-only**. `FR-10` grants the Admin the read; no requirement grants a resolve, so no endpoint clears a flag.

### 4.4 Balances

| Method | Path | Role | Scope | Realizes |
| --- | --- | --- | --- | --- |
| `GET` | `/balances` | any | self | `FR-07` |
| `GET` | `/employees/<id>/balances` | Manager, Admin | reports, all | `FR-07`, `FR-03` |

Each balance returns `available` as the primary figure, with `reserved` and `consumed` disclosed alongside it (`FR-07`). `available` is derived, never stored.

### 4.5 Leave requests

| Method | Path | Role | Scope | Realizes |
| --- | --- | --- | --- | --- |
| `POST` | `/leave-requests/preview` | any | self | `FR-08`, `AD-2` |
| `POST` | `/leave-requests` | any | self | `FR-08` |
| `GET` | `/leave-requests` | any | self, reports, all | `FR-12`, `FR-20` |
| `GET` | `/leave-requests/<id>` | any | self, reports, all | `FR-03`, `FR-20` |
| `POST` | `/leave-requests/<id>/approve` | Manager | reports | `FR-09` |
| `POST` | `/leave-requests/<id>/reject` | Manager | reports | `FR-09` |
| `POST` | `/leave-requests/<id>/cancel` | any | self | `FR-09` |

`POST /leave-requests/preview` is the **only** way a client obtains a day count (`AD-2`). It returns:

```json
{
  "leave_days": 2,
  "excluded_dates": [
    { "date": "2026-08-15", "reason": "WEEKEND" },
    { "date": "2026-08-16", "reason": "WEEKEND" },
    { "date": "2026-08-17", "reason": "HOLIDAY", "name": "Independence Day (observed)" }
  ],
  "available_before": 6,
  "available_after": 4
}
```

Naming the excluded holiday is what `UJ-1` turns on: the day count resolves to a smaller number than the calendar span, and the employee sees *why*. The value returned here is **advisory only**; admission is decided against the balance row read under lock at submission time (`AD-3`).

An Admin can read every leave request and can approve none (`DR-13`). Approval by a Manager who is not the applicant's Manager returns `404` (`AD-10`).

### 4.6 Cancellation requests

| Method | Path | Role | Scope | Realizes |
| --- | --- | --- | --- | --- |
| `POST` | `/leave-requests/<id>/cancellation-requests` | any | self | `FR-09`, `DR-14` |
| `GET` | `/cancellation-requests` | any | self, all | `DR-14` |
| `POST` | `/cancellation-requests/<id>/approve` | Admin | all | `FR-09`, `DR-14` |
| `POST` | `/cancellation-requests/<id>/reject` | Admin | all | `FR-09`, `DR-14` |

Only the applicant may raise one, against their own Approved request, for leave whose dates have not passed. Only an Admin may decide it. The targeted Leave Request stays `APPROVED` while the decision is pending (`AD-13`).

### 4.7 Supporting documents

| Method | Path | Role | Scope | Realizes |
| --- | --- | --- | --- | --- |
| `POST` | `/leave-requests/<id>/document` | any | self | `FR-13` |
| `GET` | `/leave-requests/<id>/document` | any | self, reports, all | `FR-13`, `NFR-05` |

`multipart/form-data`. Type and size are validated before any bytes are written. The document is streamed by an authorized endpoint that re-applies `AD-10`'s scope; no static route maps to the storage volume (`AD-15`).

### 4.8 Notifications

| Method | Path | Role | Scope | Realizes |
| --- | --- | --- | --- | --- |
| `GET` | `/notifications` | any | self | `FR-14` |
| `GET` | `/notifications/unread-count` | any | self | `FR-11`, `FR-14` |
| `PATCH` | `/notifications/<id>/read` | any | self | `FR-14`, `AD-16` |

The unread count is derived, never stored. Mark-read is idempotent and permitted only to the addressee, exactly as `FR-14` now requires.

### 4.9 Visibility and reporting

| Method | Path | Role | Scope | Realizes |
| --- | --- | --- | --- | --- |
| `GET` | `/dashboard/employee` | any | self | `FR-11` |
| `GET` | `/dashboard/manager` | Manager | reports | `FR-11` |
| `GET` | `/dashboard/admin` | Admin | all | `FR-11` |
| `GET` | `/team` | Manager | reports | `FR-19` |
| `GET` | `/calendar` | Manager | reports | `FR-18` |
| `GET` | `/audit-entries` | Admin | all | `FR-16`, `DR-13` |
| `GET` | `/reports/leave.csv` | Manager, Admin | reports, all | `FR-15` |

Every dashboard accepts `date_from` and `date_to` (`FR-11`). `/calendar` distinguishes Approved from Pending leave visually and never blocks an approval (`BR-06`, `FR-18`). `/reports/leave.csv` exports exactly the rows matching the applied filters (`FR-15`). Full audit read access belongs to the Admin alone; no Employee or Manager may read it (`FR-16`).

A Manager requesting `/dashboard/employee` receives their own balances, not their reports'. An Employee requesting `/dashboard/manager` is refused (`FR-11`, `FR-03`).

### 4.10 Operations

| Method | Path | Role | Realizes |
| --- | --- | --- | --- |
| `GET` | `/health` | anonymous | deployment probe |

The Leave Year rollover has **no endpoint**. It is a CLI job invoked by an external scheduler (`AD-7`), because a scheduler inside the web process fires once per uvicorn worker.

## 5. What this document does not fix

Per-endpoint request and response schemas, field-level validation messages, and the exact CSV column set. All are owned by the code and published in the generated OpenAPI document at `/docs`. Fixing them twice would guarantee they diverge.
