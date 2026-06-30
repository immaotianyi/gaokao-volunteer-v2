import { defineConfig } from "vite";
import vue from "@vitejs/plugin-vue";
import path from "path";

export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "."),
    },
  },
  server: {
    host: "0.0.0.0",
    port: 5173,
    proxy: {
      // 仅代理后端 API 请求；前端模块文件 /api/index.ts 必须跳过
      "/api": {
        target: "http://localhost:8000",
        changeOrigin: true,
        bypass(req) {
          if (/\.(ts|js|vue|css|html|json|map)$/.test(req.url)) return req.url;
        },
      },
      "/sse": {
        target: "http://localhost:8000",
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      output: {
        // 拆分 three.js 到独立 chunk，避免主包体积膨胀
        manualChunks: {
          three: ["three"],
        },
      },
    },
  },
});
