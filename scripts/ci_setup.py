#!/usr/bin/env python3
"""
CI/CD 环境设置脚本
用于配置持续集成和持续部署环境
"""

import os
import sys
import subprocess
import json
import yaml
from pathlib import Path

def print_step(step: str, description: str):
    """打印步骤信息"""
    print(f"\n=== {step} ===")
    print(description)

def run_command(cmd: str, description: str = None) -> bool:
    """执行命令"""
    if description:
        print(f"执行: {description}")
    print(f"命令: {cmd}")

    try:
        result = subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout)
        return True
    except subprocess.CalledProcessError as e:
        print(f"执行失败: {e}")
        if e.stderr:
            print(f"错误信息: {e.stderr}")
        return False

def create_ci_directories():
    """创建 CI/CD 相关目录"""
    print_step("1", "创建 CI/CD 目录结构")

    directories = [
        ".github/workflows",
        "tests/unit",
        "tests/integration",
        "tests/performance",
        "scripts/ci",
        "artifacts",
        "reports"
    ]

    for directory in directories:
        Path(directory).mkdir(parents=True, exist_ok=True)
        print(f"✓ 创建目录: {directory}")

def create_test_files():
    """创建测试文件"""
    print_step("2", "创建测试文件")

    # 单元测试示例
    unit_test = """import unittest
import sys
import os

# 添加项目根目录到 Python 路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.common.config_loader import CONFIG

class TestConfigLoader(unittest.TestCase):
    def test_load_config(self):
        \"\"\"测试配置加载\"\"\"
        self.assertIsNotNone(CONFIG)

    def test_redis_config(self):
        \"\"\"测试 Redis 配置\"\"\"
        redis_config = CONFIG.get('redis', {})
        self.assertIn('host', redis_config)
        self.assertIn('port', redis_config)

if __name__ == '__main__':
    unittest.main()
"""

    with open("tests/unit/test_config.py", "w") as f:
        f.write(unit_test)

    # 集成测试示例
    integration_test = """import unittest
import requests
import time
import subprocess
import sys
import os

class TestAPIIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        \"\"\"启动测试环境\"\"\"
        print("启动测试环境...")
        # 这里可以添加启动 Docker 容器的代码
        time.sleep(30)

    @classmethod
    def tearDownClass(cls):
        \"\"\"清理测试环境\"\"\"
        print("清理测试环境...")
        # 这里可以添加停止 Docker 容器的代码

    def test_health_endpoint(self):
        \"\"\"测试健康检查端点\"\"\"
        try:
            response = requests.get('http://localhost:8788/health', timeout=10)
            self.assertEqual(response.status_code, 200)
        except requests.exceptions.RequestException as e:
            self.skipTest(f"服务不可用: {e}")

    def test_workflow_creation(self):
        \"\"\"测试工作流创建\"\"\"
        workflow_data = {
            \"video_path\": \"/app/videos/test.mp4\",
            \"workflow_config\": {
                \"workflow_chain\": [
                    \"ffmpeg.extract_audio\",
                    \"whisperx.generate_subtitles\"
                ]
            }
        }

        try:
            response = requests.post(
                'http://localhost:8788/v1/workflows',
                json=workflow_data,
                timeout=30
            )
            self.assertIn(response.status_code, [200, 201])

            data = response.json()
            self.assertIn('workflow_id', data)

        except requests.exceptions.RequestException as e:
            self.skipTest(f"服务不可用: {e}")

if __name__ == '__main__':
    unittest.main()
"""

    with open("tests/integration/test_api.py", "w") as f:
        f.write(integration_test)

    # 性能测试示例
    performance_test = """import unittest
import time
import requests
import statistics

class TestPerformance(unittest.TestCase):
    def test_api_response_time(self):
        \"\"\"测试 API 响应时间\"\"\"
        response_times = []

        for _ in range(10):
            start_time = time.time()
            try:
                response = requests.get('http://localhost:8788/health', timeout=10)
                response_times.append(time.time() - start_time)
            except requests.exceptions.RequestException:
                pass

        if response_times:
            avg_time = statistics.mean(response_times)
            self.assertLess(avg_time, 1.0, f"平均响应时间过长: {avg_time:.2f}s")
        else:
            self.skipTest("无法连接到服务")

    def test_concurrent_requests(self):
        \"\"\"测试并发请求处理\"\"\"
        import threading
        import queue

        result_queue = queue.Queue()

        def make_request():
            try:
                response = requests.get('http://localhost:8788/health', timeout=10)
                result_queue.put(response.status_code)
            except requests.exceptions.RequestException:
                result_queue.put(None)

        threads = []
        for _ in range(20):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        success_count = sum(1 for status in result_queue.queue if status == 200)
        self.assertGreater(success_count, 15, f"成功率过低: {success_count}/20")

if __name__ == '__main__':
    unittest.main()
"""

    with open("tests/performance/test_performance.py", "w") as f:
        f.write(performance_test)

    print("✓ 创建测试文件")

def create_ci_scripts():
    """创建 CI/CD 脚本"""
    print_step("3", "创建 CI/CD 脚本")

    # 健康检查脚本
    health_check_script = """#!/usr/bin/env python3
import sys
import requests
import time
import json
from datetime import datetime

def check_service_health():
    \"\"\"检查服务健康状态\"\"\"
    services = {
        'api_gateway': 'http://localhost:8788/health',
        'redis': 'http://localhost:6379/ping',
        'whisperx_service': 'http://localhost:8080/health'
    }

    results = {}

    for service_name, url in services.items():
        try:
            response = requests.get(url, timeout=10)
            results[service_name] = {
                'status': 'healthy',
                'status_code': response.status_code,
                'response_time': response.elapsed.total_seconds()
            }
        except requests.exceptions.RequestException as e:
            results[service_name] = {
                'status': 'unhealthy',
                'error': str(e)
            }

    return results

def generate_health_report(results):
    \"\"\"生成健康检查报告\"\"\"
    report = {
        'timestamp': datetime.now().isoformat(),
        'services': results,
        'summary': {
            'total_services': len(results),
            'healthy_services': sum(1 for r in results.values() if r['status'] == 'healthy'),
            'unhealthy_services': sum(1 for r in results.values() if r['status'] == 'unhealthy')
        }
    }

    return report

def main():
    print("=== 健康检查 ===")

    results = check_service_health()
    report = generate_health_report(results)

    # 输出结果
    print(f"总服务数: {report['summary']['total_services']}")
    print(f"健康服务数: {report['summary']['healthy_services']}")
    print(f"不健康服务数: {report['summary']['unhealthy_services']}")

    for service_name, result in results.items():
        status = result['status']
        if status == 'healthy':
            print(f"✓ {service_name}: 健康 ({result['response_time']:.3f}s)")
        else:
            print(f"✗ {service_name}: 不健康 ({result.get('error', 'Unknown error')})")

    # 保存报告
    with open('health_report.json', 'w') as f:
        json.dump(report, f, indent=2)

    # 设置退出码
    unhealthy_count = report['summary']['unhealthy_services']
    sys.exit(1 if unhealthy_count > 0 else 0)

if __name__ == '__main__':
    main()
"""

    with open("scripts/ci/health_check.py", "w") as f:
        f.write(health_check_script)

    # 部署脚本
    deploy_script = """#!/usr/bin/env python3
import os
import sys
import subprocess
import argparse

def parse_args():
    parser = argparse.ArgumentParser(description='部署 WhisperX 应用')
    parser.add_argument('--environment', choices=['staging', 'production'], required=True)
    parser.add_argument('--version', required=True)
    return parser.parse_args()

def deploy_to_staging(version):
    \"\"\"部署到测试环境\"\"\"
    print(f"部署到测试环境: {version}")

    # 更新配置
    subprocess.run(['sed', '-i', f's/VERSION=.*/VERSION={version}/', '.env'], check=True)

    # 构建并启动服务
    subprocess.run(['docker-compose', '-f', 'docker-compose.yml', 'up', '-d'], check=True)

    # 运行健康检查
    subprocess.run(['python', 'scripts/ci/health_check.py'], check=True)

def deploy_to_production(version):
    \"\"\"部署到生产环境\"\"\"
    print(f"部署到生产环境: {version}")

    # 停止当前服务
    subprocess.run(['docker-compose', 'down'], check=True)

    # 拉取最新镜像
    subprocess.run(['docker-compose', 'pull'], check=True)

    # 启动服务
    subprocess.run(['docker-compose', 'up', '-d'], check=True)

    # 运行生产环境测试
    subprocess.run(['python', 'scripts/ci/production_tests.py'], check=True)

def main():
    args = parse_args()

    if args.environment == 'staging':
        deploy_to_staging(args.version)
    elif args.environment == 'production':
        deploy_to_production(args.version)

    print(f"部署完成: {args.environment} v{args.version}")

if __name__ == '__main__':
    main()
"""

    with open("scripts/ci/deploy.py", "w") as f:
        f.write(deploy_script)

    # 设置执行权限
    os.chmod("scripts/ci/health_check.py", 0o755)
    os.chmod("scripts/ci/deploy.py", 0o755)

    print("✓ 创建 CI/CD 脚本")

def create_ci_config():
    """创建 CI/CD 配置文件"""
    print_step("4", "创建 CI/CD 配置文件")

    # pytest 配置
    pytest_config = """[tool:pytest]
testpaths = tests
python_files = test_*.py
python_classes = Test*
python_functions = test_*
addopts =
    -v
    --tb=short
    --strict-markers
    --disable-warnings
    --cov=.
    --cov-report=term-missing
    --cov-report=html
    --cov-report=xml

markers =
    unit: 单元测试
    integration: 集成测试
    performance: 性能测试
    slow: 慢速测试
"""

    with open("pytest.ini", "w") as f:
        f.write(pytest_config)

    # coverage 配置
    coverage_config = """[run]
source = .
omit =
    tests/*
    */venv/*
    */env/*
    */.tox/*

[report]
exclude_lines =
    pragma: no cover
    def __repr__
    raise AssertionError
    raise NotImplementedError
    if __name__ == .__main__.:
"""

    with open(".coveragerc", "w") as f:
        f.write(coverage_config)

    # tox 配置
    tox_config = """[tox]
envlist = py38,py39,py310

[testenv]
deps =
    pytest
    pytest-cov
    pytest-mock
    requests
commands =
    pytest {posargs}

[testenv:integration]
deps =
    pytest
    pytest-cov
    docker
commands =
    pytest tests/integration/ {posargs}

[testenv:performance]
deps =
    pytest
    pytest-benchmark
    locust
commands =
    pytest tests/performance/ {posargs}
"""

    with open("tox.ini", "w") as f:
        f.write(tox_config)

    print("✓ 创建 CI/CD 配置文件")

def setup_github_secrets():
    """设置 GitHub Secrets 指导"""
    print_step("5", "设置 GitHub Secrets")

    secrets_guide = """# GitHub Secrets 设置指南

需要在 GitHub 仓库中设置以下 Secrets:

## 必需 Secrets

### 1. GITHUB_TOKEN
- 自动由 GitHub 提供
- 用于推送镜像到 GitHub Container Registry

### 2. DOCKER_USERNAME
- Docker Hub 用户名
- 用于推送镜像到 Docker Hub

### 3. DOCKER_PASSWORD
- Docker Hub 密码
- 用于推送镜像到 Docker Hub

### 4. SLACK_WEBHOOK
- Slack 通知 Webhook URL
- 用于发送构建和部署通知

### 5. SSH_PRIVATE_KEY
- 部署服务器的 SSH 私钥
- 用于远程部署到生产环境

### 6. DEPLOY_HOST
- 部署服务器地址
- 格式: user@hostname

## 可选 Secrets

### 1. AWS_ACCESS_KEY_ID
- AWS 访问密钥 ID
- 用于 AWS 服务集成

### 2. AWS_SECRET_ACCESS_KEY
- AWS 秘密访问密钥
- 用于 AWS 服务集成

### 3. DATABASE_URL
- 数据库连接 URL
- 用于数据库测试

### 4. REDIS_URL
- Redis 连接 URL
- 用于 Redis 测试

## 设置方法

1. 进入 GitHub 仓库设置
2. 点击 "Secrets and variables" -> "Actions"
3. 点击 "New repository secret"
4. 输入 Secret 名称和值
5. 点击 "Add secret"

## 验证 Secrets

可以使用以下命令验证 Secrets 是否正确设置:

```bash
# 在 GitHub Actions 中验证
echo ${{ secrets.DOCKER_USERNAME }}
echo ${{ secrets.SLACK_WEBHOOK }}
```
"""

    with open("docs/github_secrets.md", "w") as f:
        f.write(secrets_guide)

    print("✓ 创建 GitHub Secrets 设置指南")

def main():
    """主函数"""
    print("=== CI/CD 环境设置 ===")

    try:
        create_ci_directories()
        create_test_files()
        create_ci_scripts()
        create_ci_config()
        setup_github_secrets()

        print("\n=== CI/CD 环境设置完成 ===")
        print("请执行以下步骤完成设置:")
        print("1. 设置 GitHub Secrets (参考 docs/github_secrets.md)")
        print("2. 运行测试: pytest")
        print("3. 运行健康检查: python scripts/ci/health_check.py")
        print("4. 提交代码并推送到 GitHub")

    except Exception as e:
        print(f"\n设置失败: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()