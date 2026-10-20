#!/bin/bash
# 使用当前项目代码重新构建镜像并更新容器
set -euo pipefail

# 从脚本所在目录运行，确保使用本项目的代码和 Compose 配置
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"

echo "🔨 使用当前代码重新构建镜像..."
docker compose build

echo "🚀 使用新镜像更新容器..."
docker compose up -d --no-build --pull never

echo "📋 查看日志..."
docker compose logs --tail=50

echo "✅ 镜像构建及容器更新命令执行成功"

