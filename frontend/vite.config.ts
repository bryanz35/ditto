/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// Ports come from API_PORT / WEB_PORT via `make dev`.
const apiPort = process.env.API_PORT ?? '8000'

export default defineConfig({
  plugins: [react()],
  // the device test reads the fixture's assembly.glb with ?inline
  assetsInclude: ['**/*.glb'],
  server: {
    port: Number(process.env.WEB_PORT ?? 5173),
    strictPort: true,
    // Tests import the shared fixtures with ?raw; allow only that folder outside frontend/.
    fs: { allow: ['.', '../fixtures'] },
    // The UI calls /api/...; the API serves the same routes without the prefix (/runs, /memory, ...).
    proxy: {
      '/api': {
        target: `http://127.0.0.1:${apiPort}`,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
  test: { environment: 'jsdom' },
})
