#!/bin/bash
# 安装每日数据更新 cron 任务（macOS/Linux）
# 每天北京时间 07:00 执行

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
PYTHON_SCRIPT="$PROJECT_DIR/backend/scripts/daily_update.py"
LOG_DIR="$PROJECT_DIR/logs"

# 创建日志目录
mkdir -p "$LOG_DIR"

# 查找 Python
PYTHON=$(which python3 2>/dev/null || which python 2>/dev/null)

# 构建 cron 命令
CRON_CMD="0 7 * * * cd $PROJECT_DIR && $PYTHON $PYTHON_SCRIPT >> $LOG_DIR/daily_update.log 2>&1"

echo "==============================================="
echo "  安装每日数据更新 cron 任务"
echo "==============================================="
echo ""
echo "Cron 命令:"
echo "  $CRON_CMD"
echo ""
echo "添加到 crontab..."
echo ""

# 检查是否已存在
EXISTING=$(crontab -l 2>/dev/null | grep "daily_update.py" || true)

if [ -n "$EXISTING" ]; then
    echo "⚠️  已存在 daily_update 任务，跳过安装。"
    echo "  现有任务: $EXISTING"
    echo ""
    echo "如需更新，请手动编辑 crontab:"
    echo "  crontab -e"
else
    # 添加新任务
    (crontab -l 2>/dev/null; echo "$CRON_CMD") | crontab -
    echo "✅ Cron 任务已安装成功！"
    echo ""
    echo "验证安装:"
    crontab -l | grep daily_update
fi

echo ""
echo "手动测试运行:"
echo "  $PYTHON $PYTHON_SCRIPT"
echo "  $PYTHON $PYTHON_SCRIPT --dry-run  # 仅对比差异"
echo ""
echo "查看日志:"
echo "  tail -f $LOG_DIR/daily_update.log"
