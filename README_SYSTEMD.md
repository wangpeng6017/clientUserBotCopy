# Telegram Client User Bot Systemd 服务安装指南

## 前置要求

1. Python 3.9+ 已安装
2. 虚拟环境已创建并安装了依赖（pyrogram, tgcrypto）
3. 已配置好所有账户的 API 信息和登录（首次运行需要交互式登录）

## 安装步骤

### 方法一：使用自动安装脚本（推荐）

```bash
cd clientTgUserBot
chmod +x install_service.sh
./install_service.sh
```

脚本会自动：
- 检测虚拟环境和配置文件
- 替换服务文件中的路径和用户名
- 安装并启用服务

### 方法二：手动安装

#### 1. 修改服务文件

编辑 `clienttguserbot.service` 文件，替换以下路径：

- `YOUR_USERNAME`: 替换为运行服务的 Linux 用户名
- `/path/to/clientTgUserBot`: 替换为项目的实际路径（例如：`/home/username/clientTgUserBot`）

示例：
```ini
User=ubuntu
WorkingDirectory=/home/ubuntu/clientTgUserBot
Environment="PATH=/home/ubuntu/clientTgUserBot/client_env/bin:/usr/local/bin:/usr/bin:/bin"
ExecStart=/home/ubuntu/clientTgUserBot/client_env/bin/python /home/ubuntu/clientTgUserBot/main.py
```

#### 2. 复制服务文件到 systemd 目录

```bash
sudo cp clienttguserbot.service /etc/systemd/system/
```

#### 3. 重新加载 systemd 配置

```bash
sudo systemctl daemon-reload
```

#### 4. 启用服务（开机自启）

```bash
sudo systemctl enable clienttguserbot.service
```

#### 5. 启动服务

```bash
sudo systemctl start clienttguserbot.service
```

#### 6. 检查服务状态

```bash
sudo systemctl status clienttguserbot.service
```

## 服务管理命令

### 启动服务
```bash
sudo systemctl start clienttguserbot
```

### 停止服务
```bash
sudo systemctl stop clienttguserbot
```

### 重启服务
```bash
sudo systemctl restart clienttguserbot
```

### 查看服务状态
```bash
sudo systemctl status clienttguserbot
```

### 查看服务日志
```bash
# 实时查看日志
sudo journalctl -u clienttguserbot -f

# 查看最近 100 行日志
sudo journalctl -u clienttguserbot -n 100

# 查看今天的日志
sudo journalctl -u clienttguserbot --since today
```

### 禁用服务（取消开机自启）
```bash
sudo systemctl disable clienttguserbot
```

### 卸载服务
```bash
sudo systemctl stop clienttguserbot
sudo systemctl disable clienttguserbot
sudo rm /etc/systemd/system/clienttguserbot.service
sudo systemctl daemon-reload
```

## 首次登录

**重要**：在将服务设置为自动启动之前，必须确保所有账户都已完成首次登录。

### 步骤

1. **手动运行程序完成登录**：
   ```bash
   cd clientTgUserBot
   source client_env/bin/activate
   python main.py
   ```

2. **为每个账户完成登录**：
   - 输入电话号码
   - 输入验证码
   - 如果启用了两步验证，输入密码

3. **确认所有 session 文件已创建**：
   ```bash
   ls -la session_*.session
   ```
   应该看到所有账户的 session 文件，例如：
   - `session_account1_12345678.session`
   - `session_account2_87654321.session`

4. **登录完成后，按 Ctrl+C 退出**

5. **然后安装并启动服务**：
   ```bash
   ./install_service.sh
   sudo systemctl start clienttguserbot
   ```

## 故障排查

### 服务无法启动

1. **检查服务状态**：
   ```bash
   sudo systemctl status clienttguserbot
   ```

2. **查看详细日志**：
   ```bash
   sudo journalctl -u clienttguserbot -n 50 --no-pager
   ```

3. **常见问题**：
   - **虚拟环境路径错误**：检查 `clienttguserbot.service` 中的路径是否正确
   - **权限问题**：确保服务文件中的 `User` 设置正确
   - **未完成登录**：确保所有账户的 session 文件都存在
   - **配置文件错误**：检查 `config.json` 格式是否正确

### 服务启动但立即停止

1. **查看错误日志**：
   ```bash
   sudo journalctl -u clienttguserbot -n 100 --no-pager
   ```

2. **手动运行测试**：
   ```bash
   cd clientTgUserBot
   source client_env/bin/activate
   python main.py
   ```
   查看是否有错误信息

### 服务运行但无法连接

1. **检查网络连接**
2. **检查防火墙设置**
3. **查看应用日志文件**：
   ```bash
   tail -f logs/client_tguserbot_*.log
   ```

### 多账户相关问题

- **部分账户登录失败**：检查对应账户的 session 文件是否存在
- **账户权限不足**：确保所有账户都有权限访问目标群组
- **消息重复发送**：检查去重机制是否正常工作

## 日志位置

- **Systemd 日志**：`sudo journalctl -u clienttguserbot -f`
- **应用日志文件**：`logs/client_tguserbot_YYYYMMDD.log`

## 安全建议

1. **保护敏感文件**：
   ```bash
   chmod 600 config.json
   chmod 600 session_*.session
   ```

2. **定期更新依赖**：
   ```bash
   source client_env/bin/activate
   pip install --upgrade pyrogram tgcrypto
   ```

3. **监控服务状态**：定期检查服务是否正常运行

## 更新服务

如果需要更新代码或配置：

1. **停止服务**：
   ```bash
   sudo systemctl stop clienttguserbot
   ```

2. **更新代码或配置**

3. **重启服务**：
   ```bash
   sudo systemctl start clienttguserbot
   ```

## 相关文档

- [README.md](README.md) - 项目主文档
- [config.json.example](config.json.example) - 配置文件示例

