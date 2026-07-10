# Review — Version & Currency Lens

**Target:** `ARCHITECTURE-SPINE.md` (LeaveFlow, 2026-07-10)
**Lens:** Verify every committed decision was web-researched or reality-checked rather than asserted from training data — current library/framework versions, that each named technology still exists and fits, and (greenfield) the live defaults of any starter it leans on.
**Reviewed:** 2026-07-10, against PyPI JSON, npm registry, PostgreSQL.org, and vendor docs.
**Verdict:** PASS with minor notes. Every row of the Stack table is real and current as of today, the `uuidv7()`/PG18 dependency (the one HIGH-risk item) is genuinely native, and all three grounds for rejecting `full-stack-fastapi-template` still hold in the template's current state. The only inaccuracy is a characterization issue around `python-jose` and a conservative-but-N-1 Python pin.

---

## 1. Stack table — every row checked against the live registry

Method: `https://pypi.org/pypi/<pkg>/json` (`info.version`) and `https://registry.npmjs.org/<pkg>` (`dist-tags.latest`), fetched 2026-07-10.

| Spine claim | Registry latest (2026-07-10) | Result |
| --- | --- | --- |
| Python 3.13 | 3.14.6 is current stable (3.14.0 GA 2025-10-07) | **REAL, but N-1** — see Finding F3 |
| FastAPI 0.139.0 | 0.139.0 | ✅ exact match, current |
| Pydantic 2.13.4 | 2.13.4 | ✅ exact match, current |
| SQLAlchemy 2.0.51 | 2.0.51 (stable); 2.1 only at `2.1.0b3` | ✅ current, and confirms the "2.1 still beta" note |
| Alembic 1.18.5 | 1.18.5 | ✅ exact match, current |
| psycopg 3.3.4 | 3.3.4 | ✅ exact match, current |
| PostgreSQL 18 | major 18 current (patch 18.4); 19 only Beta 1 (2026-06-04) | ✅ current major |
| PyJWT 2.13.0 | 2.13.0 | ✅ exact match, current |
| pwdlib 0.3.0 | 0.3.0 (uploaded 2025-10-25) | ✅ exact match, current |
| bcrypt 5.0.0 | 5.0.0 | ✅ exact match, current |
| pytest 9.1.1 | 9.1.1 | ✅ exact match, current |
| React 19.2.7 | 19.2.7 | ✅ exact match, current |
| Vite 8.1.4 | 8.1.4 | ✅ exact match, current |
| TypeScript 6.0.3 | latest is 7.0.2; 6.0.3 is the **last stable 6.x** (2026-04-16) | ✅ correct conservative pin — see item 4 |
| TanStack Query 5.101.2 | `@tanstack/react-query` 5.101.2 | ✅ exact match, current |

No row is stale, yanked, misstated, or nonexistent. The Stack section's header claim ("Verified current on 2026-07-10 against PyPI, the npm registry, and official release pages") is itself accurate — this is not an asserted-from-memory table.

Sources: `https://pypi.org/pypi/fastapi/json`, `.../pydantic/json`, `.../sqlalchemy/json`, `.../alembic/json`, `.../psycopg/json`, `.../pyjwt/json`, `.../pwdlib/json`, `.../bcrypt/json`, `.../pytest/json`; `https://registry.npmjs.org/react`, `.../vite`, `.../typescript`, `.../@tanstack/react-query`.

---

## 2. Rejected libraries

### `passlib` — spine claim CONFIRMED (no finding)
Spine (AD-14): "`passlib` is not used, being unmaintained since 2020 and broken against modern bcrypt."
- PyPI `passlib` latest = **1.7.4, uploaded 2020-10-08** — no release in ~6 years. "Unmaintained since 2020" is exactly right. (`https://pypi.org/pypi/passlib/json`)
- "Broken against modern bcrypt" is real and, notably, bites the *exact* bcrypt the spine pins: passlib 1.7.4's backend fails against **bcrypt 5.0.0** (which removed `__about__`), producing a misleading `ValueError: password cannot be longer than 72 bytes`. See pyca/bcrypt #1079 and #684. (`https://github.com/pyca/bcrypt/issues/1079`)
- Rejecting passlib in favor of `pwdlib` is well-justified.

### `python-jose` — CVE history real, but "stale" is inaccurate → Finding F2
Spine (AD-14) text only says "`python-jose` is not used" (the review brief frames the rationale as "stale with a CVE history").
- CVE history is real and serious: **CVE-2024-33663** (algorithm confusion, CVSS 9.3) and **CVE-2024-33664** (DoS via compressed JWT). Ample reason to prefer PyJWT. (`https://github.com/advisories/GHSA-6c5p-j8vq-pqhj`)
- BUT "stale" would be wrong: PyPI `python-jose` latest = **3.5.0, uploaded 2025-05-28** — a release ~13 months ago that post-dates and remediates the CVEs (fixed in 3.4.0). (`https://pypi.org/pypi/python-jose/json`)
- Net: the *decision* (use PyJWT) is sound; only the "abandoned/stale" framing is unsupportable. The spine text avoids the word, so this is low-impact — a caution against anyone restating the rejection as "python-jose is dead."

---

## 3. `SQLAlchemy 2.1 is still beta` — CONFIRMED (no finding)
Spine: "SQLAlchemy is pinned to the 2.0 line because 2.1 is still beta."
- PyPI shows the entire 2.1 line as pre-release only: `2.1.0b1`, `2.1.0b2`, `2.1.0b3`. `info.version` (latest stable) = **2.0.51**. No 2.1 final exists. (`https://pypi.org/pypi/sqlalchemy/json`)

---

## 4. TypeScript 7.0.2 = Go rewrite, shipped ~2026-07-08; 6.0.3 the last 6.x — CONFIRMED (no finding)
Spine: "TypeScript is pinned to 6.0.3 rather than the two-day-old 7.0.2 (the Go rewrite)."
- npm `typescript` `dist-tags.latest` = **7.0.2**, published **2026-07-08T15:55Z** (`time["7.0.2"]`) — exactly "two days old" relative to today (2026-07-10). The 7.x line is the native/Go port ("Project Corsa" → TypeScript 7). (`https://registry.npmjs.org/typescript`)
- **6.0.3 is real and is the highest stable 6.x**: the only stable 6.x releases are 6.0.2 and 6.0.3 (everything else in 6.x is `-dev`/`-rc`/`-beta`); 6.0.3 published **2026-04-16**. So 6.0.3 is a real, sensible conservative pin and genuinely the last 6.x. (`https://registry.npmjs.org/typescript`)

---

## 5. PostgreSQL 18 + native `uuidv7()` — CONFIRMED (the HIGH-risk item passes)
Spine Conventions: "UUID primary keys generated by PostgreSQL 18's native `uuidv7()`."
- PostgreSQL 18 is a real, current major (GA 2025-09-25; patch line at 18.4; PG19 only at Beta 1). (`https://www.postgresql.org/docs/current/release-18.html`)
- **`uuidv7()` is a genuine core function in PG18** — added to the server, no `uuid-ossp`/`pgcrypto` extension required, generating RFC 9562 v7 time-ordered UUIDs (PG18 also added `uuidv4()` as an alias of `gen_random_uuid()`). The Conventions table's dependency is sound. (`https://www.postgresql.org/docs/current/release-18.html`, `https://neon.com/postgresql/18/uuidv7-support`)

This was flagged as potentially HIGH if false; it is true, so **no finding**.

---

## 6. `pwdlib` real/maintained/bcrypt+Argon2 — CONFIRMED (no finding)
- PyPI `pwdlib` latest = **0.3.0, uploaded 2025-10-25** (active). Package metadata declares `provides_extra: ["argon2", "bcrypt"]` and the description states it aims to "support modern and secure algorithms like Argon2 or Bcrypt." Both algorithms supported; version matches the Stack table. (`https://pypi.org/pypi/pwdlib/json`)

---

## 7. `psycopg 3.3.4` + SQLAlchemy 2.0 — CONFIRMED (no finding)
- psycopg 3.3.4 is the current psycopg3 release (`info.version` = 3.3.4). SQLAlchemy 2.0 ships a first-class native psycopg (v3) dialect (`postgresql+psycopg://`), so psycopg3 with SQLAlchemy 2.0.51 is a fully supported, sane pairing. (`https://pypi.org/pypi/psycopg/json`)

---

## 8. React 19.2.7 / Vite 8.1.4 / TanStack Query 5.101.2 — CONFIRMED (no finding)
All three are the current `dist-tags.latest` on npm as of 2026-07-10 (see the Stack table above). React `latest` = 19.2.7, Vite `latest` = 8.1.4, `@tanstack/react-query` `latest` = 5.101.2.

---

## 9. `full-stack-fastapi-template` rejection rationale — still CURRENT (no finding)
Spine declines the template because it ships (a) SQLModel fusing Pydantic schema and SQLAlchemy table, (b) email password recovery, and (c) Traefik. Checked the template's live `master` README:
- **SQLModel** — still present: "SQLModel for the Python SQL database interactions (ORM)." ✅
- **Email password recovery** — still present: "Email based password recovery." ✅
- **Traefik** — still present: "Traefik as a reverse proxy / load balancer." ✅

All three grounds hold against the template's current state, so the rejection rationale is **not** stale. (The template has since added Tailwind/shadcn on the frontend, but that does not touch any of the three cited grounds.) (`https://github.com/fastapi/full-stack-fastapi-template` — `README.md` on `master`)

---

## 10. Technologies named but not in the Stack table
| Named where | Technology | Status |
| --- | --- | --- |
| Conventions → Configuration | `pydantic-settings` | Real, current (latest 2.14.2), actively maintained. **Unpinned** in the spine — acceptable for a spine, but no version was asserted so nothing is stale. (`https://pypi.org/pypi/pydantic-settings/json`) |
| Structural Seed diagram | `uvicorn` | Real, current (latest 0.51.0). Unpinned. (`https://pypi.org/pypi/uvicorn/json`) |
| Stack + deploy steps | Alembic (`alembic upgrade head`) | Version 1.18.5 in Stack (current); usage is standard. ✅ |
| Deployment | Docker Compose (`docker compose up`) | Standard Compose v2 CLI; current. ✅ |

None of these introduce a stale or nonexistent dependency. Only observation: `pydantic-settings` and `uvicorn` are named without a pinned version, but the spine explicitly defers exact pins to "the code" once it exists, so this is by design rather than an oversight.

---

## Findings, ranked

**F1 — LOW (informational): `python-jose` rejection is sound but must not be restated as "stale."**
The CVEs are real (CVE-2024-33663, CVSS 9.3), but `python-jose` shipped 3.5.0 on 2025-05-28, so it is not abandoned. The spine's actual text ("python-jose is not used") is fine; only a "stale"/"dead" framing would be inaccurate. `https://pypi.org/pypi/python-jose/json`

**F2 — LOW: `Python 3.13` is one major behind the current stable (3.14.6).**
Python 3.14.0 went GA 2025-10-07 and 3.14.6 is out (2026-06-10). 3.13 is fully supported and a defensible conservative pin, but it is N-1, not the latest; the Stack header's "verified current" is technically an N-1 choice here rather than "the current version." Recommend a one-line note that 3.13 is a deliberate pin, not the newest. `https://www.python.org/downloads/release/python-3146/`

**F3 — INFORMATIONAL: PostgreSQL major is stated as bare `18`.**
Correct as the current major (19 is only Beta 1), and a bare major is the right granularity for pinning a DB engine; noted only for completeness — the running patch line is 18.4. `https://www.postgresql.org/docs/current/release-18.html`

No critical, high, or medium findings. Every load-bearing currency claim — the Stack versions, `uuidv7()` being native to PG18, SQLAlchemy 2.1 being beta, TypeScript 7 being the ~2-day-old Go rewrite with 6.0.3 as the last 6.x, `pwdlib`'s bcrypt/Argon2 support, `passlib` being unmaintained-and-broken, and the `full-stack-fastapi-template` still shipping SQLModel + email recovery + Traefik — was verified against the live web and holds.

## Nothing left UNVERIFIED
Every item in the review brief was confirmed against a live source. The only claim I did not hit a dedicated URL for is the identity "TypeScript 7 = the Go/native rewrite" as a semantic fact; it is corroborated by the npm `dist-tags` (7.0.2 latest, 7.1.0-dev next) and is well-established public record, and the spine's version/date facts around it (7.0.2, 2026-07-08, two days old) are all independently verified.
