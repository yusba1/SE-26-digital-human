"""THG 数字人服务接口"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator, TypedDict, Optional, Callable
import base64
import numpy as np
import cv2
import asyncio
import io
import os
import wave
import struct
import logging

logger = logging.getLogger(__name__)

try:
    import soundfile as sf
    SOUNDFILE_AVAILABLE = True
except ImportError:
    SOUNDFILE_AVAILABLE = False

try:
    from app.services.dihuman_core import DiHumanProcessor, IDLE_INFERENCE_ENABLED
    DIHUMAN_AVAILABLE = True
except ImportError:
    DIHUMAN_AVAILABLE = False
    IDLE_INFERENCE_ENABLED = False


class THGService(ABC):
    """THG 服务抽象基类"""

    class VideoFrame(TypedDict):
        data: bytes
        timestamp_ms: int
        frame_index: int

    @abstractmethod
    async def generate_video(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> AsyncGenerator["THGService.VideoFrame", None]:
        """
        根据音频流生成数字人视频流

        Args:
            audio_stream: 音频流（异步生成器）
            cancel_check: 可选的取消检查函数，返回 True 表示应取消处理

        Yields:
            视频帧数据（包含帧字节、时间戳与索引）
        """
        pass


class MockTHGService(THGService):
    """Mock THG 服务实现"""

    async def generate_video(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> AsyncGenerator[THGService.VideoFrame, None]:
        """模拟视频生成"""
        import asyncio

        # 消费音频流（模拟处理）
        async for audio_chunk in audio_stream:
            # 检查是否需要取消
            if cancel_check and cancel_check():
                logger.info("[MockTHG] 处理被取消（音频消费阶段）")
                return
            # 模拟根据音频生成视频的处理
            await asyncio.sleep(0.05)
            pass

        # 模拟生成视频帧
        # 实际应用中，这里会调用真实的 THG 服务
        chunk_size = 2048  # 每个块 2KB
        num_chunks = 20  # 生成 20 个视频块（减少数量，加快完成）
        mock_fps = 20
        frame_interval_ms = int(1000 / mock_fps)
        frame_index = 0

        for i in range(num_chunks):
            # 检查是否需要取消
            if cancel_check and cancel_check():
                logger.info("[MockTHG] 处理被取消（视频生成阶段）")
                return

            await asyncio.sleep(0.08)  # 模拟处理延迟（稍微加快）

            # 生成模拟的视频数据（实际应该是真实的视频帧字节流）
            # 这里使用简单的字节序列作为模拟
            mock_video_chunk = b'\xFF' * chunk_size
            timestamp_ms = frame_index * frame_interval_ms
            yield {
                "data": mock_video_chunk,
                "timestamp_ms": timestamp_ms,
                "frame_index": frame_index,
            }
            frame_index += 1


class RealTHGService(THGService):
    """真实的 THG 服务实现，使用 DiHumanProcessor"""

    # DiHumanProcessor 内部处理延迟（毫秒）
    # 来源：dihuman_core.py 中音频处理的内部偏移
    # - 需要积累 450ms (7200 samples) 才开始处理（原 690ms）
    # - 实际取用的音频从 160ms 偏移开始（原 320ms）
    # 这个值用于校正时间戳，使视频帧与音频位置对齐
    AUDIO_PROCESSING_DELAY_MS = 160  # 与 dihuman_core.py 中的 INITIAL_AUDIO_BUFFER_FRAMES * 10 对应

    def __init__(self, data_path: str, use_gpu: bool = True):
        """
        初始化 THG 服务

        Args:
            data_path: THG 数据文件路径（包含模型文件和数据文件）
            use_gpu: 是否使用 GPU
        """
        if not DIHUMAN_AVAILABLE:
            raise ImportError("DiHumanProcessor is not available. Please ensure dihuman_core.py is present.")

        # 将相对路径转换为绝对路径（相对于backend目录）
        if not os.path.isabs(data_path):
            # 获取backend目录的绝对路径
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            data_path = os.path.join(backend_dir, data_path)
            # 规范化路径（处理 ./ 和 ../）
            data_path = os.path.normpath(data_path)
        
        # 验证路径是否存在
        if not os.path.exists(data_path):
            raise FileNotFoundError(
                f"THG数据路径不存在: {data_path}\n"
                f"请检查配置中的 thg_data_path 设置"
            )
        
        self.processor = DiHumanProcessor(data_path, use_gpu=use_gpu)
        self.audio_buffer = np.array([], dtype=np.int16)
        self.target_sample_rate = 16000
        self.chunk_size_samples = 160  # 10ms at 16kHz = 160 samples
    
    def _convert_audio_to_pcm16_16k(self, audio_data: bytes, original_sample_rate: int = None) -> np.ndarray:
        """
        将音频数据转换为 int16 PCM 格式，16000Hz
        
        Args:
            audio_data: 音频数据（字节流）
            original_sample_rate: 原始采样率（如果已知）
            
        Returns:
            int16 PCM 音频数组，16000Hz
        """
        try:
            # 尝试使用 soundfile 读取（如果是 WAV 或其他格式）
            if SOUNDFILE_AVAILABLE:
                # 如果 audio_data 看起来像 WAV 文件头，尝试用 soundfile 解析
                if audio_data[:4] == b'RIFF' or audio_data[:4] == b'FORM':
                    # 将 bytes 写入临时内存缓冲区
                    audio_file = io.BytesIO(audio_data)
                    try:
                        data, sr = sf.read(audio_file, dtype='int16')
                        audio_array = np.array(data, dtype=np.int16)
                        
                        # 如果采样率不是 16000，需要重采样
                        if sr != self.target_sample_rate:
                            # 简单的线性插值重采样（对于实时场景，可以使用更复杂的方法）
                            num_samples = len(audio_array)
                            new_num_samples = int(num_samples * self.target_sample_rate / sr)
                            indices = np.linspace(0, num_samples - 1, new_num_samples)
                            audio_array = np.interp(indices, np.arange(num_samples), audio_array.astype(np.float32)).astype(np.int16)
                        
                        return audio_array
                    except Exception:
                        pass  # 如果 soundfile 无法解析，继续尝试其他方法
            
            # 默认假设已经是 int16 PCM 格式（16000Hz 或需要重采样）
            # 如果原始采样率已知，进行重采样
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            if original_sample_rate and original_sample_rate != self.target_sample_rate:
                num_samples = len(audio_array)
                new_num_samples = int(num_samples * self.target_sample_rate / original_sample_rate)
                indices = np.linspace(0, num_samples - 1, new_num_samples)
                audio_array = np.interp(indices, np.arange(num_samples), audio_array.astype(np.float32)).astype(np.int16)
            
            return audio_array
            
        except Exception as e:
            # 如果所有方法都失败，返回空数组或抛出异常
            print(f"Error converting audio format: {e}")
            # 默认尝试直接解析为 int16 PCM
            return np.frombuffer(audio_data, dtype=np.int16)
    
    async def generate_video(
        self,
        audio_stream: AsyncGenerator[bytes, None],
        cancel_check: Optional[Callable[[], bool]] = None
    ) -> AsyncGenerator[THGService.VideoFrame, None]:
        """
        根据音频流生成数字人视频流

        Args:
            audio_stream: 音频流（异步生成器），支持多种音频格式，会自动转换为 int16 PCM, 16000Hz
            cancel_check: 可选的取消检查函数，返回 True 表示应取消处理

        Yields:
            视频帧数据（包含 JPEG 字节流与时间戳）
        """
        # 每次调用前重置状态，防止上一次被 cancel 时残留数据污染本次推理
        self.audio_buffer = np.array([], dtype=np.int16)
        self.processor.reset()
        logger.info("[RealTHG] 处理器状态已重置，开始新一轮视频生成")

        processed_samples = 0
        frame_index = 0
        check_interval = 10  # 每处理 10 帧检查一次取消状态

        try:
            # 处理音频流
            async for audio_chunk in audio_stream:
                # 检查是否需要取消
                if cancel_check and cancel_check():
                    logger.info("[RealTHG] 处理被取消（音频消费阶段）")
                    return

                if not audio_chunk:
                    continue

                # 将音频块转换为 int16 PCM, 16000Hz 格式
                try:
                    audio_data = self._convert_audio_to_pcm16_16k(audio_chunk)
                except Exception as e:
                    print(f"Error converting audio chunk: {e}")
                    continue

                if len(audio_data) == 0:
                    continue

                # 添加到缓冲区
                self.audio_buffer = np.concatenate([self.audio_buffer, audio_data])

                # 按 10ms (160 samples) 的块处理
                frames_processed_in_chunk = 0
                while len(self.audio_buffer) >= self.chunk_size_samples:
                    # 定期检查取消状态
                    if frames_processed_in_chunk % check_interval == 0:
                        if cancel_check and cancel_check():
                            logger.info("[RealTHG] 处理被取消（帧处理阶段）")
                            return

                    # 提取一个 10ms 的音频帧
                    audio_frame = self.audio_buffer[:self.chunk_size_samples]
                    self.audio_buffer = self.audio_buffer[self.chunk_size_samples:]
                    processed_samples += self.chunk_size_samples
                    frames_processed_in_chunk += 1

                    # 调用 DiHumanProcessor 处理
                    # process 方法返回 (return_img, playing_audio, check_img)
                    # return_img: BGR 图像（numpy array）或 None
                    # playing_audio: int16 PCM 音频
                    # check_img: 1 表示有新图像，0 表示没有
                    try:
                        # 在线程池中运行 ONNX 推理，避免阻塞 asyncio 事件循环
                        # 这样 audio_send_task 等协程可以在推理期间正常运行
                        loop = asyncio.get_running_loop()
                        return_img, playing_audio, check_img = await loop.run_in_executor(
                            None, self.processor.process, audio_frame
                        )

                        # 如果有新图像，编码为 JPEG 并返回
                        if check_img == 1 and return_img is not None:
                            # 将 BGR 图像编码为 JPEG
                            success, encoded_img = cv2.imencode('.jpg', return_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                            if success:
                                # 返回 JPEG 图像的字节流
                                video_chunk = encoded_img.tobytes()
                                # 计算时间戳并校正内部处理延迟
                                # 原始时间戳基于累计输入样本数
                                raw_timestamp_ms = int(processed_samples * 1000 / self.target_sample_rate)
                                # 减去内部处理延迟，使时间戳与实际音频位置对齐
                                timestamp_ms = max(0, raw_timestamp_ms - self.AUDIO_PROCESSING_DELAY_MS)
                                yield {
                                    "data": video_chunk,
                                    "timestamp_ms": timestamp_ms,
                                    "frame_index": frame_index,
                                }
                                frame_index += 1

                    except Exception as e:
                        # 处理异常，继续处理下一个音频块
                        print(f"Error processing audio frame: {e}")
                        continue

            # 处理剩余的音频缓冲区（如果有）
            if len(self.audio_buffer) > 0:
                # 填充到 160 samples
                padding = np.zeros(self.chunk_size_samples - len(self.audio_buffer), dtype=np.int16)
                audio_frame = np.concatenate([self.audio_buffer, padding])
                processed_samples += self.chunk_size_samples
                try:
                    loop = asyncio.get_running_loop()
                    return_img, playing_audio, check_img = await loop.run_in_executor(
                        None, self.processor.process, audio_frame
                    )
                    if check_img == 1 and return_img is not None:
                        success, encoded_img = cv2.imencode('.jpg', return_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                        if success:
                            video_chunk = encoded_img.tobytes()
                            raw_timestamp_ms = int(processed_samples * 1000 / self.target_sample_rate)
                            timestamp_ms = max(0, raw_timestamp_ms - self.AUDIO_PROCESSING_DELAY_MS)
                            yield {
                                "data": video_chunk,
                                "timestamp_ms": timestamp_ms,
                                "frame_index": frame_index,
                            }
                            frame_index += 1
                except Exception as e:
                    print(f"Error processing final audio frame: {e}")

        finally:
            # 无论正常结束、被 cancel 还是抛异常，都清理状态
            self.audio_buffer = np.array([], dtype=np.int16)
            logger.info(f"[RealTHG] 视频生成结束，共 {frame_index} 帧，状态已清理")
    
    def reset(self):
        """重置处理器状态"""
        self.processor.reset()
        self.audio_buffer = np.array([], dtype=np.int16)
    
    async def generate_idle_video(
        self,
        cancel_check: Optional[Callable[[], bool]] = None,
        fps: int = 15
    ) -> AsyncGenerator[THGService.VideoFrame, None]:
        """
        生成空闲状态的视频流（聆听中）
        
        使用空音频进行推理，让嘴型保持闭合，同时保留自然的身体/表情变化
        
        Args:
            cancel_check: 取消检查函数，返回 True 时停止生成
            fps: 目标帧率
            
        Yields:
            视频帧数据
        """
        if not IDLE_INFERENCE_ENABLED:
            logger.info("[RealTHG] 空闲推理未启用，跳过空闲视频生成")
            return
        
        frame_interval = 1.0 / fps
        frame_index = 0
        
        logger.info(f"[RealTHG] 开始空闲视频生成，目标帧率: {fps} fps")
        
        while True:
            # 检查是否需要取消
            if cancel_check and cancel_check():
                logger.info("[RealTHG] 空闲视频生成被取消")
                break
            
            # 用空音频帧调用 process
            silent_frame = np.zeros(self.chunk_size_samples, dtype=np.int16)
            
            try:
                return_img, playing_audio, check_img = self.processor.process(silent_frame)
                
                if check_img == 1 and return_img is not None:
                    # 编码为 JPEG
                    success, encoded_img = cv2.imencode('.jpg', return_img, [cv2.IMWRITE_JPEG_QUALITY, 95])
                    if success:
                        video_chunk = encoded_img.tobytes()
                        timestamp_ms = int(frame_index * 1000 / fps)
                        yield {
                            "data": video_chunk,
                            "timestamp_ms": timestamp_ms,
                            "frame_index": frame_index,
                        }
                        frame_index += 1
                
                # 控制帧率
                await asyncio.sleep(frame_interval)
                
            except Exception as e:
                logger.error(f"[RealTHG] 空闲视频生成错误: {e}")
                await asyncio.sleep(frame_interval)
                continue