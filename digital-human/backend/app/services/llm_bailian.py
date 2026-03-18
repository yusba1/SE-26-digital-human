"""阿里云百炼应用 LLM 服务"""
import asyncio
import logging
from http import HTTPStatus
from typing import AsyncGenerator, Optional

from app.services.llm_service import LLMService

logger = logging.getLogger(__name__)

# 检查 DashScope 是否可用
try:
    import dashscope
    from dashscope import Application
    DASHSCOPE_AVAILABLE = True
except ImportError:
    dashscope = None
    Application = None
    DASHSCOPE_AVAILABLE = False


class BailianLLMService(LLMService):
    """阿里云百炼应用 LLM 服务实现"""

    def __init__(
        self,
        api_key: str,
        app_id: str,
        session_id: Optional[str] = None,
    ):
        """
        初始化百炼应用 LLM 服务

        Args:
            api_key: DashScope API Key
            app_id: 百炼应用ID
            session_id: 会话ID，用于多轮对话（可选）
        """
        if not DASHSCOPE_AVAILABLE:
            raise ImportError("dashscope is not installed. Please run: pip install dashscope")

        dashscope.api_key = api_key
        self.api_key = api_key
        self.app_id = app_id
        self.session_id = session_id

    def get_session_id(self) -> Optional[str]:
        """获取当前会话ID"""
        return self.session_id

    def set_session_id(self, session_id: Optional[str]) -> None:
        """设置会话ID"""
        self.session_id = session_id

    def clear_session(self) -> None:
        """清空会话，开始新的对话"""
        self.session_id = None

    async def optimize_text(self, text: str) -> str:
        """
        使用百炼应用优化文本

        Args:
            text: 原始文本

        Returns:
            优化后的文本
        """
        if not text or not text.strip():
            return text

        try:
            def _call_bailian():
                response = Application.call(
                    api_key=self.api_key,
                    app_id=self.app_id,
                    prompt=text,
                    session_id=self.session_id,  # 传入session_id支持多轮对话
                )
                return response

            # 在线程池中执行同步调用
            response = await asyncio.to_thread(_call_bailian)

            if response.status_code != HTTPStatus.OK:
                logger.error(
                    f"[BailianLLM] API Error: {response.code} - {response.message}, "
                    f"request_id={response.request_id}"
                )
                # 出错时返回原文
                return text

            # 获取返回的文本
            result = response.output.text if hasattr(response.output, 'text') else str(response.output)
            
            # 更新session_id用于下一轮对话
            if hasattr(response.output, 'session_id') and response.output.session_id:
                self.session_id = response.output.session_id
                logger.debug(f"[BailianLLM] Session ID updated: {self.session_id}")

            logger.info(f"[BailianLLM] 文本处理完成: {result[:50]}...")
            return result

        except Exception as e:
            logger.error(f"[BailianLLM] Error: {e}", exc_info=True)
            # 出错时返回原文
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
            def _stream_bailian():
                responses = Application.call(
                    api_key=self.api_key,
                    app_id=self.app_id,
                    prompt=text,
                    session_id=self.session_id,
                    stream=True,  # 流式输出
                    incremental_output=True,  # 增量输出
                )
                return responses

            # 在线程池中启动流式调用
            response_generator = await asyncio.to_thread(_stream_bailian)

            # 累积文本，按句子边界分割
            buffer = ""
            sentence_endings = "。！？.!?"
            full_response = ""

            for response in response_generator:
                if response.status_code != HTTPStatus.OK:
                    logger.error(
                        f"[BailianLLM] Stream Error: {response.code} - {response.message}, "
                        f"request_id={response.request_id}"
                    )
                    break

                # 获取增量文本
                if hasattr(response.output, 'text') and response.output.text:
                    delta = response.output.text
                    buffer += delta
                    full_response += delta

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
                            logger.debug(f"[BailianLLM Stream] 输出句子: {sentence[:30]}...")
                            yield sentence

                # 更新session_id（通常在最后一个响应中）
                if hasattr(response.output, 'session_id') and response.output.session_id:
                    self.session_id = response.output.session_id

            # 返回剩余的文本
            if buffer.strip():
                logger.debug(f"[BailianLLM Stream] 输出剩余: {buffer[:30]}...")
                yield buffer

            # 注意：流式输出中session_id已经在循环中处理了

        except Exception as e:
            logger.error(f"[BailianLLM] Stream Error: {e}", exc_info=True)
            # 出错时返回原文
            yield text
