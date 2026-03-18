"""WebSocket API 端点"""
import json
import base64
import asyncio
import logging
from typing import Dict, Any, Optional, AsyncGenerator, List
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.services.orchestrator import DigitalHumanOrchestrator
from app.services.evaluation_service import EvaluationService
from app.services.prompts import get_interview_prompt_with_context
from app.services.resume_store import resume_store
from app.services.llm_qwen import QwenLLMService, QwenChatLLMService

router = APIRouter()
logger = logging.getLogger(__name__)

# 全局共享的 THG 服务实例（避免每次连接都重新初始化，耗时4-5秒）
_shared_thg_service: Optional[Any] = None
_thg_service_lock = asyncio.Lock()


async def get_shared_thg_service():
    """
    获取共享的 THG 服务实例（单例模式）
    避免每次WebSocket连接都重新初始化THG服务（加载ONNX模型耗时4-5秒）
    """
    global _shared_thg_service
    
    if _shared_thg_service is None:
        async with _thg_service_lock:
            # 双重检查，避免并发创建
            if _shared_thg_service is None:
                logger.info("[THG] 创建共享的 THG 服务实例（首次初始化，可能需要几秒钟）")
                from app.services.thg_service import RealTHGService
                from app.config import settings
                import os
                
                if settings.thg_data_path and os.path.exists(settings.thg_data_path):
                    try:
                        _shared_thg_service = RealTHGService(
                            data_path=settings.thg_data_path,
                            use_gpu=settings.thg_use_gpu
                        )
                        logger.info("[THG] 共享 THG 服务实例创建完成")
                    except Exception as e:
                        logger.error(f"[THG] Failed to create shared THG service: {e}", exc_info=True)
                        from app.services.thg_service import MockTHGService
                        _shared_thg_service = MockTHGService()
                else:
                    from app.services.thg_service import MockTHGService
                    _shared_thg_service = MockTHGService()
    
    return _shared_thg_service


class InterruptibleTask:
    """可中断的任务封装"""

    def __init__(self):
        self._cancelled = False
        self._cancel_event = asyncio.Event()

    @property
    def is_cancelled(self) -> bool:
        return self._cancelled

    def cancel(self):
        """标记任务为已取消"""
        self._cancelled = True
        self._cancel_event.set()

    def reset(self):
        """重置取消状态"""
        self._cancelled = False
        self._cancel_event.clear()

    async def check_cancelled(self) -> bool:
        """检查是否已取消，用于在处理过程中检查"""
        return self._cancelled


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket 端点
    
    消息协议：
    客户端发送：
    - {"type": "audio_chunk", "data": "base64_encoded_audio"}
    - {"type": "audio_end"}
    - {"type": "resume_context", "resume_id": "resume_id"}
    - {"type": "job_context", "job_title": "岗位名称"}
    
    服务端响应：
    - {"type": "status", "stage": "asr|llm|tts|thg", "message": "..."}
    - {"type": "asr_result", "text": "..."}
    - {"type": "llm_result", "text": "..."}
    - {"type": "tts_audio_chunk", "data": "base64_encoded_audio", "chunk_index": 0, "is_first": true, "is_final": false}  # TTS 流式音频块
    - {"type": "video_chunk", "data": "base64_encoded_video"}
    - {"type": "complete"}
    - {"type": "error", "message": "..."}
    """
    await websocket.accept()
    logger.info("WebSocket connection established")
    
    # 使用共享的THG服务，但每个连接创建独立的orchestrator（用于session管理）
    shared_thg_service = await get_shared_thg_service()
    orchestrator = DigitalHumanOrchestrator(thg_service=shared_thg_service)
    
    # 用于收集音频数据
    audio_chunks: list[bytes] = []
    processing_started = False
    processing_task: Optional[asyncio.Task] = None
    using_tingwu = False  # 标记是否使用听悟（收到asr_result说明使用了听悟）
    interrupt_task = InterruptibleTask()  # 用于打断控制
    is_digital_human_speaking = False  # 数字人是否正在说话
    idle_video_task: Optional[asyncio.Task] = None  # 空闲视频生成任务
    idle_video_cancelled = False  # 空闲视频取消标志
    
    # 面试状态管理
    interview_state: str = "idle"  # "idle" | "in_progress" | "ended"
    conversation_history: List[Dict[str, str]] = []  # 对话历史 [{role: str, content: str}]
    resume_text: Optional[str] = None
    job_description: Optional[str] = None
    context_prompt: Optional[str] = None
    
    # 初始化评价服务，复用orchestrator中的LLM服务
    evaluation_service = EvaluationService(llm_service=orchestrator.llm_service)
    
    # 定义发送消息的辅助函数
    async def send_message(msg: Dict[str, Any]) -> None:
        """发送消息到客户端，忽略连接断开错误"""
        try:
            await websocket.send_json(msg)
        except (WebSocketDisconnect, RuntimeError, ConnectionError):
            # 连接已断开，忽略发送错误
            pass
        except Exception as e:
            logger.warning(f"Failed to send message: {e}")

    def should_inline_prompt() -> bool:
        return not isinstance(orchestrator.llm_service, (QwenLLMService, QwenChatLLMService))

    def build_context_prompt() -> Optional[str]:
        if not resume_text and not job_description:
            return None
        return get_interview_prompt_with_context(
            job_description=job_description,
            candidate_resume=resume_text
        )

    def build_llm_input(user_text: str) -> str:
        if context_prompt and should_inline_prompt():
            return f"{context_prompt}\n\n候选人回答：\n{user_text}"
        return user_text
    
    async def start_idle_video_generation() -> None:
        """启动空闲视频生成（聆听状态）"""
        nonlocal idle_video_task, idle_video_cancelled
        
        # 如果已经有空闲视频任务在运行，不要重复启动
        if idle_video_task and not idle_video_task.done():
            return
        
        # 检查 THG 服务是否支持空闲视频生成
        if not hasattr(shared_thg_service, 'generate_idle_video'):
            logger.info("[Idle] THG 服务不支持空闲视频生成")
            return
        
        idle_video_cancelled = False
        
        async def idle_video_loop():
            nonlocal idle_video_cancelled
            logger.info("[Idle] 开始空闲视频生成（聆听状态）")
            
            try:
                frame_count = 0
                async for video_frame in shared_thg_service.generate_idle_video(
                    cancel_check=lambda: idle_video_cancelled,
                    fps=15
                ):
                    if idle_video_cancelled:
                        break
                    
                    frame_count += 1
                    
                    if isinstance(video_frame, dict):
                        video_chunk = video_frame.get("data", b"")
                        frame_index = video_frame.get("frame_index")
                        timestamp_ms = video_frame.get("timestamp_ms")
                    else:
                        video_chunk = video_frame
                        frame_index = None
                        timestamp_ms = None
                    
                    video_base64 = base64.b64encode(video_chunk).decode('utf-8')
                    
                    message: Dict[str, Any] = {
                        "type": "video_chunk",
                        "data": video_base64,
                        "is_idle": True  # 标记为空闲帧
                    }
                    if frame_index is not None:
                        message["frame_index"] = frame_index
                    if timestamp_ms is not None:
                        message["timestamp_ms"] = timestamp_ms
                    
                    await send_message(message)
                    
                    # 每 50 帧打印一次日志
                    if frame_count % 50 == 0:
                        logger.debug(f"[Idle] 已生成 {frame_count} 个空闲帧")
                        
            except asyncio.CancelledError:
                logger.info("[Idle] 空闲视频生成被取消")
            except Exception as e:
                logger.error(f"[Idle] 空闲视频生成错误: {e}")
            finally:
                logger.info(f"[Idle] 空闲视频生成结束，共 {frame_count} 帧")
        
        idle_video_task = asyncio.create_task(idle_video_loop())
    
    async def stop_idle_video_generation() -> None:
        """停止空闲视频生成"""
        nonlocal idle_video_task, idle_video_cancelled
        
        if idle_video_task and not idle_video_task.done():
            idle_video_cancelled = True
            idle_video_task.cancel()
            try:
                await idle_video_task
            except asyncio.CancelledError:
                pass
            idle_video_task = None
            logger.info("[Idle] 空闲视频生成已停止")
    
    async def stream_processing_pipeline() -> None:
        """
        流式处理流程（不使用听悟时的备用方案）
        当直接发送audio_chunk到主WS时使用，会调用orchestrator的ASR服务
        """
        try:
            # 等待音频收集完成（简单延迟，实际应该等待audio_end）
            await asyncio.sleep(0.5)
            
            # 将所有音频块合并
            audio_data = b''.join(audio_chunks)
            
            if not audio_data:
                logger.warning("No audio data collected for processing")
                return
            
            # 使用 orchestrator 处理音频流（包含ASR步骤）
            await orchestrator.process_audio_stream(audio_data, send_message)
        except asyncio.CancelledError:
            logger.info("Processing pipeline cancelled")
            raise
        except Exception as e:
            logger.error(f"处理流程错误: {e}", exc_info=True)
            await send_message({
                "type": "error",
                "message": f"处理过程中发生错误: {str(e)}"
            })
    
    async def process_from_text(text: str, enable_qa: bool = False) -> None:
        """
        从文本开始处理流程（LLM → TTS → THG）
        用于听悟转写结果或直接文本输入
        
        Args:
            text: 输入文本
            enable_qa: 是否启用LLM实时问答（使用百炼应用）
        """
        # 检查面试状态
        if interview_state == "ended":
            logger.warning("[Interview] 面试已结束，停止处理")
            return
        
        try:
            logger.info(f"开始处理文本: {text[:50]}..., enable_qa={enable_qa}")
            
            # 根据enable_qa切换LLM服务
            if enable_qa:
                # 切换到百炼应用
                if not orchestrator.switch_to_bailian_service(enable=True):
                    logger.warning("[WebSocket] 切换到百炼应用失败，使用默认LLM服务")
            else:
                # 切换回默认服务
                orchestrator.switch_to_bailian_service(enable=False)
            if context_prompt and not should_inline_prompt():
                orchestrator.llm_service.set_system_prompt(context_prompt)
            
            # 1. LLM: 优化文字（或实时问答）
            # LLM 处理期间启动空闲视频生成（思考中状态）
            await start_idle_video_generation()
            
            await send_message({
                "type": "status",
                "stage": "llm",
                "message": "开始文本处理..." if enable_qa else "开始文本优化..."
            })
            llm_input = build_llm_input(text)
            optimized_text = await orchestrator.llm_service.optimize_text(llm_input)
            logger.info(f"LLM 处理完成: {optimized_text[:50]}...")
            
            # 更新百炼应用的session_id
            orchestrator.update_bailian_session()
            
            await send_message({
                "type": "llm_result",
                "text": optimized_text
            })
            
            # 记录LLM输出到对话历史
            if interview_state == "in_progress":
                conversation_history.append({
                    "role": "assistant",
                    "content": optimized_text
                })
                logger.info(f"[Interview] 记录面试官输出，对话历史长度: {len(conversation_history)}")
            
            # LLM 处理完成，停止空闲视频（即将开始说话）
            await stop_idle_video_generation()
            
            # 2. TTS 和 THG 并行处理，确保音视频同步
            await send_message({
                "type": "status",
                "stage": "tts",
                "message": "开始语音合成..."
            })
            logger.info("开始 TTS 合成...")
            
            # 用于同步的变量
            tts_audio_queue = asyncio.Queue()  # 缓存 TTS 音频块（用于发送给前端）
            tts_audio_buffer: List[bytes] = []  # 缓存音频块（用于 THG）
            tts_complete = asyncio.Event()  # TTS 完成标记
            # first_video_frame_received 已移除：音频不再等待 THG 首帧，改为立即发送
            # 前端通过 timestamp_ms 做音视频同步
            
            # 创建共享的音频流：同时提供给 THG 和音频发送
            audio_stream = orchestrator.tts_service.synthesize(optimized_text)
            
            # TTS 收集任务：收集音频并放入缓冲区和队列
            async def tts_collect_task():
                try:
                    chunk_index = 0
                    async for audio_chunk in audio_stream:
                        # 同时放入缓冲区和队列
                        tts_audio_buffer.append(audio_chunk)
                        await tts_audio_queue.put((audio_chunk, chunk_index))
                        chunk_index += 1
                    
                    logger.info(f"TTS 合成完成，共 {len(tts_audio_buffer)} 个音频块")
                    # 标记 TTS 完成
                    await tts_audio_queue.put((None, chunk_index))  # None 表示完成
                    tts_complete.set()
                except Exception as e:
                    logger.error(f"TTS 收集任务错误: {e}", exc_info=True)
                    await tts_audio_queue.put((Exception(f"TTS error: {e}"), -1))
                    tts_complete.set()
            
            # 音频发送任务：TTS 产出即发送，无需等待 THG 第一帧
            async def audio_send_task():
                try:
                    # 检查面试状态
                    if interview_state == "ended":
                        logger.info("[Interview] 面试已结束，停止音频发送")
                        return
                    
                    logger.info("TTS 音频开始流式发送（不等待 THG 首帧）")
                    
                    # 发送缓存的音频块
                    chunk_index = 0
                    while True:
                        try:
                            # 从队列获取音频块（带超时避免无限等待）
                            audio_chunk, idx = await asyncio.wait_for(tts_audio_queue.get(), timeout=1.0)
                            
                            if audio_chunk is None:
                                # TTS 完成标记
                                await send_message({
                                    "type": "tts_audio_chunk",
                                    "data": "",
                                    "chunk_index": idx,
                                    "is_first": False,
                                    "is_final": True
                                })
                                break
                            
                            if isinstance(audio_chunk, Exception):
                                raise audio_chunk
                            
                            # 检查面试状态
                            if interview_state == "ended":
                                logger.info("[Interview] 面试已结束，停止音频发送")
                                break
                            
                            # 发送音频块
                            chunk_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                            await send_message({
                                "type": "tts_audio_chunk",
                                "data": chunk_base64,
                                "chunk_index": chunk_index,
                                "is_first": chunk_index == 0,
                                "is_final": False
                            })
                            chunk_index += 1
                            
                        except asyncio.TimeoutError:
                            # 检查 TTS 是否完成
                            if tts_complete.is_set():
                                break
                            continue
                            
                except Exception as e:
                    logger.error(f"音频发送任务错误: {e}", exc_info=True)
            
            # THG 任务：生成视频
            async def thg_task():
                # 检查面试状态
                if interview_state == "ended":
                    logger.info("[Interview] 面试已结束，跳过视频生成")
                    return
                
                try:
                    await send_message({
                        "type": "status",
                        "stage": "thg",
                        "message": "开始生成数字人视频..."
                    })
                    logger.info("开始 THG 视频生成...")
                    
                    # 创建音频流生成器用于 THG（从缓冲区读取）
                    async def audio_stream_for_thg() -> AsyncGenerator[bytes, None]:
                        buffer_index = 0
                        while True:
                            # 如果缓冲区有数据，yield 它
                            if buffer_index < len(tts_audio_buffer):
                                yield tts_audio_buffer[buffer_index]
                                buffer_index += 1
                            elif tts_complete.is_set() and buffer_index >= len(tts_audio_buffer):
                                # TTS 完成且所有数据已发送
                                break
                            else:
                                # 等待新数据
                                await asyncio.sleep(0.01)
                    
                    video_stream = orchestrator.thg_service.generate_video(audio_stream_for_thg())
                    
                    chunk_count = 0
                    async for video_frame in video_stream:
                        # 检查面试状态
                        if interview_state == "ended":
                            logger.info("[Interview] 面试已结束，停止视频生成")
                            break
                        
                        chunk_count += 1
                        
                        # 每 5 个块更新一次进度
                        if chunk_count % 5 == 0:
                            logger.debug(f"已生成 {chunk_count} 个视频帧")
                            await send_message({
                                "type": "status",
                                "stage": "thg",
                                "message": f"正在生成视频帧... ({chunk_count} 帧)"
                            })
                        
                        if isinstance(video_frame, dict):
                            video_chunk = video_frame.get("data", b"")
                            frame_index = video_frame.get("frame_index")
                            timestamp_ms = video_frame.get("timestamp_ms")
                        else:
                            video_chunk = video_frame
                            frame_index = None
                            timestamp_ms = None
                        
                        # 将视频块编码为 base64
                        video_base64 = base64.b64encode(video_chunk).decode('utf-8')
                        
                        # 发送视频帧
                        message: Dict[str, Any] = {
                            "type": "video_chunk",
                            "data": video_base64
                        }
                        if frame_index is not None:
                            message["frame_index"] = frame_index
                        if timestamp_ms is not None:
                            message["timestamp_ms"] = timestamp_ms
                        await send_message(message)
                    
                    logger.info(f"视频生成完成，共 {chunk_count} 帧")
                    await send_message({
                        "type": "status",
                        "stage": "thg",
                        "message": "视频生成完成"
                    })
                except Exception as e:
                    logger.error(f"THG 任务错误: {e}", exc_info=True)
                    raise
            
            # 并行执行任务
            tts_collect_task_obj = asyncio.create_task(tts_collect_task())
            audio_send_task_obj = asyncio.create_task(audio_send_task())
            thg_task_obj = asyncio.create_task(thg_task())
            
            # 等待所有任务完成
            await asyncio.gather(tts_collect_task_obj, audio_send_task_obj, thg_task_obj, return_exceptions=True)
            
            await send_message({
                "type": "complete"
            })
            
            # 说话完成后，启动空闲视频生成（聆听状态）
            await start_idle_video_generation()
        except asyncio.CancelledError:
            logger.info("Text processing cancelled")
            raise
        except Exception as e:
            logger.error(f"处理流程错误: {e}", exc_info=True)
            await send_message({
                "type": "error",
                "message": f"处理过程中发生错误: {str(e)}"
            })
    
    try:
        while True:
            # 接收消息
            data = await websocket.receive_text()
            try:
                message = json.loads(data)
            except json.JSONDecodeError as e:
                print(f"[WebSocket] JSON 解析失败: {e}, 原始数据: {data[:100]}")
                await send_message({
                    "type": "error",
                    "message": f"JSON 解析失败: {str(e)}"
                })
                continue
            
            message_type = message.get("type")
            print(f"[WebSocket] 收到消息类型: {message_type}")
            
            if message_type == "resume_context":
                resume_id = (message.get("resume_id") or "").strip()
                if not resume_id:
                    resume_text = None
                    context_prompt = build_context_prompt()
                    if not context_prompt:
                        orchestrator.llm_service.set_system_prompt(None)
                    await send_message({
                        "type": "resume_context",
                        "message": "待读取您的简历，请上传"
                    })
                    continue

                resume_text = await resume_store.get(resume_id)
                if not resume_text:
                    await send_message({
                        "type": "error",
                        "message": "简历不存在或已过期"
                    })
                    continue

                context_prompt = build_context_prompt()
                if context_prompt and not should_inline_prompt():
                    orchestrator.llm_service.set_system_prompt(context_prompt)
                await send_message({
                    "type": "resume_context",
                    "message": "已读取您的简历",
                    "text_length": len(resume_text)
                })
                continue

            if message_type == "job_context":
                job_title = (message.get("job_title") or "").strip()
                if not job_title:
                    job_description = None
                    context_prompt = build_context_prompt()
                    if context_prompt and not should_inline_prompt():
                        orchestrator.llm_service.set_system_prompt(context_prompt)
                    await send_message({
                        "type": "job_context",
                        "message": "岗位已清除"
                    })
                    continue

                jd_request = (
                    "请根据以下岗位名称生成简洁的岗位JD，面向校园学生体验面试用。\n"
                    "要求：不需要过度精细，突出职责、技能点与项目方向即可，100-200字。\n"
                    f"岗位名称：{job_title}"
                )
                jd_text = await orchestrator.llm_service.optimize_text(jd_request)
                job_description = jd_text.strip()
                context_prompt = build_context_prompt()
                if context_prompt and not should_inline_prompt():
                    orchestrator.llm_service.set_system_prompt(context_prompt)
                await send_message({
                    "type": "job_context",
                    "message": "岗位JD已生成",
                    "text_length": len(job_description)
                })
                continue

            if message_type == "audio_chunk":
                # 如果面试已结束，重置状态开始新面试
                if interview_state == "ended":
                    logger.info("[Interview] 检测到新音频输入，重置面试状态，开始新一轮面试")
                    interview_state = "idle"
                    conversation_history.clear()
                
                # 收集音频块（不使用听悟时的备用方案）
                audio_base64 = message.get("data", "")
                try:
                    audio_chunk = base64.b64decode(audio_base64)
                    audio_chunks.append(audio_chunk)
                    
                    # 如果面试状态为idle，设置为in_progress
                    if interview_state == "idle":
                        interview_state = "in_progress"
                        logger.info("[Interview] 面试开始")
                    
                    # 如果未使用听悟，收到第一个音频块时启动处理流程
                    # 如果使用听悟，前端会发送asr_result，不需要这里处理
                    if not using_tingwu and not processing_started and len(audio_chunks) == 1:
                        processing_started = True
                        logger.info("启动备用处理流程（不使用听悟）")
                        # 在后台启动处理流程（ASR → LLM → TTS → THG）
                        processing_task = asyncio.create_task(stream_processing_pipeline())
                        
                except Exception as e:
                    logger.error(f"音频数据解码失败: {e}", exc_info=True)
                    await send_message({
                        "type": "error",
                        "message": f"音频数据解码失败: {str(e)}"
                    })
            
            elif message_type == "asr_result":
                # 如果面试已结束，重置状态开始新面试
                if interview_state == "ended":
                    logger.info("[Interview] 检测到新输入，重置面试状态，开始新一轮面试")
                    interview_state = "idle"
                    conversation_history.clear()
                
                # 收到 ASR 结果（来自听悟的最终句子），触发后续流程（LLM → TTS → THG）
                asr_text = message.get("text", "")
                enable_qa = message.get("enable_qa", False)  # 获取前端传来的开关状态
                logger.info(f"收到 asr_result: {asr_text[:50]}..., enable_qa={enable_qa}")
                
                if not asr_text or not asr_text.strip():
                    logger.warning("收到空的ASR结果，跳过处理")
                    continue
                
                # 记录用户输入到对话历史
                if interview_state == "idle":
                    interview_state = "in_progress"
                    logger.info("[Interview] 面试开始")
                
                conversation_history.append({
                    "role": "user",
                    "content": asr_text.strip()
                })
                logger.info(f"[Interview] 记录用户输入，对话历史长度: {len(conversation_history)}")
                
                # 停止空闲视频生成（用户开始新的交互）
                await stop_idle_video_generation()
                
                # 标记使用听悟，取消备用处理流程（如果有）
                using_tingwu = True
                if processing_task and not processing_task.done():
                    logger.info("取消备用处理流程，使用听悟结果")
                    processing_task.cancel()
                    try:
                        await processing_task
                    except asyncio.CancelledError:
                        pass
                
                # 启动新的处理任务（LLM → TTS → THG）
                processing_task = asyncio.create_task(process_from_text(asr_text.strip(), enable_qa=enable_qa))
            
            elif message_type == "text_input":
                # 如果面试已结束，重置状态开始新面试
                if interview_state == "ended":
                    logger.info("[Interview] 检测到新输入，重置面试状态，开始新一轮面试")
                    interview_state = "idle"
                    conversation_history.clear()
                
                # 收到文本输入（用户直接输入的文本），触发后续流程（LLM → TTS → THG）
                input_text = message.get("text", "")
                enable_qa = message.get("enable_qa", False)  # 获取前端传来的开关状态
                logger.info(f"收到 text_input 消息: {input_text[:50]}..., enable_qa={enable_qa}")
                
                if not input_text or not input_text.strip():
                    logger.warning("文本内容为空")
                    await send_message({
                        "type": "error",
                        "message": "文本内容为空"
                    })
                    continue
                
                # 记录用户输入到对话历史
                if interview_state == "idle":
                    interview_state = "in_progress"
                    logger.info("[Interview] 面试开始")
                
                conversation_history.append({
                    "role": "user",
                    "content": input_text.strip()
                })
                logger.info(f"[Interview] 记录用户输入，对话历史长度: {len(conversation_history)}")
                
                # 停止空闲视频生成（用户开始新的交互）
                await stop_idle_video_generation()
                
                # 取消之前的任务（如果有）
                if processing_task and not processing_task.done():
                    logger.info("取消之前的处理任务")
                    processing_task.cancel()
                    try:
                        await processing_task
                    except asyncio.CancelledError:
                        pass
                
                # 启动新的处理任务（复用 process_from_text 函数）
                processing_task = asyncio.create_task(process_from_text(input_text.strip(), enable_qa=enable_qa))
            
            elif message_type == "audio_end":
                # 音频传输完成（不使用听悟时的结束信号）
                if not audio_chunks:
                    logger.warning("audio_end 但未收到音频数据")
                    await send_message({
                        "type": "error",
                        "message": "未收到音频数据"
                    })
                    continue
                
                # 等待处理流程完成（如果还在运行）
                if processing_task and not processing_task.done():
                    try:
                        await asyncio.wait_for(processing_task, timeout=30.0)
                    except asyncio.TimeoutError:
                        logger.warning("处理流程超时")
                    except asyncio.CancelledError:
                        logger.info("处理流程被取消")
                
                # 清理
                audio_chunks.clear()
                processing_started = False
                processing_task = None
                using_tingwu = False
            
            elif message_type == "interrupt":
                # 处理打断请求
                logger.info("收到打断请求")

                # 设置打断标志
                interrupt_task.cancel()
                is_digital_human_speaking = False

                # 取消当前处理任务
                if processing_task and not processing_task.done():
                    logger.info("取消当前处理任务")
                    processing_task.cancel()
                    try:
                        await processing_task
                    except asyncio.CancelledError:
                        pass

                # 重置状态
                audio_chunks.clear()
                processing_started = False
                processing_task = None

                # 通知前端打断成功
                await send_message({
                    "type": "interrupted",
                    "message": "已打断数字人说话"
                })

                # 重置打断标志，准备下一次交互
                interrupt_task.reset()
                
                # 打断后启动空闲视频生成（聆听状态）
                await start_idle_video_generation()
            
            elif message_type == "end_interview":
                # 处理结束面试请求
                logger.info("[Interview] 收到结束面试请求")
                
                # 检查面试状态
                if interview_state == "ended":
                    logger.warning("[Interview] 面试已经结束")
                    await send_message({
                        "type": "error",
                        "message": "面试已经结束"
                    })
                    continue
                
                # 设置面试状态为ended
                interview_state = "ended"
                logger.info("[Interview] 面试状态设置为ended")
                
                # 取消所有处理任务
                if processing_task and not processing_task.done():
                    logger.info("[Interview] 取消当前处理任务")
                    processing_task.cancel()
                    try:
                        await processing_task
                    except asyncio.CancelledError:
                        pass
                
                # 停止空闲视频生成
                await stop_idle_video_generation()
                
                # 停止音频播放（通过发送停止消息）
                interrupt_task.cancel()
                is_digital_human_speaking = False
                
                # 通知前端面试已结束
                await send_message({
                    "type": "interview_ended",
                    "message": "面试已结束，正在生成评价..."
                })
                
                # 生成评价
                try:
                    logger.info(f"[Interview] 开始生成评价，对话历史长度: {len(conversation_history)}")
                    
                    # 使用orchestrator当前的LLM服务（可能已经被切换），而不是evaluation_service初始化时的
                    current_llm_service = orchestrator.llm_service
                    llm_service_name = type(current_llm_service).__name__
                    logger.info(f"[Interview] 使用LLM服务: {llm_service_name}")
                    
                    # 检查是否是Mock服务
                    if "Mock" in llm_service_name:
                        logger.warning(f"[Interview] 当前使用的是MockLLMService，评价结果可能不准确")
                        logger.info(f"[Interview] 请检查配置: llm_mode={getattr(settings, 'llm_mode', 'MOCK')}, dashscope_api_key={'已配置' if settings.dashscope_api_key else '未配置'}")
                    
                    # 临时更新evaluation_service的LLM服务为当前使用的服务
                    evaluation_service.llm_service = current_llm_service
                    logger.info(f"[Evaluation] 已更新LLM服务为: {llm_service_name}")
                    
                    if not conversation_history:
                        logger.warning("[Interview] 对话历史为空，无法生成评价")
                        await send_message({
                            "type": "error",
                            "message": "对话历史为空，无法生成评价"
                        })
                        continue
                    
                    evaluation_result = await evaluation_service.evaluate_interview(
                        conversation_history=conversation_history
                    )
                    
                    logger.info("[Interview] 评价生成完成")
                    logger.debug(f"[Interview] 评价结果摘要: {evaluation_result.get('summary', '')[:100]}")
                    
                    # 发送评价结果
                    await send_message({
                        "type": "evaluation_result",
                        "data": evaluation_result
                    })
                    
                except Exception as e:
                    logger.error(f"[Interview] 评价生成失败: {e}", exc_info=True)
                    import traceback
                    logger.error(f"[Interview] 异常堆栈: {traceback.format_exc()}")
                    await send_message({
                        "type": "error",
                        "message": f"评价生成失败: {str(e)}"
                    })

            else:
                logger.warning(f"未知的消息类型: {message_type}")
                await send_message({
                    "type": "error",
                    "message": f"未知的消息类型: {message_type}"
                })
    
    except WebSocketDisconnect:
        # 客户端断开连接
        logger.info("WebSocket connection closed by client")
        # 清理资源
        await stop_idle_video_generation()
        if processing_task and not processing_task.done():
            processing_task.cancel()
            try:
                await processing_task
            except asyncio.CancelledError:
                pass
    except Exception as e:
        # 其他错误
        logger.error(f"WebSocket error: {e}", exc_info=True)
        try:
            await send_message({
                "type": "error",
                "message": f"服务器错误: {str(e)}"
            })
        except Exception:
            # 如果连接已断开，忽略发送错误
            pass
