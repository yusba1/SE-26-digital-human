"""语音活动检测（VAD）服务"""
import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional, Tuple
import numpy as np

logger = logging.getLogger(__name__)

# 检查 Silero VAD 是否可用
try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    torch = None
    TORCH_AVAILABLE = False


class VADState(Enum):
    """VAD 状态"""
    SILENCE = "silence"  # 静音
    SPEECH_START = "speech_start"  # 语音开始
    SPEECH = "speech"  # 说话中
    SPEECH_END = "speech_end"  # 语音结束


class VADService(ABC):
    """VAD 服务抽象基类"""

    @abstractmethod
    def process(self, audio_chunk: bytes, sample_rate: int = 16000) -> Tuple[VADState, float]:
        """
        处理音频块，检测语音活动

        Args:
            audio_chunk: 音频数据（16-bit PCM）
            sample_rate: 采样率

        Returns:
            (VAD 状态, 语音概率/能量值)
        """
        pass

    @abstractmethod
    def reset(self):
        """重置 VAD 状态"""
        pass


class EnergyVADService(VADService):
    """基于能量的简单 VAD 实现"""

    def __init__(
        self,
        energy_threshold: float = 0.01,
        speech_threshold: float = 0.02,
        smoothing_frames: int = 3,
        speech_pad_frames: int = 5,
    ):
        """
        初始化能量 VAD

        Args:
            energy_threshold: 能量阈值（低于此值认为是静音）
            speech_threshold: 语音阈值（高于此值认为是说话）
            smoothing_frames: 平滑帧数
            speech_pad_frames: 语音结束后的填充帧数（防止过早结束）
        """
        self.energy_threshold = energy_threshold
        self.speech_threshold = speech_threshold
        self.smoothing_frames = smoothing_frames
        self.speech_pad_frames = speech_pad_frames

        self.energy_history: list[float] = []
        self.is_speaking = False
        self.silence_frames = 0

    def process(self, audio_chunk: bytes, sample_rate: int = 16000) -> Tuple[VADState, float]:
        """处理音频块"""
        # 转换为 numpy 数组
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0

        # 计算 RMS 能量
        rms = np.sqrt(np.mean(audio_data ** 2))

        # 平滑处理
        self.energy_history.append(rms)
        if len(self.energy_history) > self.smoothing_frames:
            self.energy_history.pop(0)

        avg_energy = sum(self.energy_history) / len(self.energy_history)

        # 状态机逻辑
        prev_speaking = self.is_speaking

        if self.is_speaking:
            # 当前在说话
            if avg_energy < self.energy_threshold:
                self.silence_frames += 1
                if self.silence_frames >= self.speech_pad_frames:
                    self.is_speaking = False
                    self.silence_frames = 0
                    return VADState.SPEECH_END, avg_energy
            else:
                self.silence_frames = 0
            return VADState.SPEECH, avg_energy
        else:
            # 当前静音
            if avg_energy > self.speech_threshold:
                self.is_speaking = True
                self.silence_frames = 0
                return VADState.SPEECH_START, avg_energy
            return VADState.SILENCE, avg_energy

    def reset(self):
        """重置状态"""
        self.energy_history = []
        self.is_speaking = False
        self.silence_frames = 0


class SileroVADService(VADService):
    """Silero VAD 服务实现"""

    def __init__(
        self,
        threshold: float = 0.5,
        min_speech_duration_ms: int = 250,
        min_silence_duration_ms: int = 100,
        speech_pad_ms: int = 30,
    ):
        """
        初始化 Silero VAD

        Args:
            threshold: 语音检测阈值
            min_speech_duration_ms: 最小语音持续时间
            min_silence_duration_ms: 最小静音持续时间
            speech_pad_ms: 语音填充时间
        """
        if not TORCH_AVAILABLE:
            raise ImportError("torch is not installed. Please run: pip install torch")

        self.threshold = threshold
        self.min_speech_duration_ms = min_speech_duration_ms
        self.min_silence_duration_ms = min_silence_duration_ms
        self.speech_pad_ms = speech_pad_ms

        # 加载 Silero VAD 模型
        try:
            self.model, self.utils = torch.hub.load(
                repo_or_dir='snakers4/silero-vad',
                model='silero_vad',
                force_reload=False,
                onnx=False
            )
            self.model.eval()
            logger.info("[SileroVAD] 模型加载成功")
        except Exception as e:
            logger.error(f"[SileroVAD] 模型加载失败: {e}")
            raise

        self.is_speaking = False
        self.speech_frames = 0
        self.silence_frames = 0
        self.sample_rate = 16000

    def process(self, audio_chunk: bytes, sample_rate: int = 16000) -> Tuple[VADState, float]:
        """处理音频块"""
        # 转换为 tensor
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16).astype(np.float32) / 32768.0
        audio_tensor = torch.from_numpy(audio_data)

        # 获取语音概率
        with torch.no_grad():
            speech_prob = self.model(audio_tensor, sample_rate).item()

        # 计算帧时长
        frame_duration_ms = len(audio_data) * 1000 / sample_rate

        # 状态机逻辑
        if speech_prob >= self.threshold:
            self.speech_frames += 1
            self.silence_frames = 0
            speech_duration_ms = self.speech_frames * frame_duration_ms

            if not self.is_speaking and speech_duration_ms >= self.min_speech_duration_ms:
                self.is_speaking = True
                return VADState.SPEECH_START, speech_prob

            if self.is_speaking:
                return VADState.SPEECH, speech_prob

        else:
            self.silence_frames += 1
            silence_duration_ms = self.silence_frames * frame_duration_ms

            if self.is_speaking and silence_duration_ms >= self.min_silence_duration_ms:
                self.is_speaking = False
                self.speech_frames = 0
                return VADState.SPEECH_END, speech_prob

            if not self.is_speaking:
                self.speech_frames = 0

        return VADState.SILENCE if not self.is_speaking else VADState.SPEECH, speech_prob

    def reset(self):
        """重置状态"""
        self.is_speaking = False
        self.speech_frames = 0
        self.silence_frames = 0
        # 重置模型状态
        self.model.reset_states()


def create_vad_service(use_silero: bool = True, **kwargs) -> VADService:
    """
    创建 VAD 服务实例

    Args:
        use_silero: 是否使用 Silero VAD
        **kwargs: 传递给 VAD 服务的参数

    Returns:
        VAD 服务实例
    """
    if use_silero and TORCH_AVAILABLE:
        try:
            return SileroVADService(**kwargs)
        except Exception as e:
            logger.warning(f"[VAD] Silero VAD 初始化失败: {e}，回退到能量 VAD")

    return EnergyVADService(**kwargs)


# 导出可用性标志
SILERO_VAD_AVAILABLE = TORCH_AVAILABLE
