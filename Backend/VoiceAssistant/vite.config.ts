import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// Reads the backend's .env but only exposes NEXT_PUBLIC_* names to browser code;
// server secrets never match that prefix, so they are never bundled.
const ENV_DIR = '..'
const ENV_PREFIX = 'NEXT_PUBLIC_'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, ENV_DIR, ENV_PREFIX)
  const appUrl = env.NEXT_PUBLIC_APP_URL
  const port = appUrl ? Number(new URL(appUrl).port) || 5173 : 5173
  return {
    plugins: [react()],
    envDir: ENV_DIR,
    envPrefix: ENV_PREFIX,
    server: { port },
  }
})
