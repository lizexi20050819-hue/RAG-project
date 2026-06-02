FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# 系统依赖（pdf/docx 解析通常不需要额外系统库；保留基础构建工具以防某些依赖需要编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY 1 /app/1

WORKDIR /app/1

EXPOSE 8000

# 默认启动 API（可在 docker-compose 里覆盖）
CMD ["uvicorn", "api_app:app", "--host", "0.0.0.0", "--port", "8000"]

