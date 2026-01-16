import logging
import sys
import os
import json
import asyncio
import random
from datetime import datetime, timezone
from typing import List, Dict, Optional
from collections import defaultdict
from pyrogram import Client, filters
from pyrogram.errors import SessionPasswordNeeded

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
        
        if 'target_bot_username' not in config:
            print("错误: 配置文件缺少必需的配置项: target_bot_username")
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
target_bot_username = config['target_bot_username']
distribution_strategy = config.get('distribution_strategy', 'round_robin')  # round_robin 或 random

# 消息发送配置（防止风控）
send_interval = config.get('send_interval', 2.0)  # 发送间隔（秒），默认2秒
send_jitter = config.get('send_jitter', 1.0)  # 抖动时间（秒），默认1秒，会在0到send_jitter之间随机

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

# 已处理消息的去重集合（使用消息的唯一标识）
# 格式：f"{chat_id}_{sender_id}_{message_date}_{message_text_hash}"
# 值：消息处理时间（用于定期清理）
processed_messages: Dict[str, float] = {}

# 消息去重锁（确保多客户端并发时不会重复处理）
message_dedup_lock = asyncio.Lock()

# 清理旧消息记录的任务（每5分钟清理一次，保留最近30分钟的记录）
async def cleanup_processed_messages():
    """定期清理已处理消息记录"""
    while True:
        try:
            await asyncio.sleep(300)  # 每5分钟执行一次
            current_time = datetime.now().timestamp()
            cutoff_time = current_time - 1800  # 30分钟前
            
            # 清理30分钟前的记录
            keys_to_remove = [
                key for key, timestamp in processed_messages.items()
                if timestamp < cutoff_time
            ]
            
            for key in keys_to_remove:
                del processed_messages[key]
            
            if keys_to_remove:
                logger.info(f"清理了 {len(keys_to_remove)} 条旧的已处理消息记录，当前记录数: {len(processed_messages)}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"清理已处理消息记录时出错: {str(e)}", exc_info=True)

# 消息数据结构
class MessageTask:
    def __init__(self, chat_id, from_chat_id, message_id, user_type="", client_index=None, received_by_client_index=None):
        self.chat_id = chat_id  # 目标群组ID
        self.from_chat_id = from_chat_id  # 源消息所在群组ID
        self.message_id = message_id  # 源消息ID（这是收到消息的客户端看到的ID）
        self.user_type = user_type
        self.client_index = client_index  # 指定使用哪个客户端发送（如果为None，由分配策略决定）
        self.received_by_client_index = received_by_client_index  # 收到消息的客户端索引（用于复制消息）

def get_client_for_chat(chat_id: int) -> Client:
    """根据分配策略获取用于发送消息的客户端"""
    if len(clients) == 0:
        raise ValueError("没有可用的客户端")
    
    if distribution_strategy == 'round_robin':
        # 轮询策略：每个群组按顺序使用不同的客户端
        index = chat_client_index[chat_id] % len(clients)
        chat_client_index[chat_id] += 1
        return clients[index]
    elif distribution_strategy == 'random':
        # 随机策略：随机选择一个客户端
        return random.choice(clients)
    else:
        # 默认使用第一个客户端
        return clients[0]

async def message_sender():
    """消息发送任务，从队列中取出消息并按间隔发送（使用客户端模拟操作）"""
    logger.info("消息发送任务已启动，等待队列中的消息...")
    while True:
        try:
            # 从队列中获取消息（会阻塞直到有消息）
            task = await message_queue.get()
            logger.info(f"从队列获取到消息，准备复制到群组 {task.chat_id}...")
            
            # 选择用于发送的客户端
            # 优先使用收到消息的客户端来复制（因为它能看到正确的 message_id）
            # 如果指定了 client_index，则使用指定的客户端
            if task.client_index is not None:
                send_client = clients[task.client_index]
                send_client_name = accounts[task.client_index]['name']
            else:
                send_client = get_client_for_chat(task.chat_id)
                send_client_name = accounts[clients.index(send_client)]['name']
            
            # 用于复制消息的客户端（必须使用收到消息的客户端，因为它能看到正确的 message_id）
            if task.received_by_client_index is not None:
                copy_client = clients[task.received_by_client_index]
                copy_client_name = accounts[task.received_by_client_index]['name']
            else:
                # 如果没有记录收到消息的客户端，使用发送客户端（降级方案）
                copy_client = send_client
                copy_client_name = send_client_name
                logger.warning(f"未记录收到消息的客户端，使用发送客户端 {copy_client_name} 来复制")
            
            logger.info(f"使用客户端 {send_client_name} 发送消息到群组 {task.chat_id}（使用客户端 {copy_client_name} 复制消息）")
            
            # 计算延迟时间（基础间隔 + 随机抖动）
            jitter = random.uniform(0, send_jitter)
            delay = send_interval + jitter
            logger.info(f"等待 {delay:.2f} 秒后发送（间隔: {send_interval}秒，抖动: {jitter:.2f}秒）...")
            
            # 等待延迟时间
            await asyncio.sleep(delay)
            
            # 使用客户端模拟操作：copy_message（不带转发标头，模拟用户复制粘贴）
            # 重要：必须使用收到消息的客户端来复制，因为它能看到正确的 message_id
            try:
                logger.info(f"开始使用客户端 {copy_client_name} 模拟操作复制消息到群组 {task.chat_id}...")
                
                # 使用收到消息的客户端来复制消息（因为它能看到正确的 message_id）
                copied_message = await copy_client.copy_message(
                    chat_id=task.chat_id,
                    from_chat_id=task.from_chat_id,
                    message_id=task.message_id
                )
                
                if copied_message:
                    logger.info(f"✓ 已通过客户端 {copy_client_name} 模拟操作复制{task.user_type}消息到群组 {task.chat_id} (消息ID: {copied_message.id})")
                else:
                    logger.warning(f"⚠ 客户端 {copy_client_name} 复制消息返回 None，可能消息为空或无法复制")
                
            except Exception as e:
                logger.error(f"✗ 客户端 {copy_client_name} 复制消息到群组 {task.chat_id} 时发生错误: {str(e)}", exc_info=True)
                # 如果 copy_message 失败，尝试降级为 send_message（但这不是客户端模拟操作）
                try:
                    logger.warning(f"尝试降级方案：获取原始消息后重新发送...")
                    original_message = await copy_client.get_messages(task.from_chat_id, task.message_id)
                    if original_message and original_message.text:
                        await send_client.send_message(task.chat_id, original_message.text)
                        logger.info(f"✓ 已通过客户端 {send_client_name} 降级方案发送消息到群组 {task.chat_id}")
                    else:
                        logger.error(f"原始消息无文本内容或无法获取，无法降级发送")
                except Exception as e2:
                    logger.error(f"✗ 客户端 {copy_client_name} 降级方案也失败: {str(e2)}", exc_info=True)
            
            # 标记任务完成
            message_queue.task_done()
            logger.info(f"消息发送完成，当前队列剩余: {message_queue.qsize()} 条")
            
        except asyncio.CancelledError:
            logger.info("消息发送任务已取消")
            break
        except Exception as e:
            logger.error(f"消息发送任务发生错误: {str(e)}", exc_info=True)
            await asyncio.sleep(1)  # 出错后等待1秒再继续

def create_message_handler(client_index: int):
    """为每个客户端创建消息处理器"""
    client = clients[client_index]
    client_name = accounts[client_index]['name']
    
    @client.on_message(filters.all)
    async def message_handler(client, message):
        """处理收到的消息"""
        global start_time
        try:
            # 记录启动时间（首次收到消息时）
            if start_time is None:
                from datetime import timezone
                start_time = datetime.now(timezone.utc)
                logger.info(f"首次收到消息，启动时间: {start_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
            
            # 记录所有收到的消息（用于调试）
            logger.info(f"🔔 [{client_name}] 收到新消息 - 消息ID: {message.id}, 群组ID: {message.chat.id}, 是否群组: {message.chat.type}")
            
            # 检查消息时间，只处理启动后的消息
            message_time = message.date
            # 确保时间对象都有时区信息，统一转换为 UTC 进行比较
            if message_time.tzinfo is None:
                # 如果没有时区信息，假设是 UTC
                from datetime import timezone
                message_time = message_time.replace(tzinfo=timezone.utc)
            
            if message_time < start_time:
                # 这是历史消息，忽略
                logger.info(f"⏮️ [{client_name}] 忽略历史消息 ID {message.id} (消息时间: {message_time}, 启动时间: {start_time})")
                return
            
            logger.info(f"✅ [{client_name}] 消息时间检查通过，继续处理...")
            
            # 获取发送者信息
            sender = message.from_user
            if sender:
                sender_info = f"用户名: {sender.username or '无用户名'}, ID: {sender.id}, 是否机器人: {sender.is_bot}"
                logger.info(f"👤 [{client_name}] 发送者信息 - {sender_info}, 群组: {message.chat.id}, 消息ID: {message.id}")
            else:
                logger.warning(f"⚠️ [{client_name}] 无法获取发送者信息，sender 为 None")
                return
            
            # 判断是否为目标用户（可以是机器人或普通用户）
            logger.info(f"🔍 [{client_name}] 检查用户名匹配 - 目标: '{target_bot_username}', 实际: '{sender.username if sender else None}'")
            
            if sender and sender.username == target_bot_username:
                logger.info(f"✅ [{client_name}] 匹配到目标用户: {sender.username} (ID: {sender.id})")
                
                # 使用锁确保去重检查的原子性
                async with message_dedup_lock:
                    # 生成消息的唯一标识（用于去重）
                    # 使用：chat_id + sender_id + message_date（精确到秒，忽略毫秒）+ message_text前200字符的hash
                    # 注意：不同客户端看到的 message.id 可能不同，所以不能使用 message.id
                    
                    # 处理消息日期时间（精确到秒，忽略毫秒和时区差异）
                    if message.date:
                        # 转换为 UTC 并只保留到秒
                        if message.date.tzinfo is None:
                            msg_date_utc = message.date.replace(tzinfo=timezone.utc)
                        else:
                            msg_date_utc = message.date.astimezone(timezone.utc)
                        # 只保留到秒，忽略微秒
                        msg_date_utc = msg_date_utc.replace(microsecond=0)
                        message_date_str = msg_date_utc.strftime('%Y%m%d%H%M%S')
                    else:
                        message_date_str = ""
                    
                    # 处理消息文本（取前200字符，确保hash稳定）
                    message_text = (message.text or message.caption or "").strip()
                    if message_text:
                        # 只取前200字符，避免文本过长导致hash不稳定
                        message_text_for_hash = message_text[:200]
                        message_text_hash = hash(message_text_for_hash)
                    else:
                        # 如果没有文本，使用媒体类型作为标识
                        if message.media:
                            media_type = str(type(message.media).__name__)
                            message_text_hash = hash(f"media_{media_type}")
                        else:
                            message_text_hash = 0
                    
                    message_key = f"{message.chat.id}_{sender.id}_{message_date_str}_{message_text_hash}"
                    
                    # 调试日志：输出生成的 key（仅前100个字符，避免日志过长）
                    logger.debug(f"🔑 [{client_name}] 消息唯一标识: {message_key[:100]}... (消息ID: {message.id})")
                    
                    # 检查是否已处理过
                    if message_key in processed_messages:
                        logger.info(f"🔄 [{client_name}] 消息已由其他客户端处理，跳过重复处理（消息ID: {message.id}, key: {message_key[:50]}...）")
                        return
                    
                    # 标记为已处理（记录当前时间戳）
                    processed_messages[message_key] = datetime.now().timestamp()
                    logger.info(f"📝 [{client_name}] 标记消息为已处理（消息ID: {message.id}, key: {message_key[:50]}...）")
                
                # 获取消息所在的群组ID
                chat_id = message.chat.id
                from_chat_id = message.chat.id
                message_id = message.id
                
                # 获取用户类型信息（用于日志）
                user_type = "机器人" if sender.is_bot else "普通用户"
                
                # 将消息加入队列，而不是直接发送
                # 重要：记录收到消息的客户端索引，因为不同客户端看到的 message_id 可能不同
                # 发送时必须使用收到消息的客户端来复制，因为它能看到正确的 message_id
                task = MessageTask(
                    chat_id=chat_id,
                    from_chat_id=from_chat_id,
                    message_id=message_id,
                    user_type=user_type,
                    received_by_client_index=client_index  # 记录收到消息的客户端
                )
                await message_queue.put(task)
                queue_size = message_queue.qsize()
                logger.info(f"[{client_name}] 消息已加入队列（队列长度: {queue_size}），等待通过客户端模拟操作发送...")
                
            else:
                logger.info(f"❌ [{client_name}] 用户名不匹配，跳过处理")
                
        except Exception as e:
            logger.error(f"❌ [{client_name}] 处理消息时发生错误: {str(e)}", exc_info=True)
    
    return message_handler

# 启动消息发送任务的辅助函数
async def start_sender():
    """启动消息发送任务"""
    await message_sender()

async def main():
    """主函数"""
    try:
        logger.info("正在启动 Telegram 客户端（Pyrogram）...")
        logger.info(f"共配置 {len(accounts)} 个账户，将创建 {len(clients)} 个客户端")
        
        # 为每个客户端注册消息处理器
        for i, client in enumerate(clients):
            create_message_handler(i)
            logger.info(f"已为客户端 {accounts[i]['name']} 注册消息处理器")
        
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
        logger.info(f"目标用户名: {target_bot_username}")
        logger.info(f"分配策略: {distribution_strategy}")
        logger.info("使用客户端模拟操作（copy_message）复制消息")
        logger.info("=" * 60)
        logger.info("📢 程序已开始监听所有群的指定用户消息...")
        logger.info("📢 同一个群的消息将按轮询方式分配给不同客户端发送")
        logger.info("=" * 60)
        
        # 在客户端启动后，启动消息发送任务和清理任务
        sender_task = asyncio.create_task(start_sender())
        cleanup_task = asyncio.create_task(cleanup_processed_messages())
        logger.info("消息队列发送任务已启动，等待消息...")
        logger.info("消息去重清理任务已启动...")
        
        try:
            # 使用 idle() 保持运行（Pyrogram 推荐方式）
            from pyrogram import idle
            await idle()
        except KeyboardInterrupt:
            logger.info("收到中断信号，正在关闭...")
        finally:
            # 取消消息发送任务和清理任务
            sender_task.cancel()
            cleanup_task.cancel()
            try:
                await sender_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"取消发送任务时出错: {str(e)}")
            
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.warning(f"取消清理任务时出错: {str(e)}")
            
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
