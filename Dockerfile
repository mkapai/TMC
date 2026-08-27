# 多阶段构建 - 后端
# 可覆盖基础镜像以规避 Docker Hub 500：
#   docker build --build-arg PY_IMAGE=python:3.12.6-slim-bookworm .
ARG PY_IMAGE=python:3.12.6-slim-bookworm
FROM ${PY_IMAGE} AS backend-builder

# 设置构建时代理参数
ARG HTTP_PROXY
ARG HTTPS_PROXY

WORKDIR /build

# 配置apt使用代理（如果提供）
RUN if [ -n "$HTTP_PROXY" ]; then \
        echo "Acquire::http::Proxy \"$HTTP_PROXY\";" > /etc/apt/apt.conf.d/proxy.conf && \
        echo "Acquire::https::Proxy \"$HTTPS_PROXY\";" >> /etc/apt/apt.conf.d/proxy.conf; \
    fi

# 安装系统依赖（使用原始Debian源+代理）
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/* /etc/apt/apt.conf.d/proxy.conf

# 配置pip代理（如果提供）
RUN if [ -n "$HTTP_PROXY" ]; then \
        pip config set global.proxy $HTTP_PROXY; \
    fi

# 复制并安装Python依赖
COPY app/backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 多阶段构建 - 前端
FROM node:18-alpine AS frontend-builder

# 设置构建时代理参数
ARG HTTP_PROXY
ARG HTTPS_PROXY

WORKDIR /build

# 配置npm代理（如果提供）
RUN if [ -n "$HTTP_PROXY" ]; then \
        npm config set proxy $HTTP_PROXY && \
        npm config set https-proxy $HTTPS_PROXY; \
    fi

# 复制并安装Node依赖
COPY app/frontend/package*.json ./
RUN npm install

# 复制版本管理相关文件
COPY VERSION /VERSION
COPY scripts/ /scripts/

# 复制前端代码并构建
COPY app/frontend/ ./

# 设置环境变量并构建
ENV NODE_ENV=production
RUN npm run build

# 最终镜像（与上面保持一致，使用同一基础镜像以减少拉取失败）
FROM ${PY_IMAGE}

# 设置工作目录
WORKDIR /app

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    TZ=Asia/Shanghai

# 安装运行时依赖（使用缓存的包或系统源）
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/* || true

# 从builder复制Python依赖
COPY --from=backend-builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=backend-builder /usr/local/bin /usr/local/bin

# 复制后端代码
COPY app/backend/ /app/

# 复制版本文件到容器
COPY VERSION /app/VERSION

# 从builder复制前端构建产物
COPY --from=frontend-builder /build/dist /app/frontend/dist

# 创建必要的目录
RUN mkdir -p /app/data/message-resources /app/logs /app/sessions /app/temp /app/config

# 复制启动脚本并设置权限
COPY app/backend/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# 暴露端口
EXPOSE 9393

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:9393/health || exit 1

# 启动命令
CMD ["/docker-entrypoint.sh"]
