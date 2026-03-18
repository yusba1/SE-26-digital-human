"""大模型服务接口"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Optional


class LLMService(ABC):
    """大模型服务抽象基类"""

    @abstractmethod
    async def optimize_text(self, text: str) -> str:
        """
        优化文本

        Args:
            text: 原始文本

        Returns:
            优化后的文本
        """
        pass

    async def optimize_text_stream(self, text: str) -> AsyncGenerator[str, None]:
        """
        流式优化文本（默认实现：包装 optimize_text）

        Args:
            text: 原始文本

        Yields:
            优化后的文本块
        """
        result = await self.optimize_text(text)
        yield result

    def set_system_prompt(self, prompt: Optional[str]) -> None:
        """设置系统提示词（默认无操作）"""
        _ = prompt


class MockLLMService(LLMService):
    """Mock 大模型服务实现"""

    def __init__(self, delay: float = 0.0):
        """
        初始化 Mock LLM 服务

        Args:
            delay: 模拟处理延迟（秒），默认 0（无延迟）
        """
        self.delay = delay

    async def optimize_text(self, text: str) -> str:
        """模拟文本优化（实际直接返回原文）"""
        if self.delay > 0:
            import asyncio
            await asyncio.sleep(self.delay)

        # 直接返回原文，不做任何优化
        return text

    async def optimize_text_stream(self, text: str) -> AsyncGenerator[str, None]:
        """流式模拟文本优化"""
        if self.delay > 0:
            import asyncio
            await asyncio.sleep(self.delay)

        # 模拟流式输出：按句子分割
        sentences = []
        current = ""
        for char in text:
            current += char
            if char in "。！？.!?":
                sentences.append(current)
                current = ""
        if current:
            sentences.append(current)

        for sentence in sentences:
            yield sentence

