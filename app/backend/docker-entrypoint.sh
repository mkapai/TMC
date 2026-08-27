#!/bin/bash
set -e

echo "🚀 TMC 启动中..."

# 创建必需的目录
mkdir -p /app/{data/message-resources,logs,sessions,temp,config}

# 设置数据库URL
export DATABASE_URL="${DATABASE_URL:-sqlite:////app/data/bot.db}"
DB_FILE="/app/data/bot.db"
MIGRATION_TIMEOUT_SECONDS="${MIGRATION_TIMEOUT_SECONDS:-120}"

case "$MIGRATION_TIMEOUT_SECONDS" in
    ''|*[!0-9]*)
        echo "❌ MIGRATION_TIMEOUT_SECONDS 必须是正整数"
        exit 1
        ;;
    0)
        echo "❌ MIGRATION_TIMEOUT_SECONDS 必须大于 0"
        exit 1
        ;;
esac

cd /app

if ! ALEMBIC_HEAD_VERSION=$(python3 - <<'PY'
from alembic.config import Config
from alembic.script import ScriptDirectory

heads = ScriptDirectory.from_config(Config("/app/alembic.ini")).get_heads()
if len(heads) != 1:
    raise RuntimeError(f"预期一个 Alembic head，实际为: {heads}")
print(heads[0])
PY
); then
    echo "❌ 无法读取 Alembic 最新版本，请确认镜像包含 Alembic 和迁移文件"
    exit 1
fi

run_database_migration() {
    echo "   ├─ 目标版本: $ALEMBIC_HEAD_VERSION"
    echo "   ├─ 执行数据库迁移（最长 ${MIGRATION_TIMEOUT_SECONDS} 秒）..."

    if timeout --signal=TERM --kill-after=10s \
        "${MIGRATION_TIMEOUT_SECONDS}s" python3 -u -m alembic upgrade head; then
        return 0
    else
        migration_exit=$?
    fi

    if [ "$migration_exit" -eq 124 ]; then
        echo "❌ 数据库迁移超时，通常是数据库文件锁或挂载存储 I/O 异常"
    else
        echo "❌ 数据库迁移失败，退出码: $migration_exit"
    fi
    return "$migration_exit"
}

# ========== 数据库初始化 ==========
echo ""
echo "📦 数据库初始化"

if [ -f "$DB_FILE" ]; then
    echo "   ├─ 检测到已有数据库"

    # 检查 Alembic 版本表
    CURRENT_VERSION=$(python3 -c "
import sqlite3
try:
    conn = sqlite3.connect('$DB_FILE')
    cursor = conn.cursor()
    cursor.execute('SELECT version_num FROM alembic_version LIMIT 1')
    print(cursor.fetchone()[0])
except:
    print('none')
" 2>/dev/null)
    
    if [ "$CURRENT_VERSION" = "none" ]; then
        echo "   ├─ ⚠️  数据库缺少版本信息"
        echo "   ├─ 尝试自动迁移..."
    else
        echo "   ├─ 当前版本: $CURRENT_VERSION"
    fi

    if [ "$CURRENT_VERSION" = "$ALEMBIC_HEAD_VERSION" ]; then
        echo "   └─ ✅ 数据库已是最新版本，跳过迁移"
    else
        BACKUP_FILE="${DB_FILE%.db}_backup_$(date +%Y%m%d_%H%M%S).db"
        echo "   ├─ 迁移前备份: $BACKUP_FILE"
        DB_FILE="$DB_FILE" BACKUP_FILE="$BACKUP_FILE" python3 - <<'PY'
import os
import sqlite3

source = sqlite3.connect(os.environ["DB_FILE"])
backup = sqlite3.connect(os.environ["BACKUP_FILE"])
try:
    source.backup(backup)
finally:
    backup.close()
    source.close()
PY

        if run_database_migration; then
            echo "   └─ ✅ 数据库迁移成功"
        else
            migration_exit=$?
            echo "   └─ 迁移前备份已保留: $BACKUP_FILE"
            exit "$migration_exit"
        fi
    fi
else
    echo "   ├─ 未检测到数据库"
    echo "   ├─ 创建全新数据库..."

    # 使用 Alembic 创建数据库
    if run_database_migration; then
        echo "   └─ ✅ 数据库创建成功（新数据库无需修复）"
    else
        migration_exit=$?
        exit "$migration_exit"
    fi
fi

# 初始化管理员（静默失败）
python3 init_admin.py 2>/dev/null || true

# 启动应用
echo ""
echo "✅ 启动成功"
export AUTO_MIGRATE=false
exec uvicorn main:app --host 0.0.0.0 --port 9393 --workers 1
