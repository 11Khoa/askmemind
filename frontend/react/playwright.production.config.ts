import { defineConfig } from '@playwright/test'
import base from './playwright.config'

export default defineConfig({
  ...base,
  testMatch: 'admin-routing.spec.ts',
  webServer: {
    command: 'node e2e/serve-built-app.mjs',
    url: 'http://127.0.0.1:5184',
  },
})
