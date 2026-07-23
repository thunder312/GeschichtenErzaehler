import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    port: 5173,
    proxy: {
      // Backend laeuft separat unter uvicorn (Standard: Port 8000). Der
      // Proxy erspart CORS-Handling im Dev-Betrieb fuer normale Requests;
      // WebSockets (ws: true) fuer den streamenden Schreiben-Schritt.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
        ws: true,
      },
    },
  },
})
