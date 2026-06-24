# ===== Stage 1: Build =============================================
FROM node:20-alpine AS build-stage

WORKDIR /app

# 拷贝依赖声明文件
COPY package.json ./

# 安装依赖（--legacy-peer-deps 避免 peer dep 冲突）
RUN npm install --legacy-peer-deps

# 拷贝全部源码
COPY . .

# 构建 H5 产物（输出到 dist/）
# VITE_API_BASE_URL 留空 → 前端走相对路径 /api，由 nginx 反代到 backend
ENV VITE_API_BASE_URL=""
RUN npm run build

# ===== Stage 2: Serve (Nginx) ======================================
FROM nginx:alpine AS serve-stage

# 移除默认首页和默认配置
RUN rm -rf /usr/share/nginx/html/* /etc/nginx/conf.d/default.conf

# 拷贝构建产物
COPY --from=build-stage /app/dist /usr/share/nginx/html

# 拷贝自定义 Nginx 配置
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
