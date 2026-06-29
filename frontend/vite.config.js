import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Build output goes straight into the Flask package's static folder so:
//   - `npm run build` always leaves drawbridge/static ready to serve, for
//     local "build once and check it" testing without a container, and
//   - the Containerfile's frontend-build stage copies from the same path
//     it would land in locally (see docs/frontend.md).
export default defineConfig({
  plugins: [vue()],
  build: {
    outDir: '../drawbridge/static',
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:8080',
      '/scripts': 'http://127.0.0.1:8080',
      '/health': 'http://127.0.0.1:8080',
    },
  },
})
