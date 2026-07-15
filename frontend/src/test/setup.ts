/**
 * Vitest global setup (spec-logout — the app's first frontend test harness).
 *
 * Two jobs, run once per test file:
 *   1. Register `@testing-library/jest-dom`'s matchers (`toBeInTheDocument`, …) against
 *      Vitest's `expect`. The `/vitest` entry wires them to Vitest, not Jest.
 *   2. Unmount anything a test rendered, after each test, so one test's DOM never leaks
 *      into the next. Testing Library does not auto-clean under Vitest.
 */
import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

afterEach(() => {
  cleanup()
})
