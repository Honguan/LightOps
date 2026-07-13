import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import packageJson from './package.json'

export default defineConfig({
  define: {
    __APP_VERSION__: JSON.stringify(packageJson.version),
  },
  plugins: [vue()],
  server: {
    proxy: {
      '/api': 'http://127.0.0.1:9080',
    },
  },
  build: {
    outDir: 'dist',
  },
})
