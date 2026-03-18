"""ASR 服务接口"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Callable, Awaitable, Optional


class ASRService(ABC):
    """ASR 服务抽象基类"""
    
    @abstractmethod
    async def recognize(self, audio_data: bytes) -> str:
        """
        识别音频为文字（批量模式）
        
        Args:
            audio_data: 音频数据（字节流）
            
        Returns:
            识别出的文字
        """
        pass
    
    async def recognize_stream(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        send_progress: Optional[Callable[[str], Awaitable[None]]] = None
    ) -> AsyncGenerator[str, None]:
        """
        流式识别音频为文字（可选实现）
        
        Args:
            audio_stream: 音频流（异步生成器）
            send_progress: 进度回调函数（可选）
            
        Yields:
            识别出的文字片段（中间结果和最终结果）
        """
        # 默认实现：收集所有音频块后调用 recognize
        audio_chunks = []
        async for chunk in audio_stream:
            audio_chunks.append(chunk)
        
        if send_progress:
            await send_progress("正在识别语音...")
        
        full_audio = b''.join(audio_chunks)
        result = await self.recognize(full_audio)
        yield result


class MockASRService(ASRService):
    """Mock ASR 服务实现"""
    
    async def recognize(self, audio_data: bytes) -> str:
        """模拟语音识别"""
        # 模拟处理延迟
        import asyncio
        await asyncio.sleep(0.5)
        
        # 返回模拟的识别结果
        return "这是模拟识别的文字，您可以说任何话，这里会显示识别结果。"
    
    async def recognize_stream(
        self, 
        audio_data: bytes,
        send_progress: Callable[[str], Awaitable[None]] = None
    ) -> str:
        """流式识别（带进度更新）"""
        import asyncio
        
        if send_progress:
            await send_progress("正在分析音频特征...")
            await asyncio.sleep(0.2)
            
            await send_progress("正在识别语音内容...")
            await asyncio.sleep(0.2)
            
            await send_progress("正在生成文字结果...")
            await asyncio.sleep(0.1)
        
        return "这是模拟识别的文字，您可以说任何话，这里会显示识别结果。"

