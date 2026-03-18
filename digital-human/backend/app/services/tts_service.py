"""TTS 服务接口"""
from abc import ABC, abstractmethod
from typing import AsyncGenerator
import io
import platform
import shutil
import aiohttp
import asyncio

# Check if edge_tts is available
try:
    import edge_tts
    EDGE_TTS_AVAILABLE = True
except ImportError:
    EDGE_TTS_AVAILABLE = False

try:
    import miniaudio
    MINIAUDIO_AVAILABLE = True
except ImportError:
    miniaudio = None
    MINIAUDIO_AVAILABLE = False

MACOS_TTS_AVAILABLE = platform.system() == "Darwin" and shutil.which("say") is not None


# Check if aiohttp is available for Aliyun TTS
ALIYUN_TTS_AVAILABLE = True

# Check if dashscope is available for DashScope TTS
try:
    import dashscope
    from dashscope.audio.tts_v2 import SpeechSynthesizer, ResultCallback, AudioFormat
    DASHSCOPE_TTS_AVAILABLE = True
except ImportError:
    dashscope = None
    SpeechSynthesizer = None
    ResultCallback = None
    AudioFormat = None
    DASHSCOPE_TTS_AVAILABLE = False


class TTSService(ABC):
    """TTS 服务抽象基类"""
    
    @abstractmethod
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        将文本合成为音频流
        
        Args:
            text: 要合成的文本
            
        Yields:
            音频数据块（字节流）
        """
        pass


def _resample_audio(audio_data, src_rate: int, dst_rate: int):
    if src_rate == dst_rate:
        return audio_data
    if len(audio_data) == 0:
        return audio_data
    import numpy as np
    num_samples = len(audio_data)
    new_num_samples = int(num_samples * dst_rate / src_rate)
    indices = np.linspace(0, num_samples - 1, new_num_samples)
    return np.interp(indices, np.arange(num_samples), audio_data.astype(np.float32)).astype(np.int16)


def _load_audio_file(path: str):
    import numpy as np
    try:
        import soundfile as sf
        data, sr = sf.read(path, dtype="int16")
        audio = np.array(data, dtype=np.int16)
        if audio.ndim > 1:
            audio = audio.mean(axis=1).astype(np.int16)
        return audio, sr
    except Exception:
        pass

    import aifc
    with aifc.open(path, "rb") as audio_file:
        sr = audio_file.getframerate()
        channels = audio_file.getnchannels()
        sample_width = audio_file.getsampwidth()
        frames = audio_file.readframes(audio_file.getnframes())

    if sample_width == 2:
        audio = np.frombuffer(frames, dtype=">i2")
    elif sample_width == 1:
        audio = (np.frombuffer(frames, dtype=np.uint8).astype(np.int16) - 128) << 8
    else:
        import audioop
        converted = audioop.lin2lin(frames, sample_width, 2)
        audio = np.frombuffer(converted, dtype=">i2")

    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    audio = audio.astype(np.int16)
    return audio, sr


class EdgeTTSService(TTSService):
    """Edge TTS 服务实现 - 使用微软 Edge TTS 生成真实语音"""
    
    def __init__(self, voice: str = "zh-CN-XiaoxiaoNeural"):
        """
        初始化 Edge TTS 服务
        
        Args:
            voice: 语音名称，默认使用中文女声
                   可选: zh-CN-XiaoxiaoNeural, zh-CN-YunxiNeural, zh-CN-YunyangNeural
        """
        if not EDGE_TTS_AVAILABLE:
            raise ImportError("edge-tts is not installed. Please run: pip install edge-tts")
        if not MINIAUDIO_AVAILABLE:
            raise ImportError("miniaudio is required for EdgeTTSService. Please run: pip install miniaudio")
        self.voice = voice
        self.sample_rate = 16000  # THG model expects 16kHz
    
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        使用 Edge TTS 合成语音
        
        生成 16kHz, 16-bit PCM 格式的音频流，用于 THG 模型处理
        """
        if not text or not text.strip():
            return
        
        try:
            # Create Edge TTS communicate object
            communicate = edge_tts.Communicate(text, self.voice)
            
            # Collect all audio chunks first (Edge TTS returns MP3 format)
            audio_data = io.BytesIO()
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data.write(chunk["data"])
            
            audio_data.seek(0)
            mp3_bytes = audio_data.read()
            
            if len(mp3_bytes) == 0:
                print("[EdgeTTS] Warning: No audio data received")
                fallback = MockTTSService()
                async for chunk in fallback.synthesize(text):
                    yield chunk
                return
            
            # Convert MP3 to PCM using miniaudio
            try:
                # Decode MP3 to PCM (16kHz, mono, 16-bit signed)
                decoded = miniaudio.decode(mp3_bytes, sample_rate=self.sample_rate, nchannels=1)
                
                # Get PCM bytes directly from array.array (typecode 'h' = int16)
                pcm_data = decoded.samples.tobytes()
                
                duration_sec = len(pcm_data) / (self.sample_rate * 2)  # 2 bytes per sample
                print(f"[EdgeTTS] Decoded {len(pcm_data)} bytes of PCM audio ({duration_sec:.1f}s)")
                
                # Yield in chunks (3200 bytes = 100ms at 16kHz, 16-bit)
                chunk_size = 3200
                for i in range(0, len(pcm_data), chunk_size):
                    yield pcm_data[i:i + chunk_size]
                    
            except Exception as decode_error:
                print(f"[EdgeTTS] MP3 decode error: {decode_error}")
                import traceback
                traceback.print_exc()
                # Fallback to mock audio to keep THG moving
                fallback = MockTTSService()
                async for chunk in fallback.synthesize(text):
                    yield chunk
                    
        except Exception as e:
            print(f"[EdgeTTS] Error: {e}")
            import traceback
            traceback.print_exc()
            fallback = MockTTSService()
            async for chunk in fallback.synthesize(text):
                yield chunk


class MacOSTTSService(TTSService):
    """macOS 'say' TTS fallback service"""
    
    def __init__(self, voice: str = None, sample_rate: int = 16000):
        if not MACOS_TTS_AVAILABLE:
            raise ImportError("macOS 'say' command is not available.")
        self.voice = voice
        self.sample_rate = sample_rate
    
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        if not text or not text.strip():
            return
        
        import asyncio
        import os
        import subprocess
        import tempfile
        
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".aiff", delete=False) as tmp:
                tmp_path = tmp.name
            
            cmd = ["say", "-o", tmp_path]
            if self.voice:
                cmd.extend(["-v", self.voice])
            cmd.append(text)
            
            await asyncio.to_thread(
                subprocess.run,
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            
            audio_data, sr = _load_audio_file(tmp_path)
            audio_data = _resample_audio(audio_data, sr, self.sample_rate)
            pcm_data = audio_data.tobytes()
            
            chunk_size = 3200  # 100ms at 16kHz, 16-bit
            for i in range(0, len(pcm_data), chunk_size):
                yield pcm_data[i:i + chunk_size]
        except Exception as e:
            print(f"[MacOSTTS] Error: {e}")
            import traceback
            traceback.print_exc()
            fallback = MockTTSService()
            async for chunk in fallback.synthesize(text):
                yield chunk
        finally:
            if tmp_path:
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass


class AliyunTTSService(TTSService):
    """Aliyun TTS RESTful API service implementation"""
    
    # Aliyun TTS gateway URLs
    GATEWAY_URL = "https://nls-gateway-cn-shanghai.aliyuncs.com/stream/v1/tts"
    
    def __init__(
        self,
        appkey: str,
        token: str,
        voice: str = "zhitian_emo",
        format: str = "wav",
        sample_rate: int = 16000,
        volume: int = 50,
        speech_rate: int = 0,
        pitch_rate: int = 0,
    ):
        """
        Initialize Aliyun TTS service
        
        Args:
            appkey: Aliyun NLS project appkey
            token: Aliyun access token (obtained from NLS API)
            voice: Voice name, default "zhitian_emo" (Chinese female with emotion)
            format: Audio format, pcm/wav/mp3, default "wav"
            sample_rate: Sample rate, 8000/16000, default 16000
            volume: Volume level 0-100, default 50
            speech_rate: Speech rate -500~500, default 0
            pitch_rate: Pitch rate -500~500, default 0
        """
        self.appkey = appkey
        self.token = token
        self.voice = voice
        self.format = format
        self.sample_rate = sample_rate
        self.volume = volume
        self.speech_rate = speech_rate
        self.pitch_rate = pitch_rate
    
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Synthesize text to audio using Aliyun TTS RESTful API
        
        Returns 16kHz, 16-bit PCM audio stream for THG model
        """
        if not text or not text.strip():
            return
        
        try:
            # Build POST request body
            request_body = {
                "appkey": self.appkey,
                "token": self.token,
                "text": text,
                "format": self.format,
                "voice": self.voice,
                "sample_rate": self.sample_rate,
                "volume": self.volume,
                "speech_rate": self.speech_rate,
                "pitch_rate": self.pitch_rate,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.GATEWAY_URL,
                    json=request_body,
                    headers={"Content-Type": "application/json"},
                    timeout=aiohttp.ClientTimeout(total=30),
                ) as response:
                    content_type = response.headers.get("Content-Type", "")
                    audio_data = await response.read()
                    is_audio = response.status == 200 and (
                        content_type.startswith("audio/") or "application/octet-stream" in content_type
                    )
                    if not is_audio and audio_data:
                        header = audio_data[:4]
                        is_audio = header in (b"RIFF", b"FORM")
                        if not is_audio and len(audio_data) > 2:
                            is_audio = (
                                (audio_data[0] == 0xFF and (audio_data[1] & 0xE0) == 0xE0)
                                or audio_data[:3] == b"ID3"
                            )
                    
                    if is_audio:
                        if len(audio_data) == 0:
                            print("[AliyunTTS] Warning: No audio data received")
                            return
                        
                        print(f"[AliyunTTS] Received {len(audio_data)} bytes of audio")
                        
                        # Process based on format
                        if self.format == "pcm":
                            # Raw PCM, yield directly in chunks
                            chunk_size = 3200  # 100ms at 16kHz, 16-bit
                            for i in range(0, len(audio_data), chunk_size):
                                yield audio_data[i:i + chunk_size]
                        
                        elif self.format == "wav":
                            # WAV format - skip 44-byte header to get PCM
                            if len(audio_data) > 44:
                                pcm_data = audio_data[44:]  # Skip WAV header
                                duration_sec = len(pcm_data) / (self.sample_rate * 2)
                                print(f"[AliyunTTS] Extracted {len(pcm_data)} bytes PCM ({duration_sec:.1f}s)")
                                
                                chunk_size = 3200
                                for i in range(0, len(pcm_data), chunk_size):
                                    yield pcm_data[i:i + chunk_size]
                            else:
                                print("[AliyunTTS] Warning: WAV data too short")
                        
                        elif self.format == "mp3":
                            # MP3 format - need to decode
                            if not MINIAUDIO_AVAILABLE:
                                print("[AliyunTTS] MP3 decode skipped: miniaudio not available")
                                return
                            try:
                                decoded = miniaudio.decode(audio_data, sample_rate=self.sample_rate, nchannels=1)
                                pcm_data = decoded.samples.tobytes()
                                duration_sec = len(pcm_data) / (self.sample_rate * 2)
                                print(f"[AliyunTTS] Decoded MP3 to {len(pcm_data)} bytes PCM ({duration_sec:.1f}s)")
                                
                                chunk_size = 3200
                                for i in range(0, len(pcm_data), chunk_size):
                                    yield pcm_data[i:i + chunk_size]
                            except Exception as decode_error:
                                print(f"[AliyunTTS] MP3 decode error: {decode_error}")
                    else:
                        # Error response
                        error_text = audio_data.decode("utf-8", errors="ignore")
                        print(f"[AliyunTTS] API Error: {error_text}")
                        
        except Exception as e:
            print(f"[AliyunTTS] Error: {e}")
            import traceback
            traceback.print_exc()


class StreamingCallback(ResultCallback):
    """Callback class for streaming TTS audio data"""
    
    def __init__(self, queue: asyncio.Queue, loop: asyncio.AbstractEventLoop):
        """
        Initialize streaming callback
        
        Args:
            queue: asyncio.Queue to put audio data chunks
            loop: asyncio event loop to schedule callbacks
        """
        self.queue = queue
        self.loop = loop
        self.error_occurred = False
        self.error_message = None
    
    def on_data(self, data: bytes) -> None:
        """Called when audio data is received (runs in WebSocket thread)"""
        if not self.error_occurred:
            # Schedule put operation in event loop (thread-safe)
            try:
                self.loop.call_soon_threadsafe(self._put_data, data)
            except Exception as e:
                print(f"[DashScopeTTS] Error scheduling data: {e}")
    
    def _put_data(self, data: bytes) -> None:
        """Put data in queue (runs in event loop thread)"""
        try:
            self.queue.put_nowait(data)
        except asyncio.QueueFull:
            print("[DashScopeTTS] Warning: Audio queue is full, dropping data")
    
    def on_complete(self) -> None:
        """Called when synthesis is complete (runs in WebSocket thread)"""
        if not self.error_occurred:
            try:
                self.loop.call_soon_threadsafe(self._put_complete)
            except Exception as e:
                print(f"[DashScopeTTS] Error scheduling complete: {e}")
    
    def _put_complete(self) -> None:
        """Put completion signal in queue (runs in event loop thread)"""
        try:
            self.queue.put_nowait(None)  # None signals completion
        except asyncio.QueueFull:
            pass
    
    def on_error(self, message) -> None:
        """Called when an error occurs (runs in WebSocket thread)"""
        self.error_occurred = True
        self.error_message = message
        try:
            error = Exception(f"TTS synthesis error: {message}")
            self.loop.call_soon_threadsafe(self._put_error, error)
        except Exception as e:
            print(f"[DashScopeTTS] Error scheduling error: {e}")
    
    def _put_error(self, error: Exception) -> None:
        """Put error in queue (runs in event loop thread)"""
        try:
            self.queue.put_nowait(error)
        except asyncio.QueueFull:
            pass
    
    def on_open(self) -> None:
        """Called when connection is opened"""
        pass
    
    def on_event(self, message: str) -> None:
        """Called when server sends event message"""
        pass
    
    def on_close(self) -> None:
        """Called when connection is closed"""
        pass


class DashScopeTTSService(TTSService):
    """DashScope CosyVoice TTS service implementation with streaming support"""
    
    def __init__(
        self,
        api_key: str,
        model: str = None,
        voice: str = "longanyang",
        sample_rate: int = 16000,
        format: str = "pcm",
    ):
        """
        Initialize DashScope TTS service with streaming support
        
        Args:
            api_key: DashScope API Key
            model: TTS model name, default "cosyvoice-v3-plus"
            voice: Voice name, default "longanyang"
            sample_rate: Sample rate, default 16000
            format: Audio format (pcm/wav/mp3), default "pcm" (recommended for best performance)
        """
        if not DASHSCOPE_TTS_AVAILABLE:
            raise ImportError("dashscope is not installed. Please run: pip install dashscope")
        
        import os
        dashscope.api_key = api_key
        self.model = model or os.getenv("DASHSCOPE_TTS_MODEL") or "cosyvoice-v3-plus"
        self.voice = voice
        
        # Auto-detect model based on voice ID
        # If voice is a cloned voice (cosyvoice-v3-plus-*), use cosyvoice-v3-plus model
        if self.voice and self.voice.startswith("cosyvoice-v3-plus-"):
            # This is a cloned voice or cosyvoice-v3-plus voice, requires cosyvoice-v3-plus model
            # Always switch to cosyvoice-v3-plus for cloned voices, even if model was explicitly set
            if self.model != "cosyvoice-v3-plus":
                original_model = self.model
                self.model = "cosyvoice-v3-plus"
                print(f"[DashScopeTTS] Auto-detected cosyvoice-v3-plus voice '{self.voice}', switching model from '{original_model}' to '{self.model}'")
        self.sample_rate = sample_rate
        self.format = format.lower()
        
        # Validate format
        if self.format not in ("mp3", "wav", "pcm"):
            raise ValueError(f"Unsupported format: {format}. Supported: mp3, wav, pcm")
    
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """
        Synthesize text to audio using DashScope CosyVoice TTS with streaming output
        
        Returns 16kHz, 16-bit PCM audio stream for THG model
        Uses one-way streaming call for lowest latency and real-time output
        """
        if not text or not text.strip():
            return
        
        if not DASHSCOPE_TTS_AVAILABLE or ResultCallback is None:
            print("[DashScopeTTS] DashScope not available, using fallback")
            fallback = MockTTSService()
            async for chunk in fallback.synthesize(text):
                yield chunk
            return
        
        try:
            # Create queue for receiving audio data chunks
            audio_queue = asyncio.Queue(maxsize=100)  # Limit queue size to prevent memory issues
            
            # Get current event loop for thread-safe callbacks
            loop = asyncio.get_event_loop()
            
            # Create callback for streaming
            callback = StreamingCallback(audio_queue, loop)
            
            # Map format string to AudioFormat enum
            format_map = {
                "pcm": AudioFormat.PCM_16000HZ_MONO_16BIT,
                "wav": AudioFormat.WAV_16000HZ_MONO_16BIT,
                "mp3": AudioFormat.MP3_16000HZ_MONO_128KBPS,
            }
            
            audio_format = format_map.get(self.format, AudioFormat.PCM_16000HZ_MONO_16BIT)
            
            # Create synthesizer with callback for streaming
            synthesizer = SpeechSynthesizer(
                model=self.model,
                voice=self.voice,
                format=audio_format,
                callback=callback
            )
            
            # Call TTS API in background thread (non-blocking)
            # The call method will return immediately, data comes through callback
            def _call_tts():
                try:
                    synthesizer.call(text)  # Returns None, data comes via callback
                except Exception as e:
                    # Put error in queue via callback's error handler
                    # The callback will handle thread-safe error propagation
                    print(f"[DashScopeTTS] TTS call error: {e}")
                    import traceback
                    traceback.print_exc()
                    # Trigger callback's on_error if possible
                    if hasattr(callback, 'on_error'):
                        callback.on_error(str(e))
            
            # Start TTS call in background thread
            loop = asyncio.get_event_loop()
            loop.run_in_executor(None, _call_tts)
            
            # Stream audio data from queue
            total_bytes = 0
            chunk_count = 0
            
            while True:
                try:
                    # Wait for data with timeout to avoid hanging
                    data = await asyncio.wait_for(audio_queue.get(), timeout=60.0)
                    
                    if data is None:
                        # Completion signal
                        print(f"[DashScopeTTS] Streaming complete: {chunk_count} chunks, {total_bytes} bytes")
                        break
                    
                    if isinstance(data, Exception):
                        # Error occurred
                        raise data
                    
                    # Yield audio data chunk immediately
                    if len(data) > 0:
                        total_bytes += len(data)
                        chunk_count += 1
                        
                        # For PCM format, yield directly
                        if self.format == "pcm":
                            yield data
                        # For WAV format, skip header on first chunk
                        elif self.format == "wav":
                            if chunk_count == 1 and len(data) > 44:
                                # Skip WAV header (44 bytes) from first chunk
                                yield data[44:]
                            else:
                                yield data
                        # For MP3 format, yield directly (streaming MP3 is supported by CosyVoice)
                        # Note: MP3 format works with streaming, but PCM is recommended for best performance
                        elif self.format == "mp3":
                            yield data
                        else:
                            yield data
                            
                except asyncio.TimeoutError:
                    print("[DashScopeTTS] Timeout waiting for audio data")
                    break
                except Exception as e:
                    print(f"[DashScopeTTS] Error in streaming: {e}")
                    import traceback
                    traceback.print_exc()
                    break
                    
        except Exception as e:
            print(f"[DashScopeTTS] Error: {e}")
            import traceback
            traceback.print_exc()
            # Fallback to MockTTSService
            fallback = MockTTSService()
            async for chunk in fallback.synthesize(text):
                yield chunk


class MockTTSService(TTSService):
    """Mock TTS 服务实现"""
    
    async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
        """模拟音频合成 - 生成非静音音频用于 THG 处理"""
        import asyncio
        import numpy as np
        import struct
        
        # 根据文本长度估算需要的音频时长（粗略估计：1 个中文字符 ≈ 0.3 秒）
        estimated_duration = len(text) * 0.3  # 秒
        # 确保至少有 3 秒的音频（THG 模型需要足够长的音频才能生成足够的帧）
        min_duration = 3.0
        target_duration = max(estimated_duration, min_duration)
        
        # 16kHz, 16-bit PCM
        sample_rate = 16000
        chunk_duration = 0.1  # 100ms per chunk
        chunk_samples = int(sample_rate * chunk_duration)  # 1600 samples per chunk
        num_chunks = max(int(target_duration / chunk_duration), 30)  # at least 30 chunks
        
        # Generate speech-like audio with varying frequencies to simulate speech patterns
        # Use multiple harmonics to make it more speech-like for THG processing
        base_frequency = 150  # Hz (typical male voice fundamental)
        amplitude = 6000  # Volume level for int16
        
        for i in range(num_chunks):
            await asyncio.sleep(0.005)  # 5ms delay, faster generation
            
            # Generate samples with speech-like characteristics
            t_start = i * chunk_samples
            t = np.arange(t_start, t_start + chunk_samples) / sample_rate
            
            # Simulate speech with varying pitch (prosody)
            pitch_variation = 1 + 0.2 * np.sin(2 * np.pi * 3 * t)  # slow pitch change
            freq = base_frequency * pitch_variation
            
            # Add harmonics for more natural speech sound
            samples = np.zeros(chunk_samples, dtype=np.float32)
            for harmonic in range(1, 5):  # First 4 harmonics
                harmonic_amp = amplitude / harmonic
                samples += harmonic_amp * np.sin(2 * np.pi * harmonic * freq * t)
            
            # Add some noise for naturalness
            noise = np.random.randn(chunk_samples) * 500
            samples = samples + noise
            
            # Clip and convert to int16
            samples = np.clip(samples, -32767, 32767).astype(np.int16)
            
            # Convert to bytes (raw PCM, not WAV format)
            # Frontend will handle playback via browser TTS as fallback
            audio_chunk = samples.tobytes()
            yield audio_chunk

