import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // The browser only ever talks to localhost:5173, so requests are
      // same-origin and CORS never enters the picture. It also lets the app use
      // relative URLs, which are then identical in dev and in production.
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
