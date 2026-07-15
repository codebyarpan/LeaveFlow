/**
 * The document policy, restated for the pre-checks (Story 4.1 AC6; shared home added by the
 * 2026-07-15 code review so the submit panel and the history attach control state ONE copy).
 *
 * A deliberate restatement of `domain/vocabulary.py`'s `DOCUMENT_CONTENT_TYPES` /
 * `DOCUMENT_MAX_BYTES` — the server remains the guard; these only let a refusal state its
 * reason before the round-trip (NFR-17). Drift risk is the accepted app-wide frontend-literal
 * class (deferred-work.md, 2026-07-15).
 */
export const DOCUMENT_ACCEPTED_TYPES = ['application/pdf', 'image/jpeg', 'image/png']
export const DOCUMENT_MAX_BYTES = 5_242_880
