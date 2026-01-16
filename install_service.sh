#!/bin/bash

# Telegram Client User Bot Systemd 服务安装脚本

set -e

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Telegram Client User Bot Systemd 服务安装脚本 ===${NC}\n"

# 获取当前脚本所在目录
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_DIR="$SCRIPT_DIR"

# 获取当前用户名
CURRENT_USER=$(whoami)

echo -e "${YELLOW}项目目录: ${PROJECT_DIR}${NC}"
echo -e "${YELLOW}当前用户: ${CURRENT_USER}${NC}\n"

# 检查虚拟环境
if [ ! -d "$PROJECT_DIR/client_env" ]; then
    echo -e "${RED}错误: 未找到虚拟环境 client_env${NC}"
    echo -e "${YELLOW}请先创建虚拟环境: python3 -m venv client_env${NC}"
    exit 1
fi

# 检查 Python 解释器
PYTHON_PATH="$PROJECT_DIR/client_env/bin/python"
if [ ! -f "$PYTHON_PATH" ]; then
    echo -e "${RED}错误: 未找到 Python 解释器: $PYTHON_PATH${NC}"
    exit 1
fi

# 检查 main.py
if [ ! -f "$PROJECT_DIR/main.py" ]; then
    echo -e "${RED}错误: 未找到 main.py${NC}"
    exit 1
fi

# 检查配置文件
if [ ! -f "$PROJECT_DIR/config.json" ]; then
    echo -e "${YELLOW}警告: 未找到 config.json${NC}"
    echo -e "${YELLOW}请先创建配置文件: cp config.json.example config.json${NC}"
    echo -e "${YELLOW}并填写 API 信息${NC}\n"
fi

# 创建服务文件
SERVICE_FILE="$PROJECT_DIR/clienttguserbot.service"
TEMP_SERVICE_FILE="$PROJECT_DIR/clienttguserbot.service.tmp"

# 替换服务文件中的路径
sed "s|YOUR_USERNAME|$CURRENT_USER|g; s|/path/to/clientTgUserBot|$PROJECT_DIR|g" "$SERVICE_FILE" > "$TEMP_SERVICE_FILE"

echo -e "${GREEN}正在安装服务...${NC}"

# 复制服务文件
sudo cp "$TEMP_SERVICE_FILE" /etc/systemd/system/clienttguserbot.service

# 清理临时文件
rm "$TEMP_SERVICE_FILE"

# 重新加载 systemd
echo -e "${GREEN}重新加载 systemd 配置...${NC}"
sudo systemctl daemon-reload

# 启用服务
echo -e "${GREEN}启用服务（开机自启）...${NC}"
sudo systemctl enable clienttguserbot.service

echo -e "\n${GREEN}安装完成！${NC}\n"
echo -e "${YELLOW}使用以下命令管理服务:${NC}"
echo -e "  启动服务: ${GREEN}sudo systemctl start clienttguserbot${NC}"
echo -e "  停止服务: ${GREEN}sudo systemctl stop clienttguserbot${NC}"
echo -e "  重启服务: ${GREEN}sudo systemctl restart clienttguserbot${NC}"
echo -e "  查看状态: ${GREEN}sudo systemctl status clienttguserbot${NC}"
echo -e "  查看日志: ${GREEN}sudo journalctl -u clienttguserbot -f${NC}"
echo -e "\n${YELLOW}注意: 如果首次运行需要登录，请先手动运行一次脚本完成登录${NC}"
echo -e "${YELLOW}     所有账户都需要完成首次登录后才能作为服务运行${NC}"

