# Nginx 反向代理配置指南

## 概述

本指南介绍如何配置 Nginx 反向代理，使 Telegram Client User Bot 的 HTTP API 可以通过域名访问。

## 前置要求

1. 已安装 Nginx
2. 拥有一个域名（例如：`api.yourdomain.com`）
3. 域名 DNS 已解析到服务器 IP

## 配置步骤

### 1. 复制配置文件

将 `nginx.conf.example` 复制到 Nginx 配置目录：

```bash
sudo cp nginx.conf.example /etc/nginx/sites-available/clienttguserbot
# 或者
sudo cp nginx.conf.example /etc/nginx/conf.d/clienttguserbot.conf
```

### 2. 修改配置

编辑配置文件，修改以下内容：

```bash
sudo nano /etc/nginx/sites-available/clienttguserbot
```

**需要修改的配置项：**

- `server_name`: 改为你的域名，例如 `api.yourdomain.com`
- `proxy_pass`: 确认后端服务地址和端口（默认 `http://127.0.0.1:8000`）
- `ssl_certificate` 和 `ssl_certificate_key`: SSL 证书路径（如果使用 HTTPS）

### 3. 启用配置

```bash
# 创建软链接（如果使用 sites-available/sites-enabled）
sudo ln -s /etc/nginx/sites-available/clienttguserbot /etc/nginx/sites-enabled/

# 测试配置
sudo nginx -t

# 重新加载 Nginx
sudo systemctl reload nginx
```

### 4. 配置 SSL 证书（HTTPS，推荐）

使用 Let's Encrypt 免费 SSL 证书：

```bash
# 安装 certbot
sudo apt-get update
sudo apt-get install certbot python3-certbot-nginx

# 自动配置 SSL（会自动修改 Nginx 配置）
sudo certbot --nginx -d api.yourdomain.com

# 设置自动续期
sudo certbot renew --dry-run
```

### 5. 防火墙配置

确保防火墙允许 HTTP/HTTPS 流量：

```bash
# Ubuntu/Debian (ufw)
sudo ufw allow 'Nginx Full'
# 或者
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# CentOS/RHEL (firewalld)
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

## 配置说明

### 重要配置项

1. **`client_max_body_size 10M`**: 限制上传文件大小，根据需要调整
2. **`proxy_pass http://127.0.0.1:8000`**: 后端服务地址，确保与 `config.json` 中的 `http_port` 一致
3. **`proxy_set_header`**: 设置代理请求头，确保后端能获取真实客户端信息

### 安全建议

1. **使用 HTTPS**: 保护 API 通信安全
2. **限制访问**: 可以添加 IP 白名单或使用 Nginx 的 `allow/deny` 指令
3. **速率限制**: 防止 API 被滥用

### 添加访问限制示例

```nginx
# 只允许特定 IP 访问
location / {
    allow 192.168.1.0/24;  # 允许内网
    allow 1.2.3.4;         # 允许特定 IP
    deny all;               # 拒绝其他所有
    
    proxy_pass http://127.0.0.1:8000;
    # ... 其他配置
}
```

### 添加速率限制示例

```nginx
# 在 http 块中添加
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

# 在 server 块中添加
location / {
    limit_req zone=api_limit burst=20 nodelay;
    
    proxy_pass http://127.0.0.1:8000;
    # ... 其他配置
}
```

## 测试配置

### 1. 测试 Nginx 配置

```bash
sudo nginx -t
```

### 2. 测试 API 访问

```bash
# 测试健康检查
curl https://api.yourdomain.com/api/health

# 测试发送消息
curl -X POST "https://api.yourdomain.com/api/send" \
  -F "chat_id=-1001234567890" \
  -F "text=测试消息"
```

### 3. 查看日志

```bash
# Nginx 访问日志
sudo tail -f /var/log/nginx/clienttguserbot_access.log

# Nginx 错误日志
sudo tail -f /var/log/nginx/clienttguserbot_error.log

# 应用日志
tail -f logs/client_tguserbot_*.log
```

## 常见问题

### 1. 502 Bad Gateway

**原因**: 后端服务未启动或端口不匹配

**解决**:
- 检查服务是否运行：`ps aux | grep python`
- 检查端口是否正确：`netstat -tlnp | grep 8000`
- 检查防火墙是否阻止了本地连接

### 2. 413 Request Entity Too Large

**原因**: 上传的文件超过限制

**解决**: 增加 `client_max_body_size` 配置

### 3. SSL 证书错误

**原因**: 证书路径不正确或证书过期

**解决**:
- 检查证书路径是否正确
- 更新证书：`sudo certbot renew`

### 4. 连接超时

**原因**: 后端处理时间过长

**解决**: 增加超时设置：
```nginx
proxy_connect_timeout 300s;
proxy_send_timeout 300s;
proxy_read_timeout 300s;
```

## 完整配置示例（带安全限制）

```nginx
# 速率限制
limit_req_zone $binary_remote_addr zone=api_limit:10m rate=10r/s;

server {
    listen 443 ssl http2;
    server_name api.yourdomain.com;

    # SSL 配置
    ssl_certificate /etc/letsencrypt/live/api.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api.yourdomain.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    # 日志
    access_log /var/log/nginx/clienttguserbot_access.log;
    error_log /var/log/nginx/clienttguserbot_error.log;

    # 文件大小限制
    client_max_body_size 10M;

    # API 端点
    location /api/ {
        # 速率限制
        limit_req zone=api_limit burst=20 nodelay;
        
        # IP 白名单（可选）
        # allow 192.168.1.0/24;
        # deny all;
        
        # 代理配置
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # 超时设置
        proxy_connect_timeout 60s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;
    }

    # 健康检查（不限制速率）
    location /api/health {
        proxy_pass http://127.0.0.1:8000/api/health;
        proxy_set_header Host $host;
        add_header Access-Control-Allow-Origin *;
    }
}
```

## 更新配置后

每次修改配置后，记得：

```bash
# 测试配置
sudo nginx -t

# 重新加载（不中断服务）
sudo systemctl reload nginx

# 或重启（会短暂中断服务）
sudo systemctl restart nginx
```

