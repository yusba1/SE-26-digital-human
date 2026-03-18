"""听悟（Tingwu）ASR 服务实现"""
import logging
from typing import AsyncGenerator, Callable, Awaitable, Optional
from app.services.asr_service import ASRService
from app.services.tingwu_client import TingwuRealtimeClient, TingwuConfig

logger = logging.getLogger(__name__)


class TingwuASRService(ASRService):
    """听悟 ASR 服务实现，封装 TingwuRealtimeClient"""
    
    def __init__(self, config: Optional[TingwuConfig] = None):
        """
        初始化听悟 ASR 服务
        
        Args:
            config: 听悟配置，如果为 None 则使用默认配置（从环境变量读取）
        """
        self.config = config or TingwuConfig()
        self.client = TingwuRealtimeClient(self.config)
        logger.info(f"TingwuASRService initialized, using real SDK: {self.client._client is not None}")
    
    async def recognize(self, audio_data: bytes) -> str:
        """
        批量识别音频为文字
        
        Args:
            audio_data: 完整的音频数据（字节流）
            
        Returns:
            识别出的文字（最后一个完整句子的文本）
        """
        # 对于批量识别，将音频数据作为单个块处理
        async def audio_iter():
            yield audio_data
        
        last_result = ""
        async for result in self.client.stream_transcribe(audio_iter()):
            text = result.get("text", "")
            raw = result.get("raw", {})
            header = raw.get("header", {})
            message_name = header.get("name", "")
            
            # 只返回最终结果（SentenceEnd）
            if message_name == "SentenceEnd" and text:
                last_result = text
        
        return last_result if last_result else "识别失败或未识别到内容"
    
    async def recognize_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        send_progress: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式识别音频为文字
        
        Args:
            audio_stream: 音频流（异步生成器）
            send_progress: 进度回调函数（可选）
            
        Yields:
            识别出的文字片段（中间结果和最终结果）
        """
        if send_progress:
            await send_progress("开始听悟实时转写...")
        
        async for result in self.client.stream_transcribe(audio_stream):
            text = result.get("text", "")
            raw = result.get("raw", {})
            header = raw.get("header", {})
            message_name = header.get("name", "")
            
            if not text:
                continue
            
            # 发送中间结果和最终结果
            if message_name in ("TranscriptionResultChanged", "SentenceEnd"):
                if send_progress:
                    is_final = message_name == "SentenceEnd"
                    status = "识别完成" if is_final else "识别中..."
                    await send_progress(f"{status}: {text[:50]}...")
                
                yield text
