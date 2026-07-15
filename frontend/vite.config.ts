/**
 * Vite configuration.
 *
 * Implements: AC8 (Vite + React + TypeScript SPA), AC1, NFR-18.
 *
 * Vite 8 is Rolldown-based, not Rollup + esbuild. Should this file ever grow build
 * options, the names have moved: `build.rollupOptions` -> `build.rolldownOptions`,
 * top-level `esbuild` -> `oxc`, `optimizeDeps.esbuildOptions` ->
 * `optimizeDeps.rolldownOptions`. `@vitejs/plugin-react` 6.x is the matching plugin.
 */
import { fileURLToPath } from 'node:url'

import react from '@vitejs/plugin-react'
import { loadEnv } from 'vite'
// `defineConfig` comes from `vitest/config`, not `vite`: it is the same helper widened
// with the `test` field's types, so the block below type-checks. It re-exports Vite's,
// so the plugin/server config is unchanged.
import { defineConfig } from 'vitest/config'

export default defineConfig(({ mode }) => {
  // Where `npm run dev` forwards API calls. Defaults to the TLS proxy that
  // `docker compose up` starts, because that is the documented way to run LeaveFlow.
  //
  // `loadEnv` against the REPOSITORY ROOT, because that is where `.env` declares
  // PROXY_HTTPS_PORT — Vite does not read `../.env` into `process.env` on its own,
  // so a bare `process.env.PROXY_HTTPS_PORT` was never populated. The empty prefix
  // loads every variable for use HERE, in config scope; nothing beyond the usual
  // `VITE_`-prefixed set is exposed to client code.
  const env = loadEnv(mode, fileURLToPath(new URL('..', import.meta.url)), '')

  const apiProxyTarget =
    env.VITE_API_PROXY_TARGET ?? `https://localhost:${env.PROXY_HTTPS_PORT ?? '8443'}`

  return {
    plugins: [react()],
    // Vitest (spec-logout — the app's first frontend tests). `jsdom` gives components a DOM
    // to render into; `globals: true` exposes `describe`/`it`/`expect`/`vi` without imports;
    // the setup file registers jest-dom matchers and cleans up between tests.
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./src/test/setup.ts'],
    },
    server: {
      proxy: {
        '/api/v1': {
          target: apiProxyTarget,
          changeOrigin: true,
          // The proxy presents a self-signed certificate in local development.
          // Affects `npm run dev` only; this is not a runtime setting, and the built
          // bundle never sees it.
          secure: false,

          // THERE IS DELIBERATELY NO `rewrite` HERE.
          //
          // The backend already serves under `/api/v1` — FastAPI mounts the v1 router at
          // that prefix, and the production nginx proxy passes the prefix through
          // untouched. Stripping it in development would leave every path in
          // api-contracts correct in exactly one of the two environments.
        },
      },
    },
  }
})
