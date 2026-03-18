/** 录音组件 - 使用 AudioContext 实时转换为 PCM */
import { useState, useRef, useEffect } from "react";

interface AudioRecorderProps {
  onAudioChunk: (chunk: string) => void;
  onAudioEnd: () => void;
  onRecordingStart?: () => void;
  onVoiceActivity?: (isActive: boolean, energy: number) => void;
  disabled?: boolean;
}

// AudioContext 类型定义
declare global {
  interface Window {
    AudioContext: typeof AudioContext;
    webkitAudioContext: typeof AudioContext;
  }
}

// VAD 配置
const VAD_CONFIG = {
  ENERGY_THRESHOLD: 0.01, // 能量阈值，低于此值认为是静音
  SPEECH_THRESHOLD: 0.02, // 语音阈值，高于此值认为是说话
  SMOOTHING_FRAMES: 3, // 平滑帧数
};

// 音频数据处理类
class AudioDataProcessor {
  private buffer: Float32Array[] = [];
  private size = 0;
  inputSampleRate = 48000;
  private outputSampleRate = 16000;
  private energyHistory: number[] = [];
  private lastVoiceActive = false;

  clear() {
    this.buffer = [];
    this.size = 0;
  }

  input(data: Float32Array) {
    this.buffer.push(new Float32Array(data));
    this.size += data.length;
  }

  hasEnoughData(): boolean {
    // 减少发送阈值：约 50ms 的 16kHz 音频数据（从 1600 减少到 800）
    const MIN_SEND_THRESHOLD = 800;
    return this.size >= MIN_SEND_THRESHOLD;
  }

  /**
   * 检测语音活动（VAD）
   * 基于音频能量的简单 VAD 实现
   */
  detectVoiceActivity(data: Float32Array): { isActive: boolean; energy: number } {
    // 计算音频能量（RMS）
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      sum += data[i] * data[i];
    }
    const rms = Math.sqrt(sum / data.length);

    // 平滑能量值
    this.energyHistory.push(rms);
    if (this.energyHistory.length > VAD_CONFIG.SMOOTHING_FRAMES) {
      this.energyHistory.shift();
    }

    const avgEnergy =
      this.energyHistory.reduce((a, b) => a + b, 0) / this.energyHistory.length;

    // 使用滞后阈值避免频繁切换
    let isActive: boolean;
    if (this.lastVoiceActive) {
      // 当前已经在说话，使用较低阈值（更容易保持说话状态）
      isActive = avgEnergy > VAD_CONFIG.ENERGY_THRESHOLD;
    } else {
      // 当前静音，使用较高阈值（更难开始说话状态）
      isActive = avgEnergy > VAD_CONFIG.SPEECH_THRESHOLD;
    }

    this.lastVoiceActive = isActive;
    return { isActive, energy: avgEnergy };
  }

  resetVAD() {
    this.energyHistory = [];
    this.lastVoiceActive = false;
  }

  // 压缩/重采样：从 inputSampleRate 降到 outputSampleRate
  compress(): Float32Array {
    const data = new Float32Array(this.size);
    let offset = 0;
    for (let i = 0; i < this.buffer.length; i++) {
      const buffer = this.buffer[i];
      if (buffer) {
        data.set(buffer, offset);
        offset += buffer.length;
      }
    }

    const compression = Math.floor(this.inputSampleRate / this.outputSampleRate);
    const length = Math.floor(data.length / compression);
    const result = new Float32Array(length);
    let index = 0;
    let j = 0;

    while (index < length) {
      result[index] = data[j] || 0;
      j += compression;
      index++;
    }
    return result;
  }

  // 编码为 PCM16
  encodePCM(): ArrayBuffer {
    const bytes = this.compress();
    const dataLength = bytes.length * 2; // 16bit = 2 bytes per sample
    const buffer = new ArrayBuffer(dataLength);
    const dataView = new DataView(buffer);
    let offset = 0;

    for (let i = 0; i < bytes.length; i++, offset += 2) {
      const s = Math.max(-1, Math.min(1, bytes[i] || 0));
      // Convert float [-1, 1] to int16
      dataView.setInt16(offset, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    }
    return buffer;
  }
}

export function AudioRecorder({ onAudioChunk, onAudioEnd, onRecordingStart, onVoiceActivity, disabled }: AudioRecorderProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [recordingTime, setRecordingTime] = useState(0);
  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioInputRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const scriptProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const timerRef = useRef<number | null>(null);
  const audioProcessorRef = useRef(new AudioDataProcessor());
  const isRecordingRef = useRef(false); // 用于在回调中检查状态

  useEffect(() => {
    return () => {
      // 清理函数
      cleanup();
    };
  }, []);

  const cleanup = () => {
    // 停止计时器
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }

    // 断开音频处理节点
    if (scriptProcessorRef.current) {
      scriptProcessorRef.current.disconnect();
      scriptProcessorRef.current = null;
    }
    if (audioInputRef.current) {
      audioInputRef.current.disconnect();
      audioInputRef.current = null;
    }

    // 关闭 AudioContext
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {
        console.warn("关闭 AudioContext 失败");
      });
      audioContextRef.current = null;
    }

    // 停止媒体流
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop());
      streamRef.current = null;
    }

    // 清理音频处理器
    audioProcessorRef.current.clear();
    audioProcessorRef.current.resetVAD();
  };

  const sendPCMData = () => {
    const processor = audioProcessorRef.current;
    if (!processor.hasEnoughData()) {
      return;
    }

    try {
      const pcmBuffer = processor.encodePCM();
      if (pcmBuffer.byteLength === 0) {
        processor.clear();
        return;
      }

      // 转换为 base64
      const uint8Array = new Uint8Array(pcmBuffer);
      const binaryString = String.fromCharCode.apply(null, Array.from(uint8Array));
      const base64 = btoa(binaryString);

      // 发送 PCM 数据
      onAudioChunk(base64);
      processor.clear();
    } catch (error) {
      console.error("转换 PCM 数据失败:", error);
      processor.clear();
    }
  };

  const startRecording = async () => {
    try {
      // 请求麦克风权限
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      streamRef.current = stream;

      // 创建 AudioContext
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      const audioContext = new AudioContextClass();
      audioContextRef.current = audioContext;

      // 设置采样率
      audioProcessorRef.current.inputSampleRate = audioContext.sampleRate;

      // 创建音频输入
      const audioInput = audioContext.createMediaStreamSource(stream);
      audioInputRef.current = audioInput;

      // 创建 ScriptProcessor（用于实时处理音频数据）
      const scriptProcessor = audioContext.createScriptProcessor(4096, 1, 1);
      scriptProcessorRef.current = scriptProcessor;

      // 处理音频数据
      scriptProcessor.onaudioprocess = (e) => {
        if (!isRecordingRef.current) return;

        // 获取输入数据（Float32Array, 范围 [-1, 1]）
        const inputBuffer = e.inputBuffer.getChannelData(0);

        // VAD 检测
        if (onVoiceActivity) {
          const vadResult = audioProcessorRef.current.detectVoiceActivity(inputBuffer);
          onVoiceActivity(vadResult.isActive, vadResult.energy);
        }

        // 输入到音频处理器
        audioProcessorRef.current.input(inputBuffer);

        // 当累积足够数据时发送
        if (audioProcessorRef.current.hasEnoughData()) {
          sendPCMData();
        }
      };

      // 连接节点
      audioInput.connect(scriptProcessor);
      scriptProcessor.connect(audioContext.destination);

      isRecordingRef.current = true;
      setIsRecording(true);
      setRecordingTime(0);

      // 通知开始录音
      if (onRecordingStart) {
        onRecordingStart();
      }

      // 启动计时器
      timerRef.current = window.setInterval(() => {
        setRecordingTime((prev) => prev + 1);
      }, 1000);
    } catch (error) {
      console.error("启动录音失败:", error);
      alert("无法访问麦克风，请检查权限设置");
      cleanup();
    }
  };

  const stopRecording = () => {
    if (isRecordingRef.current) {
      isRecordingRef.current = false;
      
      // 发送剩余数据
      if (audioProcessorRef.current.hasEnoughData()) {
        sendPCMData();
      }

      setIsRecording(false);
      setRecordingTime(0);

      // 清理资源
      cleanup();

      // 通知音频结束
      setTimeout(() => {
        onAudioEnd();
      }, 100);
    }
  };

  const formatTime = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, "0")}:${secs.toString().padStart(2, "0")}`;
  };

  const handleClick = () => {
    if (isRecording) {
      stopRecording();
    } else {
      startRecording();
    }
  };

  return (
    <div className="audio-recorder">
      <button
        className={`record-button ${isRecording ? "recording" : ""}`}
        onClick={handleClick}
        disabled={disabled || false}
      >
        {isRecording ? "停止录音" : "开始录音"}
      </button>
      {isRecording && (
        <div className="recording-time">{formatTime(recordingTime)}</div>
      )}
    </div>
  );
}
