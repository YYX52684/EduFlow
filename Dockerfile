# EduFlow Web 服务镜像
FROM python:3.11-slim

WORKDIR /app

# 系统依赖（解析 docx/pdf 等）
RUN apt-get update && apt-get install -y --no-install-recommends \
    libmagic1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# 不复制 .env，由运行时的 --env-file 注入
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

# 生产运行可不加 --reload
CMD ["python", "run_web.py"]
