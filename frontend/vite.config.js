import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// Vite 开发配置：本地开发时通过代理转发 /api 到 FastAPI（默认 8000 端口）
export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,
    // 固定监听 IPv4，避免默认绑定 ::1 导致 127.0.0.1 无法访问
    host: '127.0.0.1',
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
