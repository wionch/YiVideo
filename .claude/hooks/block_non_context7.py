#!/usr/bin/env python3
"""
Context7 强制使用工具
拦截 WebSearch/WebFetch 的库文档查询，引导使用 Context7 MCP
"""
import json
import sys
import re

# 配置
LIBRARY_KEYWORDS = [
    r'\bdocumentation\b', r'\bdocs\b', r'\bapi\s+reference\b', 
    r'\bofficial\s+guide\b', r'\btutorial\b',
    r'\breact\b', r'\bvue\b', r'\bangular\b', r'\bsvelte\b',
    r'\bdjango\b', r'\bflask\b', r'\bfastapi\b', r'\bexpress\b',
    r'\bpandas\b', r'\bnumpy\b', r'\btensorflow\b', r'\bpytorch\b',
    r'\bnext\.?js\b', r'\bnuxt\b', r'\btailwind\b', r'\bbootstrap\b',
    r'\btypescript\b', r'\bwebpack\b', r'\bvite\b', r'\bnode\.?js\b',
    r'\bspringboot\b', r'\bspring\b', r'\bhibernate\b',
    r'\blibrary\s+documentation\b', r'\bpackage\s+docs\b',
    r'\bhow\s+to\s+use\s+\w+\b'
]

URL_PATTERNS = [
    r'github\.com/[\w-]+/[\w-]+/(wiki|docs|blob)',
    r'(npmjs\.com|pypi\.org)',
    r'(docs\.\w+|readthedocs\.(io|org))',
    r'(stackoverflow\.com|developer\.mozilla\.org)',
    r'(medium\.com|dev\.to)',
    r'\w+\.github\.io'
]

def check_library_query(query):
    """检查是否为库文档查询"""
    query_lower = query.lower()
    
    # 检查关键词
    for pattern in LIBRARY_KEYWORDS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return True
    
    # 检查URL模式
    for pattern in URL_PATTERNS:
        if re.search(pattern, query, re.IGNORECASE):
            return True
    
    return False

def main():
    try:
        input_data = json.loads(sys.stdin.read())
        tool_name = input_data.get('tool_name', '')
        tool_input = input_data.get('tool_input', {})
        
        query = ''
        if tool_name == 'WebSearch':
            query = tool_input.get('query', '')
        elif tool_name == 'WebFetch':
            query = tool_input.get('url', '')
        
        is_library_search = check_library_query(query)
        
        if is_library_search:
            response = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": f"""
📚 库文档查询规范提醒

检测到库文档相关查询: {query[:100]}

请使用 Context7 MCP 工具查询库文档：
• 执行 /mcp 查看 context7 工具列表
• 常用工具：
  - context7_search: 搜索库文档
  - context7_get_page: 获取文档页面
  - context7_list_libraries: 查看支持的库

优势：
✓ 访问最新的官方文档
✓ 结构化的文档内容
✓ 快速精准的搜索
✓ 支持主流开发库和框架
"""
                }
            }
        else:
            response = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "allow"
                }
            }
        
        print(json.dumps(response))
        sys.exit(0)
        
    except Exception as e:
        error_response = {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "allow"
            }
        }
        print(json.dumps(error_response), file=sys.stderr)
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == '__main__':
    main()
