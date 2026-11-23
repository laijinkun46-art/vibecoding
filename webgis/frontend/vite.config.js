import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  define: { CESIUM_BASE_URL: JSON.stringify('/cesium/') },
  server: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  preview: { proxy: { '/api': 'http://127.0.0.1:8000' } },
  build: {
    // Cesium 自身较大，单独分块以便缓存；不影响地图功能。
    rolldownOptions: {
      output: { codeSplitting: { groups: [{ name: 'cesium', test: /node_modules[\\/](?:@cesium|cesium)[\\/]/ }] } },
    },
    chunkSizeWarningLimit: 5000,
  },
})
