/**
 * The React entrypoint.
 *
 * Implements: AC8 (Vite + React + TypeScript SPA with TanStack Query).
 *
 * `createRoot` from `react-dom/client` remains correct on React 19.
 */
import { QueryClientProvider } from '@tanstack/react-query'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'

import { queryClient } from './api'
import { App } from './App'
import './index.css'

const container = document.getElementById('root')

if (!container) {
  throw new Error('No #root element: index.html and main.tsx disagree about the mount point.')
}

createRoot(container).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
)
