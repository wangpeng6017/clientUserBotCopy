import logging
import sys
import os
import json
import asyncio
import random
import io
from datetime import datetime, timezone
from typing import List, Dict, Optional, Union
from collections import defaultdict
from urllib.parse import urlparse
from pyrogram import Client
from pyrogram.errors import SessionPasswordNeeded, FloodWait, RPCError
from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse
import uvicorn
import aiohttp

# 加载配置文件
def load_config():
    """加载配置文件"""
    config_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')
    
    if not os.path.exists(config_path):
        print(f"错误: 配置文件不存在: {config_path}")
        print("请复制 config.json.example 为 config.json 并填写配置信息")
        sys.exit(1)
    
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        # 验证必需的配置项
        if 'accounts' not in config:
            # 兼容旧格式：单个 api_id/api_hash
            if 'api_id' in config and 'api_hash' in config:
                # 转换为新格式
                config['accounts'] = [{
                    'api_id': config['api_id'],
                    'api_hash': config['api_hash'],
                    'name': f"account_{config['api_id']}"
                }]
            else:
                print("错误: 配置文件缺少必需的配置项: accounts 或 api_id/api_hash")
                sys.exit(1)
        
        # 验证每个账户配置
        for i, account in enumerate(config['accounts']):
            if 'api_id' not in account or 'api_hash' not in account:
                print(f"错误: 账户 {i+1} 缺少 api_id 或 api_hash")
                sys.exit(1)
            if 'name' not in account:
                account['name'] = f"account_{account['api_id']}"
        
        return config
    except json.JSONDecodeError as e:
        print(f"错误: 配置文件格式错误: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"错误: 加载配置文件失败: {str(e)}")
        sys.exit(1)

# 加载配置
config = load_config()
accounts = config['accounts']
distribution_strategy = config.get('distribution_strategy', 'round_robin')  # round_robin 或 random
# 支持 "round" 作为 "round_robin" 的别名
if distribution_strategy == 'round':
    distribution_strategy = 'round_robin'

# 消息发送配置（防止风控）
send_interval = config.get('send_interval', 2.0)  # 发送间隔（秒），默认2秒
send_jitter = config.get('send_jitter', 1.0)  # 抖动时间（秒），默认1秒，会在0到send_jitter之间随机

# 模拟真人操作的配置
think_time_min = config.get('think_time_min', 0.5)  # 最小思考时间（秒），默认0.5秒，模拟看到消息后的反应时间
think_time_max = config.get('think_time_max', 3.0)  # 最大思考时间（秒），默认3秒
operation_delay_min = config.get('operation_delay_min', 0.3)  # 操作前最小延迟（秒），默认0.3秒，模拟点击、选择等操作时间
operation_delay_max = config.get('operation_delay_max', 1.0)  # 操作前最大延迟（秒），默认1秒
batch_delay_factor = config.get('batch_delay_factor', 0.5)  # 批量消息延迟因子，队列中每多一条消息，额外延迟（秒），默认0.5秒
rest_probability = config.get('rest_probability', 0.05)  # 休息概率，每次发送后有5%概率休息，默认0.05（5%）
rest_time_min = config.get('rest_time_min', 10)  # 最小休息时间（秒），默认10秒
rest_time_max = config.get('rest_time_max', 60)  # 最大休息时间（秒），默认60秒

# 自动清除未读标记配置
auto_mark_read = config.get('auto_mark_read', True)  # 是否自动标记消息为已读，默认 True
mark_read_interval = config.get('mark_read_interval', 300)  # 定期清除未读标记的间隔（秒），默认300秒（5分钟）
# mark_read_on_receive 已废弃（不再监听消息，所以不需要收到消息时立即标记为已读）
mark_read_delay = config.get('mark_read_delay', 0.5)  # 清除每个群组未读标记的延迟（秒），默认0.5秒，避免触发限流

# 验证配置合理性
if send_interval < 0:
    logger.warning(f"send_interval 配置值 {send_interval} 无效，使用默认值 2.0")
    send_interval = 2.0
if send_jitter < 0:
    logger.warning(f"send_jitter 配置值 {send_jitter} 无效，使用默认值 1.0")
    send_jitter = 1.0
if mark_read_delay < 0:
    logger.warning(f"mark_read_delay 配置值 {mark_read_delay} 无效，使用默认值 0.5")
    mark_read_delay = 0.5
if mark_read_interval < 0:
    logger.warning(f"mark_read_interval 配置值 {mark_read_interval} 无效，使用默认值 300")
    mark_read_interval = 300
if think_time_min < 0 or think_time_max < think_time_min:
    logger.warning(f"think_time 配置无效，使用默认值: min=0.5, max=3.0")
    think_time_min, think_time_max = 0.5, 3.0
if operation_delay_min < 0 or operation_delay_max < operation_delay_min:
    logger.warning(f"operation_delay 配置无效，使用默认值: min=0.3, max=1.0")
    operation_delay_min, operation_delay_max = 0.3, 1.0
if batch_delay_factor < 0:
    logger.warning(f"batch_delay_factor 配置值 {batch_delay_factor} 无效，使用默认值 0.5")
    batch_delay_factor = 0.5
if rest_probability < 0 or rest_probability > 1:
    logger.warning(f"rest_probability 配置值 {rest_probability} 无效，使用默认值 0.05")
    rest_probability = 0.05
if rest_time_min < 0 or rest_time_max < rest_time_min:
    logger.warning(f"rest_time 配置无效，使用默认值: min=10, max=60")
    rest_time_min, rest_time_max = 10, 60

# HTTP API 配置（现在只支持 HTTP API，所以总是启用）
http_host = '0.0.0.0'  # HTTP服务器监听地址（固定为0.0.0.0，监听所有接口）
http_port = config.get('http_port', 8000)  # HTTP服务器端口，默认8000

# 验证HTTP配置
if http_port < 1 or http_port > 65535:
    logger.warning(f"http_port 配置值 {http_port} 无效，使用默认值 8000")
    http_port = 8000

# 配置日志路径（支持相对路径和绝对路径）
log_dir_config = config.get('log_dir', 'logs')
if os.path.isabs(log_dir_config):
    # 绝对路径
    log_dir = log_dir_config
else:
    # 相对路径，相对于脚本目录
    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), log_dir_config)

os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, f'client_tguserbot_{datetime.now().strftime("%Y%m%d")}.log')

# 配置日志格式
# 从环境变量或配置中读取日志级别，默认为 INFO
log_level = config.get('log_level', 'INFO').upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)

logger = logging.getLogger(__name__)
logger.info(f"日志文件路径: {log_file}")
logger.info(f"配置了 {len(accounts)} 个账户")
logger.info(f"分配策略: {distribution_strategy}")

# 创建多个 Pyrogram 客户端
clients: List[Client] = []
workdir = os.path.dirname(os.path.abspath(__file__))

for account in accounts:
    api_id = account['api_id']
    api_hash = account['api_hash']
    name = account['name']
    session_name = f'session_{name}_{api_id}'
    
    client = Client(
        session_name,
        api_id=api_id,
        api_hash=api_hash,
        workdir=workdir
    )
    clients.append(client)
    logger.info(f"创建客户端: {name} (api_id: {api_id}, session: {session_name})")

# 记录启动时间，用于过滤历史消息
start_time = None

# 消息队列，用于排队发送
message_queue = asyncio.Queue()

# 每个群组的客户端轮询索引（用于 round_robin 策略）
chat_client_index: Dict[int, int] = defaultdict(int)

# 每个群组每个客户端的使用计数（用于 random 策略，确保更均匀的分配）
chat_client_usage: Dict[int, Dict[int, int]] = defaultdict(lambda: defaultdict(int))

# 自动标记消息为已读的任务（定期清除所有群组的未读标记）
async def auto_mark_read_task():
    """定期清除所有群组的未读消息标记和被回复标记"""
    if not auto_mark_read:
        return
    
    while True:
        try:
            await asyncio.sleep(mark_read_interval)
            logger.info(f"开始定期清除所有群组的未读消息标记...")
            
            for i, client in enumerate(clients):
                client_name = accounts[i]['name']
                try:
                    # 检查客户端是否连接
                    if not client.is_connected:
                        logger.warning(f"[{client_name}] 客户端未连接，跳过清除未读标记")
                        continue
                    
                    # 获取所有对话（包括群组）
                    processed_chats = set()
                    chat_count = 0
                    async for dialog in client.get_dialogs():
                        chat = dialog.chat
                        chat_id = chat.id
                        
                        # 只处理群组和超级群组，跳过私聊
                        if chat.type.name not in ['GROUP', 'SUPERGROUP']:
                            continue
                        
                        # 避免重复处理同一个群组
                        if chat_id in processed_chats:
                            continue
                        processed_chats.add(chat_id)
                        chat_count += 1
                        
                        try:
                            # 检查客户端是否连接
                            if not client.is_connected:
                                logger.warning(f"[{client_name}] 客户端未连接，跳过群组 {chat_id}")
                                continue
                            
                            # 标记该群组的所有消息为已读（清除未读标记和被回复标记）
                            await client.read_chat_history(chat_id)
                            logger.debug(f"[{client_name}] 已清除群组 {chat_id} 的未读消息标记")
                            
                            # 添加延迟，避免触发限流
                            if mark_read_delay > 0:
                                await asyncio.sleep(mark_read_delay)
                        except FloodWait as e:
                            # 处理限流错误，等待指定时间
                            wait_time = e.value
                            logger.warning(f"[{client_name}] 触发限流，等待 {wait_time} 秒后继续...")
                            await asyncio.sleep(wait_time)
                            # 重试一次
                            try:
                                await client.read_chat_history(chat_id)
                                logger.debug(f"[{client_name}] 重试后已清除群组 {chat_id} 的未读消息标记")
                            except Exception as e2:
                                logger.warning(f"[{client_name}] 重试清除群组 {chat_id} 未读标记时出错: {str(e2)}")
                        except Exception as e:
                            logger.warning(f"[{client_name}] 清除群组 {chat_id} 未读标记时出错: {str(e)}")
                    
                    logger.info(f"[{client_name}] 完成清除未读标记，共处理 {len(processed_chats)} 个群组（遍历了 {chat_count} 个群组）")
                except Exception as e:
                    logger.error(f"[{client_name}] 定期清除未读标记任务出错: {str(e)}", exc_info=True)
            
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"定期清除未读标记任务发生错误: {str(e)}", exc_info=True)
            await asyncio.sleep(60)  # 出错后等待1分钟再继续

# 消息数据结构
class MessageTask:
    def __init__(self, chat_id, client_index=None, text=None, photo=None):
        self.chat_id = chat_id  # 目标群组ID（可以是整数或字符串，如 @username）
        self.client_index = client_index  # 指定使用哪个客户端发送（如果为None，由分配策略决定）
        self.text = text  # 文本内容（可选）
        self.photo = photo  # 图片数据（bytes，可选）

def get_client_for_chat(chat_id: int) -> Client:
    """根据分配策略获取用于发送消息的客户端"""
    if len(clients) == 0:
        raise ValueError("没有可用的客户端")
    
    if distribution_strategy == 'round_robin':
        # 轮询策略：每个群组按顺序使用不同的客户端
        index = chat_client_index[chat_id] % len(clients)
        chat_client_index[chat_id] += 1
        selected_client = clients[index]
        logger.debug(f"轮询分配：群组 {chat_id} 使用客户端 {accounts[index]['name']} (索引: {index})")
        return selected_client
    elif distribution_strategy == 'random':
        # 随机策略：使用加权随机分配，确保更均匀
        # 优先选择使用次数较少的客户端，但仍然保持随机性
        usage = chat_client_usage[chat_id]
        
        # 计算每个客户端的使用次数
        usage_counts = [usage.get(i, 0) for i in range(len(clients))]
        min_usage = min(usage_counts) if usage_counts else 0
        
        # 找出使用次数最少的客户端（可能有多个）
        least_used_indices = [i for i, count in enumerate(usage_counts) if count == min_usage]
        
        # 如果有多个使用次数最少的客户端，随机选择一个
        # 这样可以确保均匀分配，同时保持随机性
        if len(least_used_indices) > 1:
            index = random.choice(least_used_indices)
        else:
            # 如果只有一个最少使用的，就选它
            index = least_used_indices[0]
        
        # 更新使用计数
        chat_client_usage[chat_id][index] += 1
        
        selected_client = clients[index]
        logger.debug(f"随机分配（加权）：群组 {chat_id} 使用客户端 {accounts[index]['name']} (索引: {index}, 使用次数: {usage[index]})")
        return selected_client
    else:
        # 默认使用第一个客户端
        logger.warning(f"未知的分配策略: {distribution_strategy}，使用第一个客户端")
        return clients[0]

async def message_sender():
    """消息发送任务，从队列中取出消息并按间隔发送（使用客户端模拟操作）"""
    logger.info("消息发送任务已启动，等待队列中的消息...")
    while True:
        try:
            # 从队列中获取消息（会阻塞直到有消息）
            task = await message_queue.get()
            
            # 选择用于发送的客户端（根据分配策略）
            # 如果指定了 client_index，则使用指定的客户端
            if task.client_index is not None:
                send_client_index = task.client_index
            else:
                # 使用分配策略选择客户端
                send_client = get_client_for_chat(task.chat_id)
                send_client_index = clients.index(send_client)
            
            send_client = clients[send_client_index]
            send_client_name = accounts[send_client_index]['name']
            
            # 记录发送信息
            content_desc = []
            if task.text:
                content_desc.append("文本")
            if task.photo:
                content_desc.append("图片")
            logger.info(f"从队列获取到发送任务，准备发送到群组 {task.chat_id}...")
            logger.info(f"使用客户端 {send_client_name} 发送消息到群组 {task.chat_id}（内容: {', '.join(content_desc) if content_desc else '空'}）")
            
            # ========== 模拟真人操作流程 ==========
            # 1. 思考时间：模拟看到消息后的反应时间（使用正态分布，更自然）
            think_time = max(think_time_min, min(think_time_max, 
                random.gauss((think_time_min + think_time_max) / 2, (think_time_max - think_time_min) / 4)))
            logger.debug(f"💭 模拟思考时间: {think_time:.2f} 秒...")
            await asyncio.sleep(think_time)
            
            # 2. 基础发送间隔 + 随机抖动（使用更不规律的分布）
            # 使用 Beta 分布，让延迟更集中在中间值，但偶尔会有较大波动
            beta_value = random.betavariate(2, 2)  # Beta(2,2) 分布，集中在中间
            jitter = send_jitter * beta_value
            base_delay = send_interval + jitter
            
            # 3. 批量消息额外延迟：如果队列中有多条消息，增加延迟（模拟真人不会立即处理所有消息）
            queue_size = message_queue.qsize()
            batch_delay = queue_size * batch_delay_factor
            if queue_size > 0:
                logger.debug(f"📦 队列中有 {queue_size} 条待处理消息，增加批量延迟: {batch_delay:.2f} 秒")
            
            total_delay = base_delay + batch_delay
            logger.info(f"⏱️  等待 {total_delay:.2f} 秒后发送（基础间隔: {send_interval}秒，抖动: {jitter:.2f}秒，批量延迟: {batch_delay:.2f}秒）...")
            
            # 等待延迟时间
            await asyncio.sleep(total_delay)
            
            # 4. 操作前延迟：模拟点击、选择等操作时间
            operation_delay = random.uniform(operation_delay_min, operation_delay_max)
            logger.debug(f"👆 模拟操作延迟: {operation_delay:.2f} 秒（点击、选择等）...")
            await asyncio.sleep(operation_delay)
            
            # 发送消息
            try:
                # 检查客户端是否连接
                if not send_client.is_connected:
                    logger.error(f"客户端 {send_client_name} 未连接，无法发送消息")
                    raise ConnectionError(f"客户端 {send_client_name} 未连接")
                
                logger.info(f"开始使用客户端 {send_client_name} 发送消息到群组 {task.chat_id}...")
                
                # 必须先获取群组信息，这样 Pyrogram 才能解析 chat_id
                # 如果客户端未加入群组，get_chat 会失败
                try:
                    chat = await send_client.get_chat(task.chat_id)
                    chat_title = chat.title if hasattr(chat, 'title') and chat.title else 'N/A'
                    logger.info(f"✓ 验证群组 {task.chat_id} 存在，标题: {chat_title}")
                except Exception as e:
                    error_msg = str(e)
                    logger.error(f"✗ 无法获取群组 {task.chat_id} 信息: {error_msg}")
                    logger.error(f"   原因：客户端 {send_client_name} 可能未加入该群组，或 chat_id 不正确")
                    logger.error(f"   解决方案：")
                    logger.error(f"     1. 确保客户端 {send_client_name} 已加入群组 {task.chat_id}")
                    logger.error(f"     2. 如果使用数字 ID，确保格式正确（群组 ID 通常是负数）")
                    logger.error(f"     3. 可以尝试使用群组用户名（如 @groupname）代替数字 ID")
                    # 不抛出异常，记录错误后继续处理下一条消息
                    message_queue.task_done()
                    continue
                
                sent_message = None
                if task.photo:
                    # 发送图片（可以带说明文字）
                    if isinstance(task.photo, bytes):
                        # Pyrogram 需要文件对象，将 bytes 转换为 BytesIO
                        photo_file = io.BytesIO(task.photo)
                        sent_message = await send_client.send_photo(
                            chat_id=task.chat_id,
                            photo=photo_file,
                            caption=task.text if task.text else None
                        )
                    else:
                        logger.error(f"图片内容格式错误，应为 bytes 类型")
                        raise ValueError("图片内容格式错误")
                elif task.text:
                    # 只发送文本消息
                    sent_message = await send_client.send_message(
                        chat_id=task.chat_id,
                        text=task.text
                    )
                else:
                    logger.error(f"消息内容为空，必须提供文本或图片")
                    raise ValueError("消息内容为空")
                
                if sent_message:
                    msg_type = "图片" if task.photo else "文本"
                    logger.info(f"✓ 已通过客户端 {send_client_name} 发送{msg_type}消息到群组 {task.chat_id} (消息ID: {sent_message.id})")
                else:
                    logger.warning(f"⚠ 客户端 {send_client_name} 发送消息返回 None")
            
            except FloodWait as e:
                # 处理限流错误
                wait_time = e.value
                logger.warning(f"✗ 客户端 {send_client_name} 触发限流，需要等待 {wait_time} 秒")
                await asyncio.sleep(wait_time)
                # 重试一次
                try:
                    if task.photo:
                        # Pyrogram 需要文件对象，将 bytes 转换为 BytesIO
                        photo_file = io.BytesIO(task.photo)
                        sent_message = await send_client.send_photo(
                            chat_id=task.chat_id,
                            photo=photo_file,
                            caption=task.text if task.text else None
                        )
                    elif task.text:
                        sent_message = await send_client.send_message(
                            chat_id=task.chat_id,
                            text=task.text
                        )
                    if sent_message:
                        logger.info(f"✓ 重试后已通过客户端 {send_client_name} 发送消息到群组 {task.chat_id} (消息ID: {sent_message.id})")
                except Exception as e_retry:
                    logger.error(f"✗ 客户端 {send_client_name} 重试发送消息也失败: {str(e_retry)}", exc_info=True)
                    raise e_retry
            except ValueError as e:
                error_msg = str(e)
                if "Peer id invalid" in error_msg or "ID not found" in error_msg:
                    # chat_id 无效或客户端未加入群组
                    logger.error(f"✗ 客户端 {send_client_name} 无法发送消息到群组 {task.chat_id}: 客户端可能未加入该群组，或 chat_id 格式不正确")
                    logger.error(f"   提示：请确保客户端 {send_client_name} 已加入群组 {task.chat_id}")
                    logger.error(f"   提示：如果使用用户名，请使用 @username 格式；如果使用数字 ID，请确保格式正确")
                    # 不抛出异常，记录错误后继续处理下一条消息
                else:
                    logger.error(f"✗ 客户端 {send_client_name} 发送消息到群组 {task.chat_id} 时发生错误: {error_msg}", exc_info=True)
                    raise
            except Exception as e:
                error_msg = str(e)
                if "Peer id invalid" in error_msg or "ID not found" in error_msg:
                    # chat_id 无效或客户端未加入群组
                    logger.error(f"✗ 客户端 {send_client_name} 无法发送消息到群组 {task.chat_id}: 客户端可能未加入该群组，或 chat_id 格式不正确")
                    logger.error(f"   提示：请确保客户端 {send_client_name} 已加入群组 {task.chat_id}")
                    logger.error(f"   提示：如果使用用户名，请使用 @username 格式；如果使用数字 ID，请确保格式正确")
                    # 不抛出异常，记录错误后继续处理下一条消息
                else:
                    logger.error(f"✗ 客户端 {send_client_name} 发送消息到群组 {task.chat_id} 时发生错误: {error_msg}", exc_info=True)
                    raise
            
            # 标记任务完成
            message_queue.task_done()
            queue_size = message_queue.qsize()
            logger.info(f"✅ 消息发送完成，当前队列剩余: {queue_size} 条")
            
            # 5. 偶尔的休息时间：模拟真人不会一直盯着屏幕（随机休息）
            if random.random() < rest_probability:
                rest_time = random.uniform(rest_time_min, rest_time_max)
                logger.info(f"😴 模拟休息时间: {rest_time:.1f} 秒（随机休息，模拟真人行为）...")
                await asyncio.sleep(rest_time)
            
        except asyncio.CancelledError:
            logger.info("消息发送任务已取消")
            break
        except Exception as e:
            logger.error(f"消息发送任务发生错误: {str(e)}", exc_info=True)
            await asyncio.sleep(1)  # 出错后等待1秒再继续

# 已移除消息监听功能，现在只通过 HTTP API 发送消息

# 启动消息发送任务的辅助函数
async def start_sender():
    """启动消息发送任务"""
    await message_sender()

# ========== HTTP API 部分 ==========
# 创建 FastAPI 应用
app = FastAPI(title="Telegram Client User Bot API", version="1.0.0")

@app.get("/")
async def root():
    """API 根路径"""
    return {
        "status": "ok",
        "service": "Telegram Client User Bot API",
        "version": "1.0.0",
        "endpoints": {
            "send": "/api/send",
            "health": "/api/health"
        }
    }

@app.get("/api/health")
async def health():
    """健康检查"""
    connected_clients = sum(1 for client in clients if client.is_connected)
    return {
        "status": "ok",
        "connected_clients": connected_clients,
        "total_clients": len(clients),
        "queue_size": message_queue.qsize()
    }

@app.post("/api/send")
async def send(
    request: Request,
    chat_id: Union[int, str] = Form(...),
    text: Optional[str] = Form(None)
):
    """发送消息（支持文本和图片，可以同时发送）
    
    参数说明:
    - chat_id: 目标群组的 chat_id（必需）
    - text: 文本内容（可选）
    - photo: 图片文件或图片 URL（字符串），可选
       - 如果传入文件：使用 multipart/form-data 文件上传，参数名为 photo
       - 如果传入 URL：使用 multipart/form-data 文本字段，参数名为 photo，值为 URL 字符串
       API 会自动判断是文件还是 URL
    """
    try:
        # 从请求中获取 photo 字段（可能是文件或字符串）
        form = await request.form()
        photo = form.get("photo")
        
        # 验证至少提供一种内容
        if not text and not photo:
            raise HTTPException(status_code=400, detail="必须提供 text 或 photo 至少一种内容")
        
        # 处理 chat_id：支持整数或字符串格式
        processed_chat_id = chat_id
        if isinstance(chat_id, str):
            # 如果是 @username 格式，保持原样
            if chat_id.startswith('@'):
                processed_chat_id = chat_id
            else:
                # 尝试转换为整数
                try:
                    processed_chat_id = int(chat_id)
                except ValueError:
                    # 如果无法转换，添加 @ 前缀（可能是用户名，不带@）
                    processed_chat_id = f"@{chat_id}"
        elif isinstance(chat_id, int):
            processed_chat_id = chat_id
        
        photo_data = None
        photo_source = None
        photo_filename = None
        photo_url_value = None
        
        if photo:
            # 判断 photo 是文件上传还是 URL 字符串
            # 检查是否有 filename 和 read 方法（文件上传的特征）
            if hasattr(photo, 'filename') and hasattr(photo, 'read'):
                # 文件上传方式
                try:
                    photo_data = await photo.read()
                    photo_source = "文件上传"
                    photo_filename = getattr(photo, 'filename', 'image.jpg')
                    
                    if not photo_data:
                        raise HTTPException(status_code=400, detail="图片文件为空")
                    
                    # 验证是否为图片格式（简单检查）
                    content_type = getattr(photo, 'content_type', '')
                    if content_type and not content_type.startswith('image/'):
                        logger.warning(f"上传的文件可能不是图片: {content_type}")
                except Exception as e:
                    logger.error(f"读取上传文件时出错: {str(e)}", exc_info=True)
                    raise HTTPException(status_code=400, detail=f"读取上传文件失败: {str(e)}")
            elif isinstance(photo, str):
                # URL 字符串方式
                photo_url_value = photo
                photo_source = "URL"
                
                # 验证 URL 格式
                if not (photo_url_value.startswith('http://') or photo_url_value.startswith('https://')):
                    raise HTTPException(status_code=400, detail="photo URL 必须以 http:// 或 https:// 开头")
                
                # 从 URL 下载图片
                try:
                    async with aiohttp.ClientSession() as session:
                        async with session.get(photo_url_value, timeout=aiohttp.ClientTimeout(total=30)) as response:
                            if response.status != 200:
                                raise HTTPException(status_code=400, detail=f"下载图片失败，HTTP 状态码: {response.status}")
                            
                            photo_data = await response.read()
                            if not photo_data:
                                raise HTTPException(status_code=400, detail="从 URL 下载的图片为空")
                            
                            # 验证内容类型
                            content_type = response.headers.get('Content-Type', '')
                            if content_type and not content_type.startswith('image/'):
                                logger.warning(f"从 URL 下载的文件可能不是图片: {content_type}")
                            
                            # 从 URL 提取文件名
                            parsed_url = urlparse(photo_url_value)
                            photo_filename = os.path.basename(parsed_url.path) or 'image.jpg'
                            
                            logger.info(f"✓ 成功从 URL 下载图片，大小: {len(photo_data)} 字节")
                except aiohttp.ClientError as e:
                    raise HTTPException(status_code=400, detail=f"下载图片失败: {str(e)}")
                except Exception as e:
                    raise HTTPException(status_code=400, detail=f"处理图片 URL 时出错: {str(e)}")
            else:
                # 添加调试信息
                logger.error(f"photo 类型错误: type={type(photo)}, value={photo}")
                raise HTTPException(status_code=400, detail=f"photo 参数必须是文件或 URL 字符串，当前类型: {type(photo).__name__}")
        
        # 创建任务
        task = MessageTask(
            chat_id=processed_chat_id,
            text=text,
            photo=photo_data
        )
        await message_queue.put(task)
        
        # 记录日志
        content_desc = []
        if text:
            content_desc.append(f"文本({len(text)}字符)")
        if photo_data:
            content_desc.append(f"图片({len(photo_data)}字节, 来源: {photo_source})")
        logger.info(f"📥 HTTP API: 收到发送请求，chat_id={processed_chat_id}, 内容={', '.join(content_desc)}, 队列长度={message_queue.qsize()}")
        
        # 返回响应
        response = {
            "status": "success",
            "message": "消息已加入队列",
            "chat_id": processed_chat_id,
            "queue_size": message_queue.qsize()
        }
        if text:
            response["has_text"] = True
        if photo_data:
            response["has_photo"] = True
            response["photo_size"] = len(photo_data)
            response["photo_source"] = photo_source
            if photo_filename:
                response["photo_filename"] = photo_filename
            # 如果是 URL 方式，也返回 URL
            if photo_source == "URL" and photo_url_value:
                response["photo_url"] = photo_url_value
        
        return response
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"处理发送请求时出错: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"服务器内部错误: {str(e)}")

async def start_http_server():
    """启动HTTP服务器（在后台运行）"""
    try:
        config_uvicorn = uvicorn.Config(
            app=app,
            host=http_host,
            port=http_port,
            log_level="info",
            access_log=False  # 禁用访问日志，避免与主日志冲突
        )
        server = uvicorn.Server(config_uvicorn)
        logger.info(f"🌐 HTTP API 服务器启动在 http://{http_host}:{http_port}")
        logger.info(f"📡 API 端点:")
        logger.info(f"   - POST /api/send - 发送消息（支持文本和图片，可同时发送）")
        logger.info(f"     参数: chat_id (必需), text (可选), photo (可选), photo_url (可选)")
        logger.info(f"   - GET  /api/health - 健康检查")
        await server.serve()
    except asyncio.CancelledError:
        logger.info("HTTP API 服务器已停止")
        raise
    except Exception as e:
        logger.error(f"HTTP API 服务器启动失败: {str(e)}", exc_info=True)

async def main():
    """主函数"""
    try:
        logger.info("正在启动 Telegram 客户端（Pyrogram）...")
        logger.info(f"共配置 {len(accounts)} 个账户，将创建 {len(clients)} 个客户端")
        
        # 启动所有客户端
        started_clients = []
        for i, client in enumerate(clients):
            account = accounts[i]
            session_file = f'session_{account["name"]}_{account["api_id"]}.session'
            session_exists = os.path.exists(session_file)
            
            if not session_exists:
                logger.info(f"[{account['name']}] 首次登录，需要输入电话号码和验证码")
            else:
                logger.info(f"[{account['name']}] 找到已保存的 session 文件，将自动登录")
            
            try:
                if not client.is_connected:
                    await client.start()
                started_clients.append(client)
                logger.info(f"✓ [{account['name']}] Telegram 客户端已启动并登录成功")
            except Exception as e:
                logger.error(f"✗ [{account['name']}] 启动失败: {str(e)}", exc_info=True)
                raise
        
        logger.info("=" * 60)
        logger.info(f"✓ 所有 {len(started_clients)} 个客户端已启动")
        logger.info(f"发送间隔: {send_interval}秒，抖动时间: 0-{send_jitter}秒")
        logger.info(f"分配策略: {distribution_strategy}")
        logger.info("=" * 60)
        logger.info("📢 程序已启动，等待 HTTP API 请求...")
        logger.info("📢 通过 HTTP API 发送的消息将按配置的策略分配给不同客户端")
        logger.info("=" * 60)
        
        # 在客户端启动后，启动消息发送任务和自动标记已读任务
        sender_task = asyncio.create_task(start_sender())
        mark_read_task = None
        if auto_mark_read:
            mark_read_task = asyncio.create_task(auto_mark_read_task())
            logger.info("自动标记已读任务已启动...")
        logger.info("消息队列发送任务已启动，等待消息...")
        
        # 启动HTTP服务器
        http_task = asyncio.create_task(start_http_server())
        logger.info("HTTP API 服务器任务已启动...")
        # 给HTTP服务器一点时间启动
        await asyncio.sleep(0.5)
        
        try:
            # 使用 idle() 保持运行（Pyrogram 推荐方式）
            # 注意：idle() 会阻塞，但HTTP服务器在独立任务中运行，不会冲突
            from pyrogram import idle
            await idle()
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        finally:
            # 取消所有任务
            sender_task.cancel()
            if mark_read_task:
                mark_read_task.cancel()
            if http_task:
                http_task.cancel()
            
            try:
                await sender_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"取消发送任务时出错: {str(e)}")
            
            if mark_read_task:
                try:
                    await mark_read_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"取消自动标记已读任务时出错: {str(e)}")
            
            if http_task:
                try:
                    await http_task
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.warning(f"取消HTTP服务器任务时出错: {str(e)}")
            
            # 等待队列中的消息发送完成（最多等待30秒）
            if not message_queue.empty():
                logger.info(f"等待队列中的 {message_queue.qsize()} 条消息发送完成...")
                try:
                    await asyncio.wait_for(message_queue.join(), timeout=30.0)
                except asyncio.TimeoutError:
                    logger.warning("等待消息发送超时，强制关闭")
            
            # 停止所有客户端
            for i, client in enumerate(started_clients):
                try:
                    await client.stop()
                    logger.info(f"✓ [{accounts[i]['name']}] Telegram 客户端已断开连接")
                except Exception as e:
                    logger.warning(f"停止客户端 {accounts[i]['name']} 时出错: {str(e)}")
            
    except SessionPasswordNeeded:
        logger.error("需要两步验证密码，请在交互式环境中运行一次以完成登录")
        raise
    except Exception as e:
        logger.error(f"程序启动失败: {str(e)}", exc_info=True)
        raise

if __name__ == '__main__':
    try:
        # 检查所有 session 文件
        logger.info("检查 session 文件状态...")
        for account in accounts:
            session_file = f'session_{account["name"]}_{account["api_id"]}.session'
            if os.path.exists(session_file):
                logger.info(f"✓ [{account['name']}] 找到已保存的 session 文件: {session_file}")
            else:
                logger.info(f"✗ [{account['name']}] 未找到 session 文件: {session_file}")
                logger.info("将进入首次登录流程，需要输入电话号码和验证码")
        
        if any(not os.path.exists(f'session_{acc["name"]}_{acc["api_id"]}.session') for acc in accounts):
            logger.info("=" * 60)
            logger.info("📱 首次登录步骤：")
            logger.info("1. 输入电话号码（格式：+86 13800138000）")
            logger.info("2. 输入 Telegram 发送的验证码")
            logger.info("3. 如果启用了两步验证，输入密码")
            logger.info("=" * 60)
        
        # Pyrogram 2.0 的正确启动方式
        # 使用第一个客户端来运行主函数（所有客户端会在 main() 中启动）
        if len(clients) > 0:
            clients[0].run(main())
        else:
            logger.error("没有可用的客户端")
            sys.exit(1)
    except KeyboardInterrupt:
        logger.info("程序已退出")
    except SessionPasswordNeeded:
        logger.error("需要两步验证密码，请在交互式环境中运行一次以完成登录")
        sys.exit(1)
    except Exception as e:
        logger.error(f"程序运行失败: {str(e)}", exc_info=True)
        sys.exit(1)
