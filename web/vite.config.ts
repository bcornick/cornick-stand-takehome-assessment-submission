// ABOUTME: Vite configuration for the web app: React, Tailwind, the @ alias and the dev proxy.
// ABOUTME: The dev server forwards /api to the app at UWH_API_URL.
import path from 'node:path'
import tailwindcss from '@tailwindcss/vite'
import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), 'UWH_')
  const apiUrl = process.env.UWH_API_URL ?? env.UWH_API_URL ?? 'http://localhost:8000'
  return {
    plugins: [react(), tailwindcss()],
    resolve: {
      alias: { '@': path.resolve(import.meta.dirname, './src') },
    },
    server: {
      proxy: { '/api': { target: apiUrl, changeOrigin: true } },
    },
  }
})
