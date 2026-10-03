import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/test/setup.ts'],
    exclude: ['node_modules', 'e2e/**'],
    // The default (~one forked jsdom worker per logical CPU) oversubscribes
    // CPU and memory: every test ran 3-25x slower than alone, and whichever
    // was slowest timed out at 5s. Half the cores keeps per-test timing near
    // the isolated numbers and finishes the suite faster overall.
    maxWorkers: '50%',
    coverage: {
      provider: 'v8',
      reporter: ['text', 'lcov'],
      include: ['src/**/*.{ts,tsx}'],
      exclude: ['src/test/**', 'src/main.tsx', 'src/**/*.d.ts'],
      // Not a quality bar — frontend coverage (~10%, re-measured
      // 2026-08-02) is a documented, accepted gap (see docs/TESTING.md),
      // not a target to gate hard on. This floor exists only to fail CI on
      // a catastrophic regression (e.g. tests accidentally deleted), well
      // below the current number.
      thresholds: {
        lines: 7,
        statements: 7,
        functions: 6,
        branches: 8,
      },
    },
  },
})
