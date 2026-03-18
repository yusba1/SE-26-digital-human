"""流程编排器"""
import asyncio
import base64
import logging
import os
from typing import AsyncGenerator, Callable, Awaitable, Optional, List
from app.services.asr_service import ASRService, MockASRService
from app.services.llm_service import LLMService, MockLLMService

# 尝试导入通义千问 LLM 服务
try:
    from app.services.llm_qwen import QwenLLMService, DASHSCOPE_AVAILABLE as QWEN_LLM_AVAILABLE
except ImportError:
    QwenLLMService = None
    QWEN_LLM_AVAILABLE = False

# 尝试导入百炼应用 LLM 服务
try:
    from app.services.llm_bailian import BailianLLMService, DASHSCOPE_AVAILABLE
    BAILIAN_LLM_AVAILABLE = DASHSCOPE_AVAILABLE
except ImportError:
    BailianLLMService = None
    BAILIAN_LLM_AVAILABLE = False
from app.services.tts_service import (
    TTSService, MockTTSService, EdgeTTSService, AliyunTTSService, MacOSTTSService, DashScopeTTSService,
    EDGE_TTS_AVAILABLE, ALIYUN_TTS_AVAILABLE, MACOS_TTS_AVAILABLE, DASHSCOPE_TTS_AVAILABLE
)
from app.services.thg_service import THGService, MockTHGService, RealTHGService
from app.config import settings

logger = logging.getLogger(__name__)

# Try to import TingwuASRService
try:
    from app.services.asr_tingwu import TingwuASRService, TingwuConfig
    TINGWU_ASR_AVAILABLE = True
except ImportError:
    TingwuASRService = None
    TingwuConfig = None
    TINGWU_ASR_AVAILABLE = False


class DigitalHumanOrchestrator:
    """数字人流程编排器"""
    
    def __init__(
        self,
        asr_service: Optional[ASRService] = None,
        llm_service: Optional[LLMService] = None,
        tts_service: Optional[TTSService] = None,
        thg_service: Optional[THGService] = None
    ):
        # 百炼应用session管理（每个orchestrator实例维护独立的session）
        self.bailian_session_id: Optional[str] = None
        """
        初始化编排器
        
        Args:
            asr_service: ASR 服务实例，如果为 None 则根据配置自动选择
            llm_service: LLM 服务实例，默认使用 Mock
            tts_service: TTS 服务实例，如果为 None 则根据配置自动选择
            thg_service: THG 服务实例，如果为 None 且配置了 thg_data_path，则使用 RealTHGService
        """
        # ASR service priority: provided > Tingwu (if configured) > Mock
        if asr_service is not None:
            self.asr_service = asr_service
            logger.info(f"[ASR] Using provided ASR service: {type(self.asr_service).__name__}")
        else:
            self._init_asr_service()

        # LLM service priority: provided > configured > Mock
        if llm_service is not None:
            self.llm_service = llm_service
            logger.info(f"[LLM] Using provided LLM service: {type(self.llm_service).__name__}")
        else:
            self._init_llm_service()
        
        # TTS service priority: provided > TTS_MODE=CLOUD (DashScope only) > TTS_MODE=LOCAL (AliyunTTS/EdgeTTS/macOS) > Mock
        logger.info(f"[TTS] 初始化 TTS 服务，配置: tts_mode={settings.tts_mode}, dashscope_api_key={'已配置' if settings.dashscope_api_key else '未配置'}")
        
        if tts_service is not None:
            self.tts_service = tts_service
            logger.info(f"[TTS] Using provided tts_service: {type(self.tts_service).__name__}")
        elif settings.tts_mode.upper() == "CLOUD":
            logger.info(f"[TTS] TTS_MODE=CLOUD，检查 DashScope 配置...")
            if settings.dashscope_api_key:
                logger.info(f"[TTS] DashScope API Key 已配置，尝试初始化 DashScopeTTSService...")
                try:
                    self.tts_service = DashScopeTTSService(
                        api_key=settings.dashscope_api_key,
                        model=settings.dashscope_tts_model,
                        voice=settings.dashscope_tts_voice,
                        sample_rate=settings.dashscope_tts_sample_rate,
                        format=settings.dashscope_tts_format,
                    )
                    logger.info(f"[TTS] 成功使用 DashScopeTTSService with model: {settings.dashscope_tts_model}, voice: {settings.dashscope_tts_voice}")
                except Exception as e:
                    logger.error(f"[TTS] Failed to initialize DashScopeTTSService: {e}", exc_info=True)
                    # Use MockTTSService instead of falling back to local TTS
                    logger.warning(f"[TTS] DashScopeTTSService 初始化失败，使用 MockTTSService")
                    self.tts_service = MockTTSService()
            else:
                logger.warning(f"[TTS] TTS_MODE=CLOUD 但 dashscope_api_key 未配置，使用 MockTTSService")
                self.tts_service = MockTTSService()
        else:
            # TTS_MODE=LOCAL 也被禁用，只使用 DashScope 或 Mock
            logger.warning(f"[TTS] TTS_MODE={settings.tts_mode}，但本地 TTS 已禁用，使用 MockTTSService")
            logger.info("[TTS] 如需使用 TTS，请设置 TTS_MODE=CLOUD 并配置 dashscope_api_key")
            self.tts_service = MockTTSService()
        
        # 如果提供了 thg_service，直接使用
        # 否则，如果配置了 thg_data_path，使用 RealTHGService
        # 最后，使用 MockTHGService
        if thg_service is not None:
            self.thg_service = thg_service
            logger.info(f"[THG] Using provided thg_service: {type(self.thg_service).__name__}")
        elif settings.thg_data_path and os.path.exists(settings.thg_data_path):
            try:
                logger.info(f"[THG] Initializing RealTHGService with data_path: {settings.thg_data_path}, use_gpu: {settings.thg_use_gpu}")
                self.thg_service = RealTHGService(
                    data_path=settings.thg_data_path,
                    use_gpu=settings.thg_use_gpu
                )
                logger.info(f"[THG] RealTHGService initialized successfully")
            except Exception as e:
                logger.error(f"[THG] Failed to initialize RealTHGService: {e}, falling back to MockTHGService", exc_info=True)
                self.thg_service = MockTHGService()
        else:
            logger.warning(f"[THG] Using MockTHGService (thg_data_path: {settings.thg_data_path}, exists: {os.path.exists(settings.thg_data_path) if settings.thg_data_path else False})")
            self.thg_service = MockTHGService()
    
    def _init_llm_service(self) -> None:
        """Initialize LLM service based on configuration"""
        llm_mode = settings.llm_mode.upper() if hasattr(settings, 'llm_mode') else "MOCK"
        logger.info(f"[LLM] 初始化 LLM 服务，LLM_MODE={llm_mode}, "
                     f"QWEN_AVAILABLE={QWEN_LLM_AVAILABLE}, "
                     f"API_KEY={'已配置' if settings.dashscope_api_key else '未配置'}")

        if llm_mode == "QWEN":
            if not QWEN_LLM_AVAILABLE:
                logger.warning("[LLM] LLM_MODE=QWEN 但 dashscope 未安装，请执行: pip install dashscope")
            elif not settings.dashscope_api_key:
                logger.warning("[LLM] LLM_MODE=QWEN 但 DASHSCOPE_API_KEY 未配置")
            else:
                try:
                    self.llm_service = QwenLLMService(
                        api_key=settings.dashscope_api_key,
                        model=getattr(settings, 'llm_model', 'qwen-turbo'),
                        system_prompt=getattr(settings, 'llm_system_prompt', None),
                    )
                    logger.info(f"[LLM] 成功使用 QwenLLMService, model={settings.llm_model}")
                    return
                except Exception as e:
                    logger.error(f"[LLM] QwenLLMService 初始化失败: {e}", exc_info=True)

        # Fallback to Mock
        delay = getattr(settings, 'llm_mock_delay', 0.0)
        self.llm_service = MockLLMService(delay=delay)
        if llm_mode != "MOCK":
            logger.warning(f"[LLM] 回退到 MockLLMService（LLM_MODE={llm_mode} 未能成功初始化）")
        else:
            logger.info(f"[LLM] Using MockLLMService with delay: {delay}s")
    
    def switch_to_bailian_service(self, enable: bool = True) -> bool:
        """
        切换到百炼应用服务
        
        Args:
            enable: True 切换到百炼应用，False 切换回默认服务
        
        Returns:
            True 如果切换成功，False 如果切换失败
        """
        if enable:
            # 切换到百炼应用
            if not BAILIAN_LLM_AVAILABLE:
                logger.warning("[LLM] BailianLLMService not available (dashscope not installed)")
                return False
            
            if not settings.dashscope_api_key:
                logger.warning("[LLM] dashscope_api_key not configured")
                return False
            
            app_id = getattr(settings, 'bailian_app_id', None)
            if not app_id:
                logger.warning("[LLM] bailian_app_id not configured, using default")
                app_id = "52ef7010e1ca4cf494ada4d65c9bce59"  # 使用默认应用ID
            logger.info(f"[LLM] Using Bailian app_id: {app_id}")
            
            try:
                self.llm_service = BailianLLMService(
                    api_key=settings.dashscope_api_key,
                    app_id=app_id,
                    session_id=self.bailian_session_id,  # 使用已有的session_id
                )
                logger.info(f"[LLM] Switched to BailianLLMService with app_id: {app_id}")
                return True
            except Exception as e:
                logger.error(f"[LLM] Failed to switch to BailianLLMService: {e}", exc_info=True)
                return False
        else:
            # 切换回默认服务
            self._init_llm_service()
            logger.info("[LLM] Switched back to default LLM service")
            return True
    
    def update_bailian_session(self) -> None:
        """更新百炼应用的session_id（从当前LLM服务中获取）"""
        if isinstance(self.llm_service, BailianLLMService):
            new_session_id = self.llm_service.get_session_id()
            if new_session_id:
                self.bailian_session_id = new_session_id
                logger.debug(f"[LLM] Bailian session updated: {self.bailian_session_id}")
    
    def clear_bailian_session(self) -> None:
        """清空百炼应用的session，开始新的对话"""
        self.bailian_session_id = None
        if isinstance(self.llm_service, BailianLLMService):
            self.llm_service.clear_session()
        logger.info("[LLM] Bailian session cleared")

    def _init_asr_service(self) -> None:
        """Initialize ASR service with fallback chain: Tingwu > Mock"""
        if TINGWU_ASR_AVAILABLE:
            try:
                config = TingwuConfig()
                if config.is_valid:
                    self.asr_service = TingwuASRService(config)
                    logger.info("[ASR] Using TingwuASRService (real SDK)")
                    return
                else:
                    logger.warning("[ASR] Tingwu config is not valid, falling back to MockASRService")
            except Exception as e:
                logger.error(f"[ASR] Failed to initialize TingwuASRService: {e}, falling back to MockASRService", exc_info=True)
        
        # Fallback to Mock
        logger.info("[ASR] Using MockASRService")
        self.asr_service = MockASRService()
    
    def _init_local_tts_service(self) -> None:
        """
        Initialize local TTS service with fallback chain: AliyunTTS > EdgeTTS > macOS say > Mock
        
        NOTE: This method is currently DISABLED. All TTS modes now use DashScope (CLOUD) or Mock only.
        Local TTS services (AliyunTTS, EdgeTTS, MacOSTTS) are no longer used.
        """
        if settings.aliyun_tts_appkey and settings.aliyun_tts_token:
            # Use Aliyun TTS if appkey and token are configured
            try:
                self.tts_service = AliyunTTSService(
                    appkey=settings.aliyun_tts_appkey,
                    token=settings.aliyun_tts_token,
                    voice=settings.aliyun_tts_voice,
                    format=settings.aliyun_tts_format,
                    sample_rate=settings.aliyun_tts_sample_rate,
                )
                logger.info(f"[TTS] Using AliyunTTSService with voice: {settings.aliyun_tts_voice}")
                return
            except Exception as e:
                logger.error(f"[TTS] Failed to initialize AliyunTTSService: {e}", exc_info=True)
        
        # Fallback to EdgeTTS
        if EDGE_TTS_AVAILABLE:
            try:
                self.tts_service = EdgeTTSService(voice="zh-CN-YunxiNeural")
                logger.info("[TTS] Using EdgeTTSService with zh-CN-YunxiNeural voice")
                return
            except Exception as e:
                logger.error(f"[TTS] Failed to initialize EdgeTTSService: {e}", exc_info=True)
        
        # Fallback to macOS say
        if MACOS_TTS_AVAILABLE:
            try:
                self.tts_service = MacOSTTSService()
                logger.info("[TTS] Using MacOSTTSService (say)")
                return
            except Exception as e:
                logger.error(f"[TTS] Failed to initialize MacOSTTSService: {e}, using MockTTSService", exc_info=True)
        
        # Final fallback to Mock
        logger.warning(f"[TTS] EDGE_TTS_AVAILABLE={EDGE_TTS_AVAILABLE}, no TTS service available, using MockTTSService")
        logger.info("[TTS] Note: MockTTSService generates synthetic audio, not real speech")
        self.tts_service = MockTTSService()
    
    async def process_audio_stream(
        self,
        audio_data: bytes,
        send_message: Callable[[dict], Awaitable[None]]
    ) -> None:
        """
        处理音频流，执行完整的数字人流程（ASR → LLM → TTS → THG）
        
        Args:
            audio_data: 完整的音频数据
            send_message: 发送消息的回调函数，用于通过 WebSocket 发送状态更新
            
        Raises:
            Exception: 处理过程中发生的任何错误
        """
        try:
            # 1. ASR: 语音识别为文字
            await send_message({
                "type": "status",
                "stage": "asr",
                "message": "开始语音识别..."
            })
            recognized_text = await self.asr_service.recognize(audio_data)
            
            await send_message({
                "type": "asr_result",
                "text": recognized_text
            })
            
            # 2. LLM: 优化文字
            await send_message({
                "type": "status",
                "stage": "llm",
                "message": "开始文本优化..."
            })
            optimized_text = await self.llm_service.optimize_text(recognized_text)
            
            await send_message({
                "type": "llm_result",
                "text": optimized_text
            })
            
            # 3. TTS 和 THG 并行处理，确保音视频同步
            await send_message({
                "type": "status",
                "stage": "tts",
                "message": "开始语音合成..."
            })
            
            # 用于同步的变量
            tts_audio_queue = asyncio.Queue()  # 缓存 TTS 音频块（用于发送给前端）
            tts_audio_buffer: List[bytes] = []  # 缓存音频块（用于 THG）
            tts_complete = asyncio.Event()  # TTS 完成标记
            first_video_frame_received = asyncio.Event()  # THG 第一帧标记
            
            # 创建共享的音频流
            audio_stream = self.tts_service.synthesize(optimized_text)
            
            # TTS 收集任务：收集音频并放入缓冲区和队列
            async def tts_collect_task():
                try:
                    chunk_index = 0
                    async for audio_chunk in audio_stream:
                        # 同时放入缓冲区和队列
                        tts_audio_buffer.append(audio_chunk)
                        await tts_audio_queue.put((audio_chunk, chunk_index))
                        chunk_index += 1
                    
                    logger.info(f"[Orchestrator] TTS 合成完成，共 {len(tts_audio_buffer)} 个音频块")
                    # 标记 TTS 完成
                    await tts_audio_queue.put((None, chunk_index))
                    tts_complete.set()
                except Exception as e:
                    logger.error(f"[Orchestrator] TTS 收集任务错误: {e}", exc_info=True)
                    await tts_audio_queue.put((Exception(f"TTS error: {e}"), -1))
                    tts_complete.set()
            
            # 音频发送任务：等待第一帧后开始发送缓存的音频
            async def audio_send_task():
                try:
                    # 等待 THG 第一帧
                    await first_video_frame_received.wait()
                    logger.info("[Orchestrator] THG 第一帧已输出，开始发送 TTS 音频")
                    
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
                    logger.error(f"[Orchestrator] 音频发送任务错误: {e}", exc_info=True)
            
            # THG 任务：生成视频
            async def thg_task():
                try:
                    await send_message({
                        "type": "status",
                        "stage": "thg",
                        "message": "开始生成数字人视频..."
                    })
                    
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
                    
                    video_stream = self.thg_service.generate_video(audio_stream_for_thg())
                    
                    chunk_count = 0
                    async for video_frame in video_stream:
                        chunk_count += 1
                        
                        # 第一帧：触发音频发送
                        if chunk_count == 1:
                            first_video_frame_received.set()
                            logger.info("[Orchestrator] THG 第一帧已生成，触发音频发送")
                        
                        # 每 5 个块更新一次进度
                        if chunk_count % 5 == 0:
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
                        
                        message = {
                            "type": "video_chunk",
                            "data": video_base64
                        }
                        if frame_index is not None:
                            message["frame_index"] = frame_index
                        if timestamp_ms is not None:
                            message["timestamp_ms"] = timestamp_ms
                        
                        await send_message(message)
                    
                    await send_message({
                        "type": "status",
                        "stage": "thg",
                        "message": "视频生成完成"
                    })
                except Exception as e:
                    logger.error(f"[Orchestrator] THG 任务错误: {e}", exc_info=True)
                    raise
            
            # 并行执行任务
            tts_collect_task_obj = asyncio.create_task(tts_collect_task())
            audio_send_task_obj = asyncio.create_task(audio_send_task())
            thg_task_obj = asyncio.create_task(thg_task())
            
            # 等待所有任务完成
            await asyncio.gather(tts_collect_task_obj, audio_send_task_obj, thg_task_obj, return_exceptions=True)
            
            # 完成
            await send_message({
                "type": "complete"
            })

        except Exception as e:
            # 错误处理
            logger.error(f"处理过程中发生错误: {e}", exc_info=True)
            await send_message({
                "type": "error",
                "message": f"处理过程中发生错误: {str(e)}"
            })
            raise

    async def process_text_stream_pipeline(
        self,
        text: str,
        send_message: Callable[[dict], Awaitable[None]],
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> None:
        """
        流式处理文本，实现 LLM → TTS 流水线并行

        LLM 按句子输出 → 每个句子立即启动 TTS 合成 → 流式发送音频

        Args:
            text: 输入文本
            send_message: 发送消息的回调函数
            cancel_check: 可选的取消检查函数，返回 True 表示应取消处理
        """
        try:
            # 1. LLM 流式优化
            await send_message({
                "type": "status",
                "stage": "llm",
                "message": "开始流式文本处理..."
            })

            all_tts_chunks: List[bytes] = []
            chunk_index = 0
            sentence_count = 0

            # 检查 LLM 服务是否支持流式输出
            if hasattr(self.llm_service, 'optimize_text_stream'):
                llm_stream = self.llm_service.optimize_text_stream(text)
            else:
                # 不支持流式，使用普通方法包装
                async def _wrap_as_stream():
                    result = await self.llm_service.optimize_text(text)
                    yield result
                llm_stream = _wrap_as_stream()

            full_llm_text = ""

            async for sentence in llm_stream:
                # 检查是否需要取消
                if cancel_check and cancel_check():
                    logger.info("[Pipeline] 处理被取消")
                    return

                sentence_count += 1
                full_llm_text += sentence
                logger.info(f"[Pipeline] LLM 输出句子 {sentence_count}: {sentence[:30]}...")

                # 发送 LLM 流式结果
                await send_message({
                    "type": "llm_stream",
                    "text": sentence,
                    "sentence_index": sentence_count,
                    "is_final": False
                })

                # 2. 立即启动该句子的 TTS 合成
                await send_message({
                    "type": "status",
                    "stage": "tts",
                    "message": f"合成句子 {sentence_count}..."
                })

                audio_stream = self.tts_service.synthesize(sentence)

                async for audio_chunk in audio_stream:
                    # 检查是否需要取消
                    if cancel_check and cancel_check():
                        logger.info("[Pipeline] TTS 处理被取消")
                        return

                    all_tts_chunks.append(audio_chunk)

                    # 流式发送音频块
                    chunk_base64 = base64.b64encode(audio_chunk).decode('utf-8')
                    await send_message({
                        "type": "tts_audio_chunk",
                        "data": chunk_base64,
                        "chunk_index": chunk_index,
                        "is_first": chunk_index == 0,
                        "is_final": False,
                        "sentence_index": sentence_count
                    })
                    chunk_index += 1

            # 发送 LLM 完成标记
            await send_message({
                "type": "llm_stream",
                "text": "",
                "sentence_index": sentence_count,
                "is_final": True
            })

            await send_message({
                "type": "llm_result",
                "text": full_llm_text
            })

            # 发送 TTS 完成标记
            if all_tts_chunks:
                await send_message({
                    "type": "tts_audio_chunk",
                    "data": "",
                    "chunk_index": chunk_index,
                    "is_first": False,
                    "is_final": True
                })
                # 不再发送完整的 tts_audio 消息，避免重复播放

            # 3. THG 生成视频
            await send_message({
                "type": "status",
                "stage": "thg",
                "message": "开始生成数字人视频..."
            })

            async def audio_stream_for_thg() -> AsyncGenerator[bytes, None]:
                for chunk in all_tts_chunks:
                    yield chunk

            video_stream = self.thg_service.generate_video(audio_stream_for_thg())

            frame_count = 0
            async for video_frame in video_stream:
                # 检查是否需要取消
                if cancel_check and cancel_check():
                    logger.info("[Pipeline] THG 处理被取消")
                    return

                frame_count += 1

                if frame_count % 5 == 0:
                    await send_message({
                        "type": "status",
                        "stage": "thg",
                        "message": f"正在生成视频帧... ({frame_count} 帧)"
                    })

                if isinstance(video_frame, dict):
                    video_chunk = video_frame.get("data", b"")
                    frame_index = video_frame.get("frame_index")
                    timestamp_ms = video_frame.get("timestamp_ms")
                else:
                    video_chunk = video_frame
                    frame_index = None
                    timestamp_ms = None

                video_base64 = base64.b64encode(video_chunk).decode('utf-8')

                message = {
                    "type": "video_chunk",
                    "data": video_base64
                }
                if frame_index is not None:
                    message["frame_index"] = frame_index
                if timestamp_ms is not None:
                    message["timestamp_ms"] = timestamp_ms

                await send_message(message)

            await send_message({
                "type": "status",
                "stage": "thg",
                "message": "视频生成完成"
            })

            await send_message({
                "type": "complete"
            })

        except asyncio.CancelledError:
            logger.info("[Pipeline] 处理任务被取消")
            raise
        except Exception as e:
            logger.error(f"[Pipeline] 处理过程中发生错误: {e}", exc_info=True)
            await send_message({
                "type": "error",
                "message": f"处理过程中发生错误: {str(e)}"
            })
            raise

