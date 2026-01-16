#!/bin/bash

# clientTgUserBot 安装脚本

set -e

echo "=========================================="
echo "clientTgUserBot 安装脚本"
echo "=========================================="

# 获取脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# 检查 Python 版本
echo "检查 Python 版本..."
if ! command -v python3 &> /dev/null; then
    echo "错误: 未找到 python3，请先安装 Python 3.9+"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "Python 版本: $(python3 --version)"

# 检查虚拟环境
if [ ! -d "client_env" ]; then
    echo "创建虚拟环境..."
    python3 -m venv client_env
fi

# 激活虚拟环境
echo "激活虚拟环境..."
source client_env/bin/activate

# 升级 pip
echo "升级 pip..."
pip install --upgrade pip

# 安装依赖
echo "安装依赖..."
pip install -r requirements.txt

# 检查配置文件
if [ ! -f "config.json" ]; then
    if [ -f "config.json.example" ]; then
        echo "复制配置文件模板..."
        cp config.json.example config.json
        echo "请编辑 config.json 文件，填写你的 API ID、API Hash 和目标用户名"
    else
        echo "警告: 未找到 config.json.example 文件"
    fi
else
    echo "配置文件已存在"
fi

# 创建日志目录
if [ ! -d "logs" ]; then
    echo "创建日志目录..."
    mkdir -p logs
fi

echo ""
echo "=========================================="
echo "安装完成！"
echo "=========================================="
echo ""
echo "下一步："
echo "1. 编辑 config.json 文件，填写配置信息"
echo "2. 运行: source client_env/bin/activate && python main.py"
echo "3. 首次运行会要求登录，请按照提示操作"
echo ""

