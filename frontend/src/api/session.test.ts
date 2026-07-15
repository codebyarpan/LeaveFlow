/**
 * Unit tests for the session token store (spec-logout).
 *
 * `clearToken` is the pure core of logout: it must forget the token in BOTH homes — the
 * in-memory `memoryToken` that `apiFetch` reads, and the `localStorage` copy that would
 * otherwise rehydrate the session on the next reload. These tests pin that, plus the
 * defensive contract that a denied `localStorage` write never throws out of the store.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clearToken, getToken, setToken, TOKEN_STORAGE_KEY } from './session'

describe('session token store', () => {
  beforeEach(() => {
    localStorage.clear()
    clearToken()
  })

  afterEach(() => {
    vi.restoreAllMocks()
    localStorage.clear()
    clearToken()
  })

  it('setToken persists to memory and localStorage; getToken reads it back', () => {
    setToken('abc.def.ghi')

    expect(getToken()).toBe('abc.def.ghi')
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBe('abc.def.ghi')
  })

  it('clearToken forgets the token in memory and removes the storage key', () => {
    setToken('abc.def.ghi')

    clearToken()

    expect(getToken()).toBeNull()
    expect(localStorage.getItem(TOKEN_STORAGE_KEY)).toBeNull()
  })

  it('clearToken still clears memory when localStorage.removeItem throws (storage denied)', () => {
    setToken('abc.def.ghi')
    vi.spyOn(Storage.prototype, 'removeItem').mockImplementation(() => {
      throw new DOMException('denied', 'SecurityError')
    })

    expect(() => clearToken()).not.toThrow()
    // Memory is authoritative for the live session, so the user is signed out for this
    // page load even though the persisted copy could not be removed.
    expect(getToken()).toBeNull()
  })

  it('setToken keeps the live session when localStorage.setItem throws (quota/denied)', () => {
    vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('quota', 'QuotaExceededError')
    })

    expect(() => setToken('abc.def.ghi')).not.toThrow()
    expect(getToken()).toBe('abc.def.ghi')
  })
})
