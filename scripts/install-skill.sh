#!/bin/bash
# Depot Agent Skill 安装脚本
# 一键安装: bash <(curl -sL https://raw.githubusercontent.com/canglang007/depot-agent/main/scripts/install-skill.sh)

set -e

SKILL_DIR="$HOME/.claude/skills/depot-agent"
SKILL_URL="https://raw.githubusercontent.com/canglang007/depot-agent/main/skills/SKILL.md"

echo "== 安装 depot-agent Skill =="
echo ""

# 安装 depot-agent
echo "[1/3] 安装 depot-agent 包..."
pip install depot-agent --quiet 2>/dev/null && echo "  ✅ depot-agent 已安装 (PyPI)" || {
    pip install git+https://github.com/canglang007/depot-agent.git --quiet 2>/dev/null && echo "  ✅ depot-agent 已安装 (GitHub)" || {
        echo "  ❌ 安装失败"
        exit 1
    }
}

# 安装 Skill 文件
echo "[2/3] 安装 Skill 定义..."
mkdir -p "$SKILL_DIR"
if curl -sL "$SKILL_URL" -o "$SKILL_DIR/SKILL.md"; then
    echo "  ✅ Skill 已安装到 $SKILL_DIR"
else
    echo "  ❌ 下载 SKILL.md 失败"
    exit 1
fi

# 验证
echo "[3/3] 验证安装..."
if depot check -c "import os; print('OK')" 2>/dev/null | grep -q "成功"; then
    echo "  ✅ Depot CLI 正常工作"
else
    echo "  ⚠️ Depot CLI 验证失败，但 Skill 已安装"
fi

echo ""
echo "======== 安装完成 ========"
echo ""
echo "使用方式:"
echo "  Claude Code: 输入 /depot-agent 调用 Skill"
echo "  命令行:      depot run script.py"
echo "  Python SDK:  from depot.sdk import execute"
echo ""
