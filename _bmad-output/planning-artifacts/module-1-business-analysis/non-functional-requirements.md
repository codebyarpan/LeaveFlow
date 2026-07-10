---
title: "LeaveFlow — Non-Functional Requirements"
module: "1 — Understanding the Problem"
status: draft
created: 2026-07-09
updated: 2026-07-09
---

# Non-Functional Requirements

> **Provenance note.** **Every requirement in this document is proposed by the engineer.** Neither the specification nor any confirmed business rule states a single non-functional requirement. Nothing here is confirmed. Each item is a defensible position offered for correction, not a discovered fact, and each should be read as beginning with "the engineer proposes that…".

Targets are calibrated to a seven-day trainee project with a small dataset and a handful of concurrent users. They are deliberately modest. A target that cannot be measured within the project's budget is not a requirement; it is decoration.

Where an item derives from something in the specification, an engineering decision, or the learning path, that link is named. Where it does not, it stands on the engineer's judgement alone.

---

## Security

**NFR-01 — Credential storage.** Passwords are stored as salted hashes using a deliberately slow algorithm (bcrypt or Argon2). Plaintext and reversible encryption are prohibited. *Derives from FR-01, which requires secure login.*

**NFR-02 — Token lifetime.** Access tokens expire, with a lifetime measured in hours rather than days if no refresh mechanism is built. *The specification requires JWT (FR-02) but is silent on token lifetime.*

**NFR-03 — Authorization is enforced server-side.** Hiding a control in the frontend is not access control. Every restricted operation is checked at the API boundary, independently of the frontend. *Derives from FR-03.*

**NFR-04 — Data scoping is enforced in the query.** A Manager's access to direct reports is constrained where data is fetched, not filtered after retrieval. This is the difference between a system that is secure and one that merely appears so. *Derives from FR-03 and engineering decision D-03.*

**NFR-05 — Upload validation.** Uploaded documents are validated for type and size, stored outside the web root, and served only to authorized callers. Filenames from the client are never trusted as paths. *Derives from FR-13.*

**NFR-06 — Transport.** Credentials and tokens travel over TLS in any deployed environment.

## Reliability and Correctness

**NFR-07 — Balance operations are atomic.** Reserving, consuming, and releasing leave days occur within a transaction. A concurrent double submission must not produce a negative or double-counted balance. *Derives from engineering decision D-01.*

**NFR-08 — The leave-day calculation is a single pure function.** One implementation, directly unit-tested, called by every path that touches a balance. Duplicating the weekend-and-holiday logic anywhere is a defect. *Derives from engineering decision D-02.*

**NFR-09 — Audit entries are append-only.** No application code path updates or deletes an audit record. *Derives from FR-16.*

## Performance

**NFR-10 — Interactive response.** Typical read endpoints respond within roughly 500 ms at the project's data scale. An order of magnitude, not a contractual figure.

**NFR-11 — Bounded result sets.** No endpoint returns an unbounded collection. Pagination has a maximum page size enforced server-side, regardless of what the client requests. *Derives from FR-12.*

**NFR-12 — Indexed access paths.** Foreign keys and the columns used to scope queries — employee, manager, department, leave year, request status — are indexed.

## Maintainability

**NFR-13 — Layered structure.** Route handlers, business logic, and data access are separated. Leave policy rules live in the service layer, not in route handlers and not in the database.

**NFR-14 — Policy as configuration.** Leave type behaviour (carry-forward, lapse, document requirement) is data the Admin configures. Adding a leave type requires no code change. *Derives from FR-06 and engineering decision D-04.*

**NFR-15 — Tests exist for the rules that are hard.** Proration, carry-forward, the year boundary, the weekend-and-holiday day count, and the authorization scope are unit-tested. Coverage of CRUD scaffolding matters less.

## Usability

**NFR-16 — Role-appropriate interface.** Each role's dashboard exposes only what that role may do. A control the user cannot successfully invoke is not displayed. *Derives from FR-03; FR-11's dashboard scope is open.*

**NFR-17 — Errors are actionable.** A refused leave request states why — insufficient balance, or spans two calendar years — rather than failing generically. *Derives from FR-08.*

**NFR-18 — Responsive layout.** The interface is usable at common desktop and tablet widths. *Named in the learning path's frontend module concepts; no target device was specified.*

## Auditability

**NFR-19 — Attribution.** Every leave state transition records who caused it and when. An approved request can be traced to the manager who approved it. *Derives from FR-16.*

## Operability

**NFR-20 — Configuration is environment-supplied.** Secrets, database credentials, and token signing keys come from the environment. None are committed.

**NFR-21 — Reproducible setup.** The project starts from a documented command sequence on a clean machine. A precondition of the learning path's deployment guide.

---

## Explicitly Not Required

Recorded so that their absence reads as a decision rather than an oversight.

High availability. Horizontal scalability. Multi-tenancy. Internationalization and localization. Formal accessibility conformance (WCAG). Rate limiting. Disaster recovery and backup policy. Penetration testing. Performance under concurrent load beyond a handful of users.

Each is a legitimate non-functional requirement for a production leave management system, and none is achievable, or assessable, inside a seven-day trainee project.

## Open

Whether any non-functional requirement is actually being evaluated is unknown, and depends on the evaluation mode — a question for the assigning manager. Should the project be assessed by technical discussion, NFR-03, NFR-04, NFR-07, and NFR-08 are the four most likely to be probed, because each is a place where a working demonstration can conceal a broken system.
