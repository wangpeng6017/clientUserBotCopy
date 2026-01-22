# HTTP API 使用说明

## 概述

系统现在支持通过 HTTP API 接口发送消息，无需监听和复制指定账号的消息。所有发送逻辑保持不变（包括分配策略、延迟、模拟真人操作等）。

**重要**：接口支持同时发送文本和图片，文本可以作为图片的说明文字。

## API 端点

### 1. 发送消息（文本和/或图片）

**端点**: `POST /api/send`

**请求格式**: `multipart/form-data`

**参数**:
- `chat_id` (int, 必需): 目标群组的 chat_id
- `text` (string, 可选): 文本内容（如果只发送文本，则只提供此参数）
- `photo` (file, 可选): 图片文件（如果只发送图片，则只提供此参数）
- 可以同时提供 `text` 和 `photo`，此时图片会带说明文字

**响应示例**:
```json
{
    "status": "success",
    "message": "消息已加入队列",
    "chat_id": -1001234567890,
    "has_text": true,
    "has_photo": true,
    "photo_size": 12345,
    "photo_filename": "image.jpg",
    "queue_size": 1
}
```

### 2. 健康检查

**端点**: `GET /api/health`

**响应示例**:
```json
{
    "status": "ok",
    "connected_clients": 2,
    "total_clients": 2,
    "queue_size": 0
}
```

## 使用示例

### cURL 示例

#### 只发送文本消息
```bash
curl -X POST "http://localhost:8000/api/send" \
  -F "chat_id=-1001234567890" \
  -F "text=Hello, World!"
```

#### 只发送图片
```bash
curl -X POST "http://localhost:8000/api/send" \
  -F "chat_id=-1001234567890" \
  -F "photo=@/path/to/image.jpg"
```

#### 同时发送文本和图片（图片带说明文字）
```bash
curl -X POST "http://localhost:8000/api/send" \
  -F "chat_id=-1001234567890" \
  -F "text=这是图片的说明文字" \
  -F "photo=@/path/to/image.jpg"
```

### Python 示例

```python
import requests

# 只发送文本消息
response = requests.post(
    "http://localhost:8000/api/send",
    data={"chat_id": -1001234567890, "text": "Hello, World!"}
)
print(response.json())

# 只发送图片
with open("image.jpg", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/send",
        data={"chat_id": -1001234567890},
        files={"photo": f}
    )
print(response.json())

# 同时发送文本和图片（图片带说明文字）
with open("image.jpg", "rb") as f:
    response = requests.post(
        "http://localhost:8000/api/send",
        data={
            "chat_id": -1001234567890,
            "text": "这是图片的说明文字"
        },
        files={"photo": f}
    )
print(response.json())
```

### JavaScript 示例

```javascript
// 只发送文本消息
const formData1 = new FormData();
formData1.append('chat_id', -1001234567890);
formData1.append('text', 'Hello, World!');

fetch('http://localhost:8000/api/send', {
  method: 'POST',
  body: formData1
})
.then(response => response.json())
.then(data => console.log(data));

// 只发送图片
const formData2 = new FormData();
formData2.append('chat_id', -1001234567890);
formData2.append('photo', fileInput.files[0]);

fetch('http://localhost:8000/api/send', {
  method: 'POST',
  body: formData2
})
.then(response => response.json())
.then(data => console.log(data));

// 同时发送文本和图片
const formData3 = new FormData();
formData3.append('chat_id', -1001234567890);
formData3.append('text', '这是图片的说明文字');
formData3.append('photo', fileInput.files[0]);

fetch('http://localhost:8000/api/send', {
  method: 'POST',
  body: formData3
})
.then(response => response.json())
.then(data => console.log(data));
```

### Node.js 示例（使用 form-data）

```javascript
const FormData = require('form-data');
const fs = require('fs');
const axios = require('axios');

// 只发送文本消息
const formData1 = new FormData();
formData1.append('chat_id', -1001234567890);
formData1.append('text', 'Hello, World!');

axios.post('http://localhost:8000/api/send', formData1, {
  headers: formData1.getHeaders()
})
.then(response => console.log(response.data));

// 同时发送文本和图片
const formData2 = new FormData();
formData2.append('chat_id', -1001234567890);
formData2.append('text', '这是图片的说明文字');
formData2.append('photo', fs.createReadStream('image.jpg'));

axios.post('http://localhost:8000/api/send', formData2, {
  headers: formData2.getHeaders()
})
.then(response => console.log(response.data));
```

## 配置说明

在 `config.json` 中可以配置 HTTP API：

```json
{
    "enable_http_api": true,
    "http_host": "0.0.0.0",
    "http_port": 8000
}
```

- `enable_http_api`: 是否启用 HTTP API，默认为 `true`
- `http_host`: HTTP 服务器监听地址，默认为 `0.0.0.0`（监听所有接口）
- `http_port`: HTTP 服务器端口，默认为 `8000`

## 注意事项

1. **消息队列**: 所有消息都会加入队列，按照配置的延迟和分配策略发送
2. **分配策略**: 同一个群的消息会按照配置的 `distribution_strategy` 分配给不同的客户端
3. **模拟真人操作**: 所有发送都会应用思考时间、延迟、批量延迟等模拟真人操作的逻辑
4. **错误处理**: 如果发送失败，会记录错误日志，但不会返回给 API 调用者（消息已加入队列）
5. **chat_id 格式**: Telegram 群组的 chat_id 通常是负数，例如 `-1001234567890`
6. **内容要求**: 必须提供 `text` 或 `photo` 至少一种，可以同时提供两种
7. **图片说明**: 当同时提供文本和图片时，文本会作为图片的说明文字（caption）

## 获取群组 chat_id

可以通过以下方式获取群组的 chat_id：

1. 使用 Telegram Bot API
2. 使用 Telegram 客户端（如 Telegram Desktop）查看群组信息
3. 使用第三方工具或脚本

注意：chat_id 是负数表示群组，正数表示私聊。
