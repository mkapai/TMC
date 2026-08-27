# 使用Python 3.11官方镜像
FROM python:3.11-slim

# 设置构建时的代理参数（用于下载依赖）
ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG NO_PROXY

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 如果提供了代理，配置pip使用代理
RUN if [ -n "$HTTP_PROXY" ]; then \
        pip config set global.proxy $HTTP_PROXY; \
    fi

# 安装系统依赖
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 复制依赖文件
COPY requirements.txt .

# 安装Python依赖（使用构建时代理）
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建必要的目录
RUN mkdir -p /app/data/message-resources /app/logs /app/sessions /app/temp /app/config

# 暴露端口
EXPOSE 9393

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:9393/health || exit 1

# 启动命令
CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "9393"]
