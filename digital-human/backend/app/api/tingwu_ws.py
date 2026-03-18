"""听悟实时转写 WebSocket 端点

WebSocket Path: /api/tingwu/ws

前端协议约定：
----------------
客户端 → 服务端：
  - {"type": "audio_chunk", "data": "base64_encoded_audio"}
  - {"type": "audio_end"}

服务端 → 客户端：
  - {"type": "status", "stage": "tingwu", "message": "..."}
  - {"type": "tingwu_result", "text": "...", "raw": {...}}
  - {"type": "complete"}
  - {"type": "error", "message": "..."}
"""

from __future__ import annotations

import asyncio
import base64
import contextlib
import json
import logging
from typing import AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.services.tingwu_client import TingwuRealtimeClient

router = APIRouter()
logger = logging.getLogger(__name__)


async def _audio_queue_iterator(
    audio_queue: asyncio.Queue[bytes | None],
) -> AsyncIterator[bytes]:
    """从 asyncio.Queue 异步迭代音频块
    
    当收到 None 时，表示音频流结束。
    """
    while True:
        chunk = await audio_queue.get()
        if chunk is None:
            # 收到结束标记，停止迭代
            break
        yield chunk
        audio_queue.task_done()


@router.websocket("/tingwu/ws")
async def tingwu_websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    logger.info("听悟 WebSocket 连接已建立")

    client = TingwuRealtimeClient()
    logger.info(f"听悟客户端初始化: 使用真实SDK={client._client is not None}, 配置有效={client.config.is_valid}")
    audio_queue: asyncio.Queue[bytes | None] = asyncio.Queue()
    transcription_task: asyncio.Task | None = None
    is_transcribing = False

    async def handle_transcription() -> None:
        """处理转写任务"""
        nonlocal is_transcribing
        try:
            is_transcribing = True
            # 通知前端：开始调用听悟
            await websocket.send_json(
                {
                    "type": "status",
                    "stage": "tingwu",
                    "message": "开始调用听悟实时转写服务...",
                }
            )

            # 构造音频流并调用听悟客户端
            audio_iter = _audio_queue_iterator(audio_queue)

            async for result in client.stream_transcribe(audio_iter):
                result_text = result.get("text", "")
                result_raw = result.get("raw", {})
                header = result_raw.get("header", {})
                message_name = header.get("name", "")
                
                # 判断消息类型：中间结果还是完整句子
                is_final = message_name == "SentenceEnd"
                
                logger.info(f"收到听悟转写结果: type={message_name}, is_final={is_final}, text={result_text[:100] if result_text else 'empty'}...")
                
                # 发送听悟转写结果
                await websocket.send_json(
                    {
                        "type": "tingwu_result",
                        "text": result_text,
                        "is_final": is_final,  # 标识是否为完整句子
                        "message_name": message_name,  # 消息类型名称
                        "raw": result_raw,
                    }
                )
                
                # 如果有文本内容，同时作为ASR结果发送到主WebSocket（如果需要）
                # 注意：这里只发送给听悟WebSocket，前端可以通过tingwu_result来处理
                # 如果需要同时更新主流程的ASR结果，需要额外的逻辑

            await websocket.send_json({"type": "complete"})
            logger.info("听悟转写任务完成")
        except Exception as e:  # noqa: BLE001
            logger.error(f"调用听悟服务失败: {e}", exc_info=True)
            try:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"调用听悟服务失败: {e}",
                    }
                )
            except Exception:
                # 连接已断开，忽略
                pass
        finally:
            is_transcribing = False

    try:
        while True:
            data = await websocket.receive_text()
            message = json.loads(data)

            msg_type = message.get("type")

            if msg_type == "audio_chunk":
                audio_base64 = message.get("data") or ""
                try:
                    audio_chunk = base64.b64decode(audio_base64)
                    # 将音频块放入队列
                    await audio_queue.put(audio_chunk)

                    # 如果还没有开始转写，启动转写任务
                    if not is_transcribing and transcription_task is None:
                        transcription_task = asyncio.create_task(handle_transcription())
                        logger.info("已启动听悟转写任务")
                except Exception as e:  # noqa: BLE001
                    logger.error(f"音频数据解码失败: {e}", exc_info=True)
                    await websocket.send_json(
                        {
                            "type": "error",
                            "message": f"音频数据解码失败: {e}",
                        }
                    )

            elif msg_type == "audio_end":
                # 发送结束标记到队列
                await audio_queue.put(None)
                
                # 等待转写任务完成
                if transcription_task is not None:
                    try:
                        await transcription_task
                    except Exception as e:  # noqa: BLE001
                        logger.error(f"转写任务执行失败: {e}", exc_info=True)
                    finally:
                        transcription_task = None

            else:
                await websocket.send_json(
                    {
                        "type": "error",
                        "message": f"未知的消息类型: {msg_type}",
                    }
                )

    except WebSocketDisconnect:
        # 客户端断开连接，清理资源
        logger.info("客户端断开连接")
        if transcription_task is not None and not transcription_task.done():
            transcription_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await transcription_task
        return
    except Exception as e:  # noqa: BLE001
        logger.error(f"服务器错误: {e}", exc_info=True)
        try:
            await websocket.send_json(
                {
                    "type": "error",
                    "message": f"服务器错误: {e}",
                }
            )
        except Exception:
            # 连接已断开，忽略
            pass
        finally:
            if transcription_task is not None and not transcription_task.done():
                transcription_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await transcription_task


