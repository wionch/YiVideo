#!/bin/bash

# Audio Separator 服务快速部署脚本
# 自动化部署和配置 Audio Separator 服务

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 日志函数
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检查是否以root权限运行
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_error "请不要以root用户运行此脚本"
        exit 1
    fi
}

# 检查Docker和Docker Compose
check_docker() {
    log_info "检查Docker环境..."

    if ! command -v docker &> /dev/null; then
        log_error "Docker未安装，请先安装Docker"
        exit 1
    fi

    if ! command -v docker-compose &> /dev/null; then
        log_error "Docker Compose未安装，请先安装Docker Compose"
        exit 1
    fi

    # 检查Docker是否运行
    if ! docker info &> /dev/null; then
        log_error "Docker服务未运行，请启动Docker服务"
        exit 1
    fi

    # 检查NVIDIA Docker支持
    if ! docker run --rm --gpus all nvidia/cuda:11.8-base nvidia-smi &> /dev/null; then
        log_error "NVIDIA Docker支持不可用，请安装nvidia-docker2"
        exit 1
    fi

    log_success "Docker环境检查通过"
}

# 创建必要目录
create_directories() {
    log_info "创建必要目录..."

    mkdir -p models/uvr_mdx
    mkdir -p share/workflows/audio_separated
    mkdir -p videos
    mkdir -p logs

    # 设置权限
    chmod -R 755 models share videos logs

    log_success "目录创建完成"
}

# 检查项目结构
check_project_structure() {
    log_info "检查项目结构..."

    required_files=(
        "docker-compose.yml"
        "config.yml"
        "services/workers/audio_separator_service/Dockerfile"
        "services/workers/audio_separator_service/requirements.txt"
        "services/workers/audio_separator_service/app/tasks.py"
        "scripts/download_audio_models.py"
        "scripts/test_audio_separator.py"
        "scripts/monitor_audio_separator.py"
    )

    for file in "${required_files[@]}"; do
        if [[ ! -f "$file" ]]; then
            log_error "缺少必要文件: $file"
            exit 1
        fi
    done

    log_success "项目结构检查通过"
}

# 启动基础服务
start_base_services() {
    log_info "启动基础服务 (Redis, API Gateway)..."

    docker-compose up -d redis api_gateway

    # 等待服务启动
    log_info "等待服务启动..."
    sleep 10

    # 检查Redis连接
    if ! docker exec redis redis-cli ping &> /dev/null; then
        log_error "Redis启动失败"
        exit 1
    fi

    # 检查API Gateway
    if ! curl -s http://localhost:8788/ &> /dev/null; then
        log_error "API Gateway启动失败"
        exit 1
    fi

    log_success "基础服务启动完成"
}

# 下载音频分离模型
download_models() {
    log_info "下载音频分离模型..."

    if python scripts/download_audio_models.py --download-recommended; then
        log_success "模型下载完成"
    else
        log_error "模型下载失败"
        exit 1
    fi

    # 验证模型
    log_info "验证模型文件..."
    if python scripts/download_audio_models.py --verify &> /dev/null; then
        log_success "模型验证通过"
    else
        log_warning "模型验证发现问题，但继续部署"
    fi
}

# 构建并启动Audio Separator服务
start_audio_separator() {
    log_info "构建并启动Audio Separator服务..."

    # 构建镜像
    docker-compose build audio_separator_service

    # 启动服务
    docker-compose up -d audio_separator_service

    # 等待服务启动
    log_info "等待Audio Separator服务启动..."
    sleep 30

    # 检查服务状态
    if ! docker ps | grep audio_separator_service &> /dev/null; then
        log_error "Audio Separator服务启动失败"
        docker-compose logs audio_separator_service
        exit 1
    fi

    log_success "Audio Separator服务启动完成"
}

# 运行健康检查
run_health_check() {
    log_info "运行健康检查..."

    # 检查服务依赖
    if python scripts/test_audio_separator.py --check-deps; then
        log_success "服务依赖检查通过"
    else
        log_error "服务依赖检查失败"
        exit 1
    fi

    # 检查服务健康状态
    if python scripts/monitor_audio_separator.py --health-check; then
        log_success "服务健康检查通过"
    else
        log_warning "服务健康检查有问题，但继续部署"
    fi
}

# 运行功能测试
run_functional_test() {
    log_info "运行功能测试..."

    # 检查是否有测试文件
    if [[ ! -f "videos/test_video.mp4" ]]; then
        log_warning "未找到测试文件 videos/test_video.mp4"
        log_info "请将测试视频文件放置到 videos/ 目录下"
        return
    fi

    # 运行基础测试
    if python scripts/test_audio_separator.py --test basic; then
        log_success "功能测试通过"
    else
        log_error "功能测试失败"
        exit 1
    fi
}

# 显示部署状态
show_deployment_status() {
    log_info "显示部署状态..."

    echo ""
    echo "============================================="
    echo "🎵 Audio Separator 服务部署完成"
    echo "============================================="
    echo ""

    # 显示服务状态
    echo "📊 服务状态:"
    docker-compose ps | grep -E "(redis|api_gateway|audio_separator_service)"
    echo ""

    # 显示模型信息
    echo "🎛️  模型信息:"
    if [[ -d "models/uvr_mdx" ]]; then
        model_count=$(ls models/uvr_mdx/*.onnx 2>/dev/null | wc -l)
        echo "  可用模型: $model_count 个"
        ls models/uvr_mdx/*.onnx 2>/dev/null | head -3 | sed 's/.*\//  - /'
    else
        echo "  模型目录不存在"
    fi
    echo ""

    # 显示访问信息
    echo "🔗 访问信息:"
    echo "  API Gateway: http://localhost:8788"
    echo "  API文档: http://localhost:8788/docs"
    echo "  监控面板: python scripts/monitor_audio_separator.py --dashboard"
    echo ""

    # 显示使用示例
    echo "📝 使用示例:"
    echo "  # 1. 创建音频分离工作流"
    echo "  curl -X POST 'http://localhost:8788/v1/workflows' \\"
    echo "    -H 'Content-Type: application/json' \\"
    echo "    -d '{"
    echo "      \"video_path\": \"/share/videos/test_video.mp4\","
    echo "      \"workflow_config\": {"
    echo "        \"workflow_chain\": [\"audio_separator.separate_vocals\"]"
    echo "      }"
    echo "    }'"
    echo ""
    echo "  # 2. 查询工作流状态"
    echo "  curl 'http://localhost:8788/v1/workflows/status/{workflow_id}'"
    echo ""

    # 显示管理命令
    echo "🔧 管理命令:"
    echo "  查看服务日志: docker-compose logs -f audio_separator_service"
    echo "  重启服务:     docker-compose restart audio_separator_service"
    echo "  停止服务:     docker-compose down"
    echo "  健康检查:     python scripts/monitor_audio_separator.py --health-check"
    echo "  性能监控:     python scripts/monitor_audio_separator.py --dashboard"
    echo ""

    echo "🎉 部署完成！Audio Separator 服务现在可以使用。"
}

# 主函数
main() {
    echo ""
    echo "============================================="
    echo "🎵 Audio Separator 服务部署脚本"
    echo "============================================="
    echo ""

    # 检查参数
    SKIP_TESTS=false
    SKIP_MODELS=false

    while [[ $# -gt 0 ]]; do
        case $1 in
            --skip-tests)
                SKIP_TESTS=true
                shift
                ;;
            --skip-models)
                SKIP_MODELS=true
                shift
                ;;
            --help)
                echo "用法: $0 [选项]"
                echo ""
                echo "选项:"
                echo "  --skip-tests    跳过功能测试"
                echo "  --skip-models   跳过模型下载"
                echo "  --help          显示此帮助信息"
                echo ""
                exit 0
                ;;
            *)
                log_error "未知选项: $1"
                exit 1
                ;;
        esac
    done

    # 执行部署步骤
    log_info "开始部署 Audio Separator 服务..."

    check_root
    check_docker
    create_directories
    check_project_structure
    start_base_services

    if [[ "$SKIP_MODELS" == false ]]; then
        download_models
    else
        log_warning "跳过模型下载"
    fi

    start_audio_separator
    run_health_check

    if [[ "$SKIP_TESTS" == false ]]; then
        run_functional_test
    else
        log_warning "跳过功能测试"
    fi

    show_deployment_status

    log_success "部署完成！"
}

# 错误处理
trap 'log_error "部署过程中发生错误，请检查日志"; exit 1' ERR

# 运行主函数
main "$@"