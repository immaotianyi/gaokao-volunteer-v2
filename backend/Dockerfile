FROM python:3.10-slim

WORKDIR /app

# 系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 源代码
COPY . .

# 数据卷挂载点（运行时映射宿主 CSV 目录）
RUN mkdir -p /app/data

EXPOSE 8000

# 生产启动：gunicorn + uvicorn workers
# 开发启动：uvicorn main:app --reload --host 0.0.0.0 --port 8000
CMD ["gunicorn", "main:app", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "-b", "0.0.0.0:8000", \
     "--timeout", "120", \
     "--graceful-timeout", "30"]
