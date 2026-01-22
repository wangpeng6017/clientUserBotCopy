# Telegram Client User Bot

一个基于 Pyrogram 的 Telegram 客户端模拟操作机器人，通过 HTTP API 接收消息并发送到指定群组，支持多账户负载均衡和模拟真人操作。

## ✨ 功能特性

- 🌐 **HTTP API 接口**：通过 RESTful API 接收发送请求，支持文本和图片消息
- 📋 **客户端模拟操作**：使用 `send_message` 和 `send_photo` 方法模拟用户发送消息的操作
- 🖼️ 支持文本和图片消息，可以同时发送文本和图片（文本作为图片说明）
- 📝 完整的日志记录功能
- 🔄 **支持 systemd 服务管理**：可安装为系统服务，开机自启
- ⚙️ 配置文件化管理
- 🛡️ 防风控机制：消息队列 + 随机延迟 + 模拟真人操作
- 🔀 **多账户负载均衡**：支持配置多组 api_id/api_hash，同一个群的消息按配置的策略分配给不同账户发送
- 📖 **自动清除未读标记**：模拟真实用户操作，自动清除所有群组的未读消息标记和被回复标记
- ⏱️ **智能延迟策略**：思考时间、操作延迟、批量延迟、随机休息等，模拟真人行为

## 🔄 与原版 tgUserBot 的区别

| 特性 | tgUserBot | clientTgUserBot |
|------|-----------|-----------------|
| 库 | Telethon | Pyrogram |
| 消息来源 | 监听指定用户消息 | HTTP API 接口 |
| 发送方式 | `send_message` (直接发送) | `send_message` / `send_photo` (客户端模拟操作) |
| 消息格式 | 重新发送文本/媒体 | 直接发送文本或图片 |
| 接口方式 | 无 | HTTP RESTful API |
| 多账户 | 不支持 | 支持，可配置多个账户 |

## 🚀 快速开始

### 前置要求

- Python 3.9+
- Telegram API ID 和 API Hash
- Linux 服务器（推荐 Ubuntu 22.04）

### 安装步骤

1. **进入项目目录**
   ```bash
   cd clientTgUserBot
   ```

2. **创建虚拟环境**
   ```bash
   python3 -m venv client_env
   source client_env/bin/activate
   pip install --upgrade pip
   ```

3. **安装依赖**
   ```bash
   pip install -r requirements.txt
   ```

4. **配置项目**
   ```bash
   cp config.json.example config.json
   nano config.json  # 编辑配置文件
   ```

5. **首次登录**
   ```bash
   python main.py  # 登录后 Ctrl+C 退出
   ```

6. **运行程序**
   ```bash
   python main.py
   ```

## ⚙️ 配置说明

配置文件：`config.json`

### 多账户配置（推荐）

```json
{
    "accounts": [
        {
            "api_id": 12345678,
            "api_hash": "your_api_hash_here_1",
            "name": "account1"
        },
        {
            "api_id": 87654321,
            "api_hash": "your_api_hash_here_2",
            "name": "account2"
        }
    ],
    "log_dir": "logs",
    "send_interval": 2.0,
    "send_jitter": 1.0,
    "log_level": "INFO",
    "distribution_strategy": "round_robin",
    "enable_http_api": true,
    "http_host": "0.0.0.0",
    "http_port": 8000
}
```

### 单账户配置（兼容旧格式）

```json
{
    "api_id": 12345678,
    "api_hash": "your_api_hash_here",
    "log_dir": "logs",
    "send_interval": 2.0,
    "send_jitter": 1.0,
    "log_level": "INFO",
    "enable_http_api": true,
    "http_port": 8000
}
```

### 配置项说明

- `accounts`: 账户列表（数组），每个账户包含：
  - `api_id`: Telegram API ID（从 https://my.telegram.org/apps 获取）
  - `api_hash`: Telegram API Hash
  - `name`: 账户名称（可选，默认使用 `account_{api_id}`）
- `log_dir`: 日志目录（相对路径或绝对路径，默认 "logs"）
- `send_interval`: 消息发送间隔（秒），默认 2.0 秒
- `send_jitter`: 随机抖动时间（秒），默认 1.0 秒，会在 0 到 send_jitter 之间随机
- `log_level`: 日志级别（DEBUG, INFO, WARNING, ERROR），默认 INFO
- `distribution_strategy`: 消息分配策略，可选值：
  - `round_robin`: 轮询分配（默认），同一个群的消息按顺序分配给不同账户
  - `random`: 加权随机分配，优先选择使用次数少的账户，确保更均匀的分配
- `enable_http_api`: 是否启用 HTTP API，默认 `true`
- `http_host`: HTTP 服务器监听地址，默认 `0.0.0.0`（监听所有接口）
- `http_port`: HTTP 服务器端口，默认 `8000`
- `auto_mark_read`: 是否自动标记消息为已读（清除未读标记和被回复标记），默认 `true`
- `mark_read_interval`: 定期清除未读标记的间隔（秒），默认 `300`（5分钟）
- `mark_read_on_receive`: 收到消息时立即标记为已读，默认 `true`（已废弃，不再监听消息）
- `think_time_min` / `think_time_max`: 思考时间范围（秒），模拟看到消息后的反应时间，默认 0.5-3.0 秒
- `operation_delay_min` / `operation_delay_max`: 操作前延迟范围（秒），模拟点击、选择等操作时间，默认 0.3-1.0 秒
- `batch_delay_factor`: 批量消息延迟因子，队列中每多一条消息，额外延迟（秒），默认 0.5 秒
- `rest_probability`: 休息概率，每次发送后有概率休息，默认 0.05（5%）
- `rest_time_min` / `rest_time_max`: 休息时间范围（秒），默认 10-60 秒

### 多账户工作原理

- **所有账户都可用于发送**：每个配置的账户都可以用于发送消息
- **消息分配策略**：
  - `round_robin`（轮询）：同一个群的消息会按顺序分配给不同的账户发送，例如群A的第1条消息用账户1，第2条用账户2，第3条用账户1，以此类推
  - `random`（加权随机）：优先选择使用次数少的账户，确保更均匀的分配，同时保持随机性
- **负载均衡**：通过多账户分配，可以有效分散发送压力，降低被风控的风险

## 📖 使用方法

### 通过 HTTP API 发送消息

程序启动后，会启动 HTTP API 服务器（默认端口 8000），可以通过 API 接口发送消息。

**快速测试**：
```bash
# 发送文本消息
curl -X POST "http://localhost:8000/api/send" \
  -F "chat_id=-1001234567890" \
  -F "text=Hello, World!"

# 发送图片（带说明文字）
curl -X POST "http://localhost:8000/api/send" \
  -F "chat_id=-1001234567890" \
  -F "text=这是图片说明" \
  -F "photo=@/path/to/image.jpg"
```

详细 API 使用说明请查看 [API_USAGE.md](API_USAGE.md)

### 直接运行

```bash
source client_env/bin/activate
python main.py
```

程序启动后会：
1. 登录所有配置的 Telegram 账户
2. 启动 HTTP API 服务器（如果启用）
3. 启动消息发送队列
4. 等待 HTTP API 请求

### 安装为系统服务（推荐）

**首次使用前，请先手动运行一次完成所有账户的登录**：

```bash
# 1. 手动运行完成登录
source client_env/bin/activate
python main.py
# 为每个账户输入电话号码、验证码和密码（如需要）
# 登录完成后按 Ctrl+C 退出

# 2. 安装服务
chmod +x install_service.sh
./install_service.sh

# 3. 启动服务
sudo systemctl start clienttguserbot

# 4. 查看服务状态
sudo systemctl status clienttguserbot
```

**服务管理命令**：
```bash
# 启动服务
sudo systemctl start clienttguserbot

# 停止服务
sudo systemctl stop clienttguserbot

# 重启服务
sudo systemctl restart clienttguserbot

# 查看状态
sudo systemctl status clienttguserbot

# 查看日志
sudo journalctl -u clienttguserbot -f
```

详细说明请查看 [Systemd 服务安装指南](README_SYSTEMD.md)

### 查看日志

```bash
# Systemd 日志（如果使用服务）
sudo journalctl -u clienttguserbot -f

# 应用日志文件
tail -f logs/client_tguserbot_*.log
```

## 🔧 技术实现

### HTTP API 接口

本项目使用 FastAPI 提供 HTTP RESTful API 接口：

- **端点**: `POST /api/send`
- **支持**: 文本消息、图片消息，或同时发送文本和图片
- **格式**: `multipart/form-data`
- **响应**: JSON 格式，包含发送状态和队列信息

### 客户端模拟操作

本项目使用 Pyrogram 的 `send_message` 和 `send_photo` 方法发送消息，并应用多种延迟策略模拟真人操作：

```python
# 发送文本消息
await client.send_message(chat_id=chat_id, text=text)

# 发送图片（带说明文字）
await client.send_photo(chat_id=chat_id, photo=photo_data, caption=caption)
```

**模拟真人操作流程：**
1. **思考时间**：模拟看到消息后的反应时间（正态分布，0.5-3.0秒）
2. **基础延迟**：发送间隔 + 随机抖动（Beta分布，更自然）
3. **批量延迟**：队列中每多一条消息，增加额外延迟
4. **操作延迟**：模拟点击、选择等操作时间（0.3-1.0秒）
5. **随机休息**：5%概率休息10-60秒，模拟真人不会一直盯着屏幕

**优势：**
- 更接近真实用户行为，降低被检测风险
- 支持多账户负载均衡，分散发送压力
- 智能延迟策略，避免触发限流

### 自动清除未读标记

本项目模拟真实用户操作，定期清除所有群组的未读消息标记和被回复标记：

**定期清除**（每 `mark_read_interval` 秒执行一次）：
```python
await client.read_chat_history(chat_id)  # 清除该群组所有未读标记
```

**功能说明：**
- 自动清除未读消息标记（红色数字提示）
- 自动清除被回复标记（@提及和回复提醒）
- 模拟真实用户行为，保持账户活跃状态
- 可配置是否启用和清除间隔
- 每个群组清除后添加延迟，避免触发限流

## 📁 项目结构

```
clientTgUserBot/
├── main.py                 # 主程序
├── config.json             # 配置文件（需要创建）
├── config.json.example     # 配置模板
├── requirements.txt        # Python 依赖
├── clienttguserbot.service # Systemd 服务文件
├── install_service.sh     # 服务安装脚本
├── README.md              # 本文件
├── README_SYSTEMD.md      # Systemd 服务安装指南
├── API_USAGE.md           # HTTP API 使用说明
├── NGINX_SETUP.md         # Nginx 反向代理配置指南
├── nginx.conf.example     # Nginx 配置示例
└── logs/                  # 日志目录（自动创建）
```

## 🔒 安全建议

1. **保护敏感文件**
   ```bash
   chmod 600 config.json
   chmod 600 *.session
   ```

2. **不要提交敏感信息**
   - `config.json` 应添加到 `.gitignore`
   - `*.session` 文件应添加到 `.gitignore`

3. **定期更新依赖**
   ```bash
   source client_env/bin/activate
   pip install --upgrade pyrogram tgcrypto
   ```

## 🐛 故障排查

### 常见问题

1. **导入错误：找不到 pyrogram**
   ```bash
   source client_env/bin/activate
   pip install -r requirements.txt
   ```

2. **登录失败**
   - 检查 `api_id` 和 `api_hash` 是否正确
   - 确保网络连接正常
   - 如果启用了两步验证，需要在交互式环境中首次登录

3. **HTTP API 无法访问**
   - 检查 HTTP API 是否启用（`enable_http_api: true`）
   - 检查端口是否被占用（`http_port`）
   - 检查防火墙是否允许访问
   - 查看日志文件了解详细错误信息

4. **消息发送失败**
   - 检查目标群组的 chat_id 是否正确
   - 检查账户是否有权限在目标群组发送消息
   - 检查是否触发限流（FloodWait），程序会自动重试
   - 查看日志文件了解详细错误信息

4. **性能问题**
   - 调整 `send_interval` 和 `send_jitter` 参数
   - 检查系统资源使用情况

## 📝 更新日志

### v2.0.0
- 移除消息监听功能，改为通过 HTTP API 接收消息
- 支持文本和图片消息发送（可同时发送）
- 优化模拟真人操作流程（思考时间、操作延迟、批量延迟、随机休息）
- 支持多账户负载均衡（round_robin 和 weighted random）
- 添加 HTTP API 健康检查端点
- 支持 Nginx 反向代理配置

### v1.0.0
- 初始版本
- 基于 Pyrogram 实现客户端模拟操作
- 支持消息队列和防风控机制
- 完整的日志记录功能

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

本项目仅供学习和个人使用。

## 🔗 相关链接

- [Pyrogram 文档](https://docs.pyrogram.org/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [Telegram API](https://core.telegram.org/api)
- [获取 API 凭证](https://my.telegram.org/apps)
- [API 使用说明](API_USAGE.md)
- [Nginx 配置指南](NGINX_SETUP.md)

---

**需要帮助？** 请查看日志文件或提交 Issue。

