"""通义千问流式 LLM 服务"""
import asyncio
import logging
from typing import AsyncGenerator, Optional

from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

# 检查 DashScope 是否可用
try:
    import dashscope
    from dashscope import Generation
    DASHSCOPE_AVAILABLE = True
except ImportError:
    dashscope = None
    Generation = None
    DASHSCOPE_AVAILABLE = False


class QwenLLMService(LLMService):
    """通义千问 LLM 服务实现"""

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-turbo",
        system_prompt: Optional[str] = None,
    ):
        """
        初始化通义千问 LLM 服务

        Args:
            api_key: DashScope API Key
            model: 模型名称，默认 qwen-turbo（快速模型）
                   可选: qwen-turbo, qwen-plus, qwen-max
            system_prompt: 系统提示词，用于指导模型行为
        """
        if not DASHSCOPE_AVAILABLE:
            raise ImportError("dashscope is not installed. Please run: pip install dashscope")

        dashscope.api_key = api_key
        self.model = model
        self._default_prompt = "你是一个友好的数字人助手，请用简洁自然的语言回答问题。"
        self.system_prompt = system_prompt or self._default_prompt

    def set_system_prompt(self, prompt: Optional[str]) -> None:
        self.system_prompt = prompt or self._default_prompt

    async def optimize_text(self, text: str) -> str:
        """
        使用通义千问优化文本

        Args:
            text: 原始文本

        Returns:
            优化后的文本
        """
        if not text or not text.strip():
            return text

        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": text}
            ]

            # 同步调用，在线程池中执行
            def _call_llm():
                response = Generation.call(
                    model=self.model,
                    messages=messages,
                    result_format="message",
                )
                if response.status_code == 200:
                    return response.output.choices[0].message.content
                else:
                    logger.error(f"[QwenLLM] API Error: {response.code} - {response.message}")
                    return text

            result = await asyncio.to_thread(_call_llm)
            logger.info(f"[QwenLLM] 文本优化完成: {result[:50]}...")
            return result

        except Exception as e:
            logger.error(f"[QwenLLM] Error: {e}")
            return text

    async def optimize_text_stream(self, text: str) -> AsyncGenerator[str, None]:
        """
        流式优化文本，按句子边界返回

        Args:
            text: 原始文本

        Yields:
            优化后的文本块（按句子分割）
        """
        if not text or not text.strip():
            yield text
            return

        try:
            messages = [
                {"role": "system", "content": self.system_prompt},
                {"role": "user", "content": text}
            ]

            # 使用流式 API
            def _stream_llm():
                responses = Generation.call(
                    model=self.model,
                    messages=messages,
                    result_format="message",
                    stream=True,
                    incremental_output=True,  # 增量输出
                )
                return responses

            # 在线程池中启动流式调用
            response_generator = await asyncio.to_thread(_stream_llm)

            # 累积文本，按句子边界分割
            buffer = ""
            sentence_endings = "。！？.!?"

            for response in response_generator:
                if response.status_code == 200:
                    delta = response.output.choices[0].message.content
                    if delta:
                        buffer += delta

                        # 检查是否有完整的句子
                        last_end = -1
                        for i, char in enumerate(buffer):
                            if char in sentence_endings:
                                last_end = i

                        if last_end >= 0:
                            # 返回完整的句子
                            sentence = buffer[:last_end + 1]
                            buffer = buffer[last_end + 1:]
                            if sentence.strip():
                                logger.debug(f"[QwenLLM Stream] 输出句子: {sentence[:30]}...")
                                yield sentence
                else:
                    logger.error(f"[QwenLLM] Stream Error: {response.code} - {response.message}")
                    break

            # 返回剩余的文本
            if buffer.strip():
                logger.debug(f"[QwenLLM Stream] 输出剩余: {buffer[:30]}...")
                yield buffer

        except Exception as e:
            logger.error(f"[QwenLLM] Stream Error: {e}")
            # 出错时返回原文
            yield text


class QwenChatLLMService(LLMService):
    """通义千问对话式 LLM 服务（支持多轮对话）"""

    def __init__(
        self,
        api_key: str,
        model: str = "qwen-turbo",
        system_prompt: Optional[str] = None,
        max_history: int = 10,
    ):
        """
        初始化通义千问对话式 LLM 服务

        Args:
            api_key: DashScope API Key
            model: 模型名称
            system_prompt: 系统提示词
            max_history: 保留的最大历史消息数
        """
        if not DASHSCOPE_AVAILABLE:
            raise ImportError("dashscope is not installed. Please run: pip install dashscope")

        dashscope.api_key = api_key
        self.model = model
        self._default_prompt = "你是一个友好的数字人助手，请用简洁自然的语言回答问题。"
        self.system_prompt = system_prompt or self._default_prompt
        self.max_history = max_history
        self.history: list[dict] = []

    def set_system_prompt(self, prompt: Optional[str]) -> None:
        self.system_prompt = prompt or self._default_prompt

    def clear_history(self):
        """清空对话历史"""
        self.history = []

    def add_user_message(self, content: str):
        """添加用户消息到历史"""
        self.history.append({"role": "user", "content": content})
        self._trim_history()

    def add_assistant_message(self, content: str):
        """添加助手消息到历史"""
        self.history.append({"role": "assistant", "content": content})
        self._trim_history()

    def _trim_history(self):
        """修剪历史记录"""
        if len(self.history) > self.max_history * 2:
            self.history = self.history[-(self.max_history * 2):]

    async def optimize_text(self, text: str) -> str:
        """对话式文本优化"""
        if not text or not text.strip():
            return text

        try:
            # 构建消息列表
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(self.history)
            messages.append({"role": "user", "content": text})

            def _call_llm():
                response = Generation.call(
                    model=self.model,
                    messages=messages,
                    result_format="message",
                )
                if response.status_code == 200:
                    return response.output.choices[0].message.content
                else:
                    logger.error(f"[QwenChatLLM] API Error: {response.code} - {response.message}")
                    return text

            result = await asyncio.to_thread(_call_llm)

            # 更新历史
            self.add_user_message(text)
            self.add_assistant_message(result)

            logger.info(f"[QwenChatLLM] 对话完成: {result[:50]}...")
            return result

        except Exception as e:
            logger.error(f"[QwenChatLLM] Error: {e}")
            return text

    async def optimize_text_stream(self, text: str) -> AsyncGenerator[str, None]:
        """流式对话"""
        if not text or not text.strip():
            yield text
            return

        try:
            messages = [{"role": "system", "content": self.system_prompt}]
            messages.extend(self.history)
            messages.append({"role": "user", "content": text})

            def _stream_llm():
                return Generation.call(
                    model=self.model,
                    messages=messages,
                    result_format="message",
                    stream=True,
                    incremental_output=True,
                )

            response_generator = await asyncio.to_thread(_stream_llm)

            buffer = ""
            full_response = ""
            sentence_endings = "。！？.!?"

            for response in response_generator:
                if response.status_code == 200:
                    delta = response.output.choices[0].message.content
                    if delta:
                        buffer += delta
                        full_response += delta

                        # 按句子边界分割
                        last_end = -1
                        for i, char in enumerate(buffer):
                            if char in sentence_endings:
                                last_end = i

                        if last_end >= 0:
                            sentence = buffer[:last_end + 1]
                            buffer = buffer[last_end + 1:]
                            if sentence.strip():
                                yield sentence
                else:
                    logger.error(f"[QwenChatLLM] Stream Error: {response.code}")
                    break

            if buffer.strip():
                yield buffer

            # 更新历史
            self.add_user_message(text)
            self.add_assistant_message(full_response)

        except Exception as e:
            logger.error(f"[QwenChatLLM] Stream Error: {e}")
            yield text
