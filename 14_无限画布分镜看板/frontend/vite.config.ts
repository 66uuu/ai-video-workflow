import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

// build 后用 server.py 直接 serve dist，base 用相对路径；
// dev 时把 /api 代理到本机 8080（server.py 的默认端口）。
export default defineConfig({
  plugins: [react()],
  base: './',
  server: {
    port: 5173,
    proxy: {
      '/api': 'http://127.0.0.1:8080'
    }
  }
})