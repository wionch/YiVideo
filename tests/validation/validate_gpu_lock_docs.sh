#!/bin/bash
# GPU锁文档与配置一致性验证脚本
# 简化版 - 使用 grep 提取配置值
# 作者: Claude Code
# 创建日期: 2025-12-24

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

DOC_FILE="docs/technical/reference/GPU_LOCK_COMPLETE_GUIDE.md"
CONFIG_FILE="config.yml"

echo "🔍 验证 GPU 锁文档与配置一致性..."
echo ""

# 检查文件
if [ ! -f "$DOC_FILE" ] || [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${RED}❌ 错误: 文件不存在${NC}"
    exit 1
fi

errors=0

# 提取并对比 poll_interval
doc_val=$(grep "poll_interval:" "$DOC_FILE" | head -1 | grep -oP '\d+(\.\d+)?' | head -1)
cfg_val=$(grep -A 20 "^gpu_lock:" "$CONFIG_FILE" | grep "poll_interval:" | grep -oP '\d+(\.\d+)?' | head -1)
if [ "$doc_val" != "$cfg_val" ]; then
    echo -e "${RED}❌ poll_interval 不一致: 文档=$doc_val, 配置=$cfg_val${NC}"
    ((errors++))
else
    echo -e "${GREEN}✅ poll_interval 一致 ($doc_val)${NC}"
fi

# 提取并对比 max_wait_time
doc_val=$(grep "max_wait_time:" "$DOC_FILE" | head -1 | grep -oP '\d+' | head -1)
cfg_val=$(grep -A 20 "^gpu_lock:" "$CONFIG_FILE" | grep "max_wait_time:" | grep -oP '\d+' | head -1)
if [ "$doc_val" != "$cfg_val" ]; then
    echo -e "${RED}❌ max_wait_time 不一致: 文档=$doc_val, 配置=$cfg_val${NC}"
    ((errors++))
else
    echo -e "${GREEN}✅ max_wait_time 一致 ($doc_val)${NC}"
fi

# 提取并对比 lock_timeout
doc_val=$(grep "lock_timeout:" "$DOC_FILE" | head -1 | grep -oP '\d+' | head -1)
cfg_val=$(grep -A 20 "^gpu_lock:" "$CONFIG_FILE" | grep "lock_timeout:" | grep -oP '\d+' | head -1)
if [ "$doc_val" != "$cfg_val" ]; then
    echo -e "${RED}❌ lock_timeout 不一致: 文档=$doc_val, 配置=$cfg_val${NC}"
    ((errors++))
else
    echo -e "${GREEN}✅ lock_timeout 一致 ($doc_val)${NC}"
fi

# 提取并对比 max_poll_interval
doc_val=$(grep "max_poll_interval:" "$DOC_FILE" | head -1 | grep -oP '\d+' | head -1)
cfg_val=$(grep -A 20 "^gpu_lock:" "$CONFIG_FILE" | grep "max_poll_interval:" | grep -oP '\d+' | head -1)
if [ "$doc_val" != "$cfg_val" ]; then
    echo -e "${RED}❌ max_poll_interval 不一致: 文档=$doc_val, 配置=$cfg_val${NC}"
    ((errors++))
else
    echo -e "${GREEN}✅ max_poll_interval 一致 ($doc_val)${NC}"
fi

echo ""
if [ $errors -eq 0 ]; then
    echo -e "${GREEN}✅ 所有验证通过!${NC}"
    exit 0
else
    echo -e "${RED}❌ 发现 $errors 个不一致${NC}"
    exit 1
fi
