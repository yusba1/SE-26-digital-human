"""会话状态管理器"""
import asyncio
import logging
from enum import Enum
from typing import Optional, Callable, Awaitable, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


class ConversationState(Enum):
    """会话状态"""
    IDLE = "idle"  # 空闲，等待用户输入
    USER_SPEAKING = "user_speaking"  # 用户正在说话
    PROCESSING = "processing"  # 正在处理（ASR/LLM/TTS）
    DIGITAL_HUMAN_SPEAKING = "digital_human_speaking"  # 数字人正在说话
    INTERRUPTED = "interrupted"  # 被打断


@dataclass
class ConversationContext:
    """会话上下文"""
    session_id: str
    state: ConversationState = ConversationState.IDLE
    current_text: str = ""  # 当前处理的文本
    interrupt_requested: bool = False  # 是否请求打断
    last_state_change: datetime = field(default_factory=datetime.now)
    processing_task: Optional[asyncio.Task] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class ConversationManager:
    """会话状态管理器"""

    def __init__(self, session_id: str):
        """
        初始化会话管理器

        Args:
            session_id: 会话 ID
        """
        self.context = ConversationContext(session_id=session_id)
        self._state_listeners: list[Callable[[ConversationState, ConversationState], Awaitable[None]]] = []
        self._cancel_event = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def state(self) -> ConversationState:
        """获取当前状态"""
        return self.context.state

    @property
    def is_cancelled(self) -> bool:
        """检查是否已取消"""
        return self.context.interrupt_requested

    async def transition_to(self, new_state: ConversationState) -> bool:
        """
        转换到新状态

        Args:
            new_state: 新状态

        Returns:
            是否转换成功
        """
        async with self._lock:
            old_state = self.context.state

            # 验证状态转换是否有效
            if not self._is_valid_transition(old_state, new_state):
                logger.warning(f"[ConversationManager] 无效的状态转换: {old_state} -> {new_state}")
                return False

            self.context.state = new_state
            self.context.last_state_change = datetime.now()
            logger.info(f"[ConversationManager] 状态转换: {old_state} -> {new_state}")

            # 通知监听器
            for listener in self._state_listeners:
                try:
                    await listener(old_state, new_state)
                except Exception as e:
                    logger.error(f"[ConversationManager] 状态监听器错误: {e}")

            return True

    def _is_valid_transition(self, from_state: ConversationState, to_state: ConversationState) -> bool:
        """
        验证状态转换是否有效

        状态转换规则:
        - IDLE -> USER_SPEAKING, PROCESSING
        - USER_SPEAKING -> PROCESSING, IDLE
        - PROCESSING -> DIGITAL_HUMAN_SPEAKING, IDLE, INTERRUPTED
        - DIGITAL_HUMAN_SPEAKING -> IDLE, INTERRUPTED, USER_SPEAKING
        - INTERRUPTED -> IDLE, USER_SPEAKING
        """
        valid_transitions = {
            ConversationState.IDLE: {
                ConversationState.USER_SPEAKING,
                ConversationState.PROCESSING
            },
            ConversationState.USER_SPEAKING: {
                ConversationState.PROCESSING,
                ConversationState.IDLE
            },
            ConversationState.PROCESSING: {
                ConversationState.DIGITAL_HUMAN_SPEAKING,
                ConversationState.IDLE,
                ConversationState.INTERRUPTED
            },
            ConversationState.DIGITAL_HUMAN_SPEAKING: {
                ConversationState.IDLE,
                ConversationState.INTERRUPTED,
                ConversationState.USER_SPEAKING
            },
            ConversationState.INTERRUPTED: {
                ConversationState.IDLE,
                ConversationState.USER_SPEAKING
            }
        }

        return to_state in valid_transitions.get(from_state, set())

    def add_state_listener(self, listener: Callable[[ConversationState, ConversationState], Awaitable[None]]):
        """添加状态变化监听器"""
        self._state_listeners.append(listener)

    def remove_state_listener(self, listener: Callable[[ConversationState, ConversationState], Awaitable[None]]):
        """移除状态变化监听器"""
        if listener in self._state_listeners:
            self._state_listeners.remove(listener)

    async def start_user_speaking(self):
        """用户开始说话"""
        await self.transition_to(ConversationState.USER_SPEAKING)

    async def stop_user_speaking(self):
        """用户停止说话"""
        if self.state == ConversationState.USER_SPEAKING:
            await self.transition_to(ConversationState.PROCESSING)

    async def start_processing(self, text: str):
        """开始处理"""
        self.context.current_text = text
        self.context.interrupt_requested = False
        self._cancel_event.clear()
        await self.transition_to(ConversationState.PROCESSING)

    async def start_digital_human_speaking(self):
        """数字人开始说话"""
        await self.transition_to(ConversationState.DIGITAL_HUMAN_SPEAKING)

    async def finish_speaking(self):
        """完成说话"""
        self.context.current_text = ""
        await self.transition_to(ConversationState.IDLE)

    async def interrupt(self) -> bool:
        """
        请求打断

        Returns:
            是否成功请求打断
        """
        if self.state in (ConversationState.PROCESSING, ConversationState.DIGITAL_HUMAN_SPEAKING):
            async with self._lock:
                self.context.interrupt_requested = True
                self._cancel_event.set()

                # 取消正在运行的任务
                if self.context.processing_task and not self.context.processing_task.done():
                    self.context.processing_task.cancel()

            await self.transition_to(ConversationState.INTERRUPTED)
            logger.info("[ConversationManager] 打断请求已处理")
            return True

        logger.warning(f"[ConversationManager] 当前状态 {self.state} 不支持打断")
        return False

    async def recover_from_interrupt(self):
        """从打断状态恢复"""
        if self.state == ConversationState.INTERRUPTED:
            self.context.interrupt_requested = False
            self._cancel_event.clear()
            await self.transition_to(ConversationState.IDLE)

    def set_processing_task(self, task: asyncio.Task):
        """设置当前处理任务"""
        self.context.processing_task = task

    def check_cancelled(self) -> bool:
        """检查是否需要取消当前处理"""
        return self.context.interrupt_requested

    async def wait_for_cancel(self, timeout: Optional[float] = None) -> bool:
        """
        等待取消事件

        Args:
            timeout: 超时时间（秒）

        Returns:
            是否收到取消信号
        """
        try:
            await asyncio.wait_for(self._cancel_event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

    def reset(self):
        """重置会话状态"""
        self.context = ConversationContext(session_id=self.context.session_id)
        self._cancel_event.clear()
        logger.info("[ConversationManager] 会话状态已重置")

    def get_state_info(self) -> Dict[str, Any]:
        """获取当前状态信息"""
        return {
            "session_id": self.context.session_id,
            "state": self.context.state.value,
            "current_text": self.context.current_text[:50] if self.context.current_text else "",
            "interrupt_requested": self.context.interrupt_requested,
            "last_state_change": self.context.last_state_change.isoformat(),
            "has_active_task": self.context.processing_task is not None and not self.context.processing_task.done()
        }
