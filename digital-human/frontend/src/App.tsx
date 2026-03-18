/** 主应用组件 */
import { useCallback, useEffect, useRef, useState } from "react";
import "./App.css";
import { AudioRecorder } from "./components/AudioRecorder";
import { ProcessSteps } from "./components/ProcessSteps";
import { StatusPanel } from "./components/StatusPanel";
import type { TingwuSegment } from "./utils/tingwuMessageProcessor";
import { processTingwuMessage } from "./utils/tingwuMessageProcessor";
import { VideoPlayer } from "./components/VideoPlayer";
import { useWebSocket } from "./hooks/useWebSocket";
import type { TingwuResultMessage, WebSocketMessage, EvaluationResult } from "./types";
import { EvaluationModal } from "./components/EvaluationModal";
import { uploadResume } from "./services/resume";

type BufferedVideoFrame = {
  data: string;
  index: number;
  timestampMs?: number;
};

const TARGET_FPS = 20;
const FRAME_INTERVAL_MS = 1000 / TARGET_FPS;
const START_BUFFER_MS = 600;
const MIN_BUFFER_FRAMES = Math.ceil((START_BUFFER_MS / 1000) * TARGET_FPS);
const MAX_BUFFER_WAIT_MS = 2000;

// 同步微调偏移（毫秒）- 可根据实际效果调整
// 正值：视频提前播放；负值：视频延后播放
const SYNC_OFFSET_MS = 0;

// 最大允许的帧延迟（毫秒）- 超过此值的旧帧将被丢弃
const MAX_FRAME_LAG_MS = 150;

// 流式音频配置
const STREAMING_AUDIO_CONFIG = {
  SAMPLE_RATE: 16000, // 16kHz
  BITS_PER_SAMPLE: 16,
  CHANNELS: 1,
  MIN_BUFFER_CHUNKS: 2, // 开始播放前最少缓冲的音频块数
};

function App() {
  const { isConnected, send, on, off } = useWebSocket();
  const { isConnected: isTingwuConnected, send: sendTingwu, on: onTingwu, off: offTingwu } = useWebSocket("ws://localhost:8000/api/tingwu/ws");
  const [messages, setMessages] = useState<WebSocketMessage[]>([]);
  const [lastVideoFrame, setLastVideoFrame] = useState<string | null>(null);
  const [videoFrameCount, setVideoFrameCount] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [tingwuSegments, setTingwuSegments] = useState<TingwuSegment[]>([]);
  const [inputText, setInputText] = useState<string>("");
  const [llmQaEnabled, setLlmQaEnabled] = useState<boolean>(false);  // LLM实时问答开关
  const [interviewState, setInterviewState] = useState<"idle" | "in_progress" | "ended">("idle");  // 面试状态
  const [evaluationResult, setEvaluationResult] = useState<EvaluationResult | null>(null);  // 评价结果
  const [showEvaluationModal, setShowEvaluationModal] = useState(false);  // 是否显示评价模态框
  const [isGeneratingEvaluation, setIsGeneratingEvaluation] = useState(false);  // 是否正在生成评价
  const [resumeId, setResumeId] = useState<string | null>(null);
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [resumeFileName, setResumeFileName] = useState<string>("");
  const [resumeStatus, setResumeStatus] = useState<string>("待读取您的简历，请上传");
  const [resumeError, setResumeError] = useState<string>("");
  const [isUploadingResume, setIsUploadingResume] = useState(false);
  const [jobTitle, setJobTitle] = useState<string>("");
  const [jobStatus, setJobStatus] = useState<string>("请输入目标岗位名称");
  const [jobError, setJobError] = useState<string>("");
  const [isGeneratingJob, setIsGeneratingJob] = useState(false);

  const lastVideoFrameRef = useRef<string | null>(null);
  const videoFrameCountRef = useRef(0);
  const latestLLMTextRef = useRef<string>("");
  const frameUpdateScheduledRef = useRef(false);
  const videoFrameQueueRef = useRef<BufferedVideoFrame[]>([]);
  const nextVideoFrameIndexRef = useRef(0);
  const playbackRafRef = useRef<number | null>(null);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const audioUrlRef = useRef<string | null>(null);
  const audioReadyRef = useRef(false);
  const audioStartedRef = useRef(false);
  const audioEndedRef = useRef(false);
  const syncActiveRef = useRef(false);
  const fallbackModeRef = useRef(false);
  const bufferTimeoutRef = useRef<number | null>(null);
  const videoTimeOffsetMsRef = useRef(0);

  // 流式音频播放相关
  const audioContextRef = useRef<AudioContext | null>(null);
  const audioBufferQueueRef = useRef<ArrayBuffer[]>([]);
  const isStreamingAudioRef = useRef(false);
  const nextPlayTimeRef = useRef(0);
  // 流式音频同步：记录 AudioContext 开始播放时的 currentTime，用于对齐视频帧时间戳
  const streamingAudioStartTimeRef = useRef<number>(0);

  // 打断相关
  const isDigitalHumanSpeakingRef = useRef(false);
  const userVoiceActiveRef = useRef(false);
  const resumeSentRef = useRef<string | null>(null);
  const resumeFileInputRef = useRef<HTMLInputElement | null>(null);

  const handleResumeFileChange = useCallback((event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) {
      return;
    }

    const isPdf = file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf");
    if (!isPdf) {
      setResumeError("仅支持 PDF 文件");
      setResumeFile(null);
      setResumeFileName("");
      return;
    }

    setResumeFile(file);
    setResumeFileName(file.name);
    setResumeError("");
    setResumeStatus("待读取您的简历，请上传");
  }, []);

  const handleResumeUpload = useCallback(async () => {
    if (!resumeFile) {
      setResumeError("请先选择 PDF 简历文件");
      return;
    }

    setIsUploadingResume(true);
    setResumeError("");
    setResumeStatus("正在读取并分析您的简历");

    try {
      const result = await uploadResume(resumeFile);
      setResumeId(result.resume_id);
      setResumeStatus("已读取您的简历");
    } catch (error) {
      const message = error instanceof Error ? error.message : "简历上传失败";
      setResumeError(message);
      setResumeStatus("");
    } finally {
      setIsUploadingResume(false);
    }
  }, [resumeFile]);

  const handleResumeClear = useCallback(() => {
    setResumeId(null);
    setResumeFile(null);
    setResumeFileName("");
    setResumeStatus("待读取您的简历，请上传");
    setResumeError("");
    if (resumeFileInputRef.current) {
      resumeFileInputRef.current.value = "";
    }
  }, []);

  const handleJobGenerate = useCallback(() => {
    const title = jobTitle.trim();
    if (!title) {
      setJobError("请填写目标岗位名称");
      return;
    }

    if (!isConnected) {
      setJobError("WebSocket 未连接，无法生成岗位JD");
      return;
    }

    setIsGeneratingJob(true);
    setJobError("");
    setJobStatus("正在生成岗位JD...");
    send({ type: "job_context", job_title: title });
  }, [jobTitle, isConnected, send]);

  const handleJobClear = useCallback(() => {
    setJobTitle("");
    setJobStatus("请输入目标岗位名称");
    setJobError("");
    if (isConnected) {
      send({ type: "job_context", job_title: "" });
    }
  }, [isConnected, send]);

  const speakFallback = useCallback((text: string) => {
    if (!text) return;
    if (!("speechSynthesis" in window)) return;

    try {
      window.speechSynthesis.cancel();
      const utterance = new SpeechSynthesisUtterance(text);
      utterance.lang = "zh-CN";
      window.speechSynthesis.speak(utterance);
    } catch (e) {
      console.warn("speechSynthesis 播放失败:", e);
    }
  }, []);

  // 初始化流式音频 AudioContext
  const initStreamingAudio = useCallback(() => {
    if (!audioContextRef.current) {
      const AudioContextClass = window.AudioContext || window.webkitAudioContext;
      audioContextRef.current = new AudioContextClass({
        sampleRate: STREAMING_AUDIO_CONFIG.SAMPLE_RATE,
      });
    }
    audioBufferQueueRef.current = [];
    isStreamingAudioRef.current = false;
    nextPlayTimeRef.current = 0;
    streamingAudioStartTimeRef.current = 0;
  }, []);

  // 播放流式音频块
  const playStreamingAudioChunk = useCallback(async (pcmData: ArrayBuffer) => {
    if (!audioContextRef.current) {
      initStreamingAudio();
    }

    const ctx = audioContextRef.current;
    if (!ctx) return;

    // 确保 AudioContext 在运行
    if (ctx.state === "suspended") {
      await ctx.resume();
    }

    // 将 PCM 数据转换为 AudioBuffer
    const samples = new Int16Array(pcmData);
    const float32Array = new Float32Array(samples.length);
    for (let i = 0; i < samples.length; i++) {
      float32Array[i] = samples[i] / 32768.0;
    }

    const audioBuffer = ctx.createBuffer(
      STREAMING_AUDIO_CONFIG.CHANNELS,
      float32Array.length,
      STREAMING_AUDIO_CONFIG.SAMPLE_RATE
    );
    audioBuffer.getChannelData(0).set(float32Array);

    // 创建音频源并播放
    const source = ctx.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(ctx.destination);

    // 计算播放时间
    const currentTime = ctx.currentTime;
    const startTime = Math.max(nextPlayTimeRef.current, currentTime);

    // 记录流式音频的起始时间，用于视频同步（仅首块时设置）
    if (streamingAudioStartTimeRef.current === 0) {
      streamingAudioStartTimeRef.current = startTime;
      isStreamingAudioRef.current = true;
    }

    source.start(startTime);
    nextPlayTimeRef.current = startTime + audioBuffer.duration;

    isDigitalHumanSpeakingRef.current = true;

    source.onended = () => {
      // 检查队列中是否还有待播放的内容
      if (audioBufferQueueRef.current.length === 0) {
        // 所有音频播放完毕
        if (nextPlayTimeRef.current <= ctx.currentTime + 0.1) {
          isDigitalHumanSpeakingRef.current = false;
        }
      }
    };
  }, [initStreamingAudio]);

  // 停止流式音频播放
  const stopStreamingAudio = useCallback(() => {
    // 停止视频同步循环
    if (playbackRafRef.current !== null) {
      cancelAnimationFrame(playbackRafRef.current);
      playbackRafRef.current = null;
    }
    syncActiveRef.current = false;
    if (audioContextRef.current) {
      audioContextRef.current.close();
      audioContextRef.current = null;
    }
    audioBufferQueueRef.current = [];
    isStreamingAudioRef.current = false;
    nextPlayTimeRef.current = 0;
    streamingAudioStartTimeRef.current = 0;
    isDigitalHumanSpeakingRef.current = false;
  }, []);

  // 发送打断信号
  const sendInterrupt = useCallback(() => {
    if (isDigitalHumanSpeakingRef.current) {
      console.log("[Interrupt] 发送打断信号");
      send({ type: "interrupt" });
      stopStreamingAudio();
      isDigitalHumanSpeakingRef.current = false;
    }
  }, [send, stopStreamingAudio]);

  // 使用 requestAnimationFrame 平滑更新视频帧
  const scheduleUiUpdate = useCallback(() => {
    if (frameUpdateScheduledRef.current) {
      return;
    }
    frameUpdateScheduledRef.current = true;
    requestAnimationFrame(() => {
      frameUpdateScheduledRef.current = false;
      setVideoFrameCount(videoFrameCountRef.current);
      if (lastVideoFrameRef.current !== null) {
        setLastVideoFrame(lastVideoFrameRef.current);
      }
    });
  }, []);

  const clearAudio = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.src = "";
      audioRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = null;
    }
  }, []);

  const stopPlaybackLoop = useCallback(() => {
    if (playbackRafRef.current !== null) {
      cancelAnimationFrame(playbackRafRef.current);
      playbackRafRef.current = null;
    }
    syncActiveRef.current = false;
  }, []);

  const stopPlaybackOnly = useCallback(() => {
    // Only stop audio playback, keep video frames
    stopPlaybackLoop();
    if (bufferTimeoutRef.current !== null) {
      window.clearTimeout(bufferTimeoutRef.current);
      bufferTimeoutRef.current = null;
    }
    clearAudio();
    audioReadyRef.current = false;
    audioStartedRef.current = false;
    audioEndedRef.current = false;
    syncActiveRef.current = false;
    fallbackModeRef.current = false;
    videoTimeOffsetMsRef.current = 0;
    videoFrameQueueRef.current = [];
    nextVideoFrameIndexRef.current = 0;
    streamingAudioStartTimeRef.current = 0;
    // Do not clear videoFrameCountRef and lastVideoFrameRef - keep video visible
  }, [clearAudio, stopPlaybackLoop]);

  const resetPlaybackState = useCallback(() => {
    stopPlaybackLoop();
    if (bufferTimeoutRef.current !== null) {
      window.clearTimeout(bufferTimeoutRef.current);
      bufferTimeoutRef.current = null;
    }
    clearAudio();
    audioReadyRef.current = false;
    audioStartedRef.current = false;
    audioEndedRef.current = false;
    syncActiveRef.current = false;
    fallbackModeRef.current = false;
    videoTimeOffsetMsRef.current = 0;
    videoFrameQueueRef.current = [];
    nextVideoFrameIndexRef.current = 0;
    videoFrameCountRef.current = 0;
    lastVideoFrameRef.current = null;
    streamingAudioStartTimeRef.current = 0;
  }, [clearAudio, stopPlaybackLoop]);

  const startPlaybackLoop = useCallback(() => {
    if (playbackRafRef.current !== null) {
      return;
    }

    const tick = () => {
      if (!syncActiveRef.current) {
        playbackRafRef.current = null;
        return;
      }

      let audioTimeMs: number;

      const audio = audioRef.current;
      const ctx = audioContextRef.current;

      if (audio) {
        // HTML Audio 模式（非流式 TTS）
        if (audio.ended) {
          syncActiveRef.current = false;
          playbackRafRef.current = null;
          return;
        }
        audioTimeMs = audio.currentTime * 1000 + SYNC_OFFSET_MS;
      } else if (ctx && isStreamingAudioRef.current && streamingAudioStartTimeRef.current > 0) {
        // 流式 AudioContext 模式：用 currentTime - 起始时间 计算已播放进度
        audioTimeMs = (ctx.currentTime - streamingAudioStartTimeRef.current) * 1000 + SYNC_OFFSET_MS;
        // 音频结束且队列清空时停止循环
        if (!isDigitalHumanSpeakingRef.current && videoFrameQueueRef.current.length === 0) {
          syncActiveRef.current = false;
          playbackRafRef.current = null;
          return;
        }
      } else {
        // 没有有效音频源，停止循环
        playbackRafRef.current = null;
        return;
      }

      const queue = videoFrameQueueRef.current;
      let updated = false;

      // 丢弃过时的帧，避免累积延迟
      while (queue.length > 1) {
        const frame = queue[0];
        const frameTimeMs = (frame.timestampMs ?? frame.index * FRAME_INTERVAL_MS) - videoTimeOffsetMsRef.current;
        // 如果帧已经超过最大允许延迟，丢弃它
        if (frameTimeMs < audioTimeMs - MAX_FRAME_LAG_MS) {
          queue.shift();
          continue;
        }
        break;
      }

      // 正常同步逻辑
      while (queue.length > 0) {
        const frame = queue[0];
        const frameTimeMs = (frame.timestampMs ?? frame.index * FRAME_INTERVAL_MS) - videoTimeOffsetMsRef.current;
        if (frameTimeMs <= audioTimeMs) {
          lastVideoFrameRef.current = frame.data;
          queue.shift();
          updated = true;
          continue;
        }
        break;
      }

      if (updated) {
        scheduleUiUpdate();
      }

      playbackRafRef.current = requestAnimationFrame(tick);
    };

    playbackRafRef.current = requestAnimationFrame(tick);
  }, [scheduleUiUpdate]);

  const maybeStartSyncedPlayback = useCallback((forceStart: boolean = false) => {
    if (audioStartedRef.current || audioEndedRef.current || fallbackModeRef.current) {
      return;
    }
    const audio = audioRef.current;
    if (!audio || !audioReadyRef.current) {
      return;
    }

    const bufferedFrames = videoFrameQueueRef.current.length;
    if (!forceStart && bufferedFrames < MIN_BUFFER_FRAMES) {
      if (bufferTimeoutRef.current === null) {
        bufferTimeoutRef.current = window.setTimeout(() => {
          bufferTimeoutRef.current = null;
          maybeStartSyncedPlayback(true);
        }, MAX_BUFFER_WAIT_MS);
      }
      return;
    }

    if (bufferTimeoutRef.current !== null) {
      window.clearTimeout(bufferTimeoutRef.current);
      bufferTimeoutRef.current = null;
    }

    const firstFrame = videoFrameQueueRef.current[0];
    if (firstFrame && typeof firstFrame.timestampMs === "number") {
      // Align playback so the first buffered frame maps to audio time 0.
      videoTimeOffsetMsRef.current = firstFrame.timestampMs;
    } else {
      videoTimeOffsetMsRef.current = 0;
    }

    audioStartedRef.current = true;
    syncActiveRef.current = true;
    audio.play()
      .then(() => {
        startPlaybackLoop();
      })
      .catch((e) => {
        console.warn("Audio play() failed:", e);
        syncActiveRef.current = false;
        audioStartedRef.current = false;
        fallbackModeRef.current = true;
        speakFallback(latestLLMTextRef.current);
      });
  }, [speakFallback, startPlaybackLoop]);

  // 流式 TTS 模式下启动视频同步循环（对应 AudioContext 时钟源）
  const maybeStartStreamingSyncedPlayback = useCallback(() => {
    if (playbackRafRef.current !== null) return; // 循环已在运行
    if (!isStreamingAudioRef.current) return;
    if (streamingAudioStartTimeRef.current === 0) return; // 音频尚未开始
    if (videoFrameQueueRef.current.length === 0) return; // 暂无帧

    // 用第一帧的 timestamp_ms 做偏移，与 HTML Audio 路径保持一致
    if (videoTimeOffsetMsRef.current === 0) {
      const firstFrame = videoFrameQueueRef.current[0];
      if (firstFrame && typeof firstFrame.timestampMs === "number") {
        videoTimeOffsetMsRef.current = firstFrame.timestampMs;
      }
    }

    syncActiveRef.current = true;
    startPlaybackLoop();
  }, [startPlaybackLoop]);

  // 处理 WebSocket 消息
  useEffect(() => {

    const handleStatus = (msg: WebSocketMessage) => {
      setMessages((prev) => [...prev, msg]);
      setIsProcessing(true);
    };

    const handleASRResult = (msg: WebSocketMessage) => {
      setMessages((prev) => [...prev, msg]);
    };

    const handleLLMResult = (msg: WebSocketMessage) => {
      setMessages((prev) => [...prev, msg]);
      if (msg.text) {
        latestLLMTextRef.current = msg.text;
      }
    };

    const handleVideoChunk = (msg: WebSocketMessage) => {
      if (!msg.data) {
        return;
      }

      // 检查面试状态
      if (interviewState === "ended") {
        return;
      }

      videoFrameCountRef.current += 1;
      scheduleUiUpdate();

      if (audioEndedRef.current) {
        return;
      }

      // fallback 模式：直接显示
      if (fallbackModeRef.current) {
        lastVideoFrameRef.current = msg.data;
        scheduleUiUpdate();
        return;
      }

      const timestampMs = typeof msg.timestamp_ms === "number" ? msg.timestamp_ms : undefined;
      let frameIndex = nextVideoFrameIndexRef.current;
      if (typeof msg.frame_index === "number") {
        frameIndex = msg.frame_index;
        nextVideoFrameIndexRef.current = Math.max(nextVideoFrameIndexRef.current, msg.frame_index + 1);
      } else {
        nextVideoFrameIndexRef.current += 1;
      }

      if (audioRef.current) {
        // HTML Audio 模式（非流式 TTS）：入队，等 HTML Audio 播放时同步显示
        videoFrameQueueRef.current.push({ data: msg.data, index: frameIndex, timestampMs });
        maybeStartSyncedPlayback();
      } else if (isStreamingAudioRef.current) {
        // 流式 AudioContext 模式：入队，由 AudioContext 时钟驱动同步显示
        videoFrameQueueRef.current.push({ data: msg.data, index: frameIndex, timestampMs });
        maybeStartStreamingSyncedPlayback();
      } else {
        // 尚无音频（极少见的竞态情况）：直接显示
        lastVideoFrameRef.current = msg.data;
        scheduleUiUpdate();
      }
    };

    const handleTTSAudio = (msg: WebSocketMessage) => {
      if (!msg.data) {
        return;
      }

      try {
        if (bufferTimeoutRef.current !== null) {
          window.clearTimeout(bufferTimeoutRef.current);
          bufferTimeoutRef.current = null;
        }
        clearAudio();
        audioReadyRef.current = false;
        audioStartedRef.current = false;
        audioEndedRef.current = false;
        syncActiveRef.current = false;
        fallbackModeRef.current = false;
        videoTimeOffsetMsRef.current = 0;

        // Decode base64 audio data
        const audioData = atob(msg.data);
        const audioBytes = new Uint8Array(audioData.length);
        for (let i = 0; i < audioData.length; i++) {
          audioBytes[i] = audioData.charCodeAt(i);
        }

        // Check audio format by header
        const hasWavHeader = audioBytes.length > 4 && 
          audioBytes[0] === 0x52 && audioBytes[1] === 0x49 && 
          audioBytes[2] === 0x46 && audioBytes[3] === 0x46;
        
        const hasMp3Header = audioBytes.length > 2 && 
          ((audioBytes[0] === 0xFF && (audioBytes[1] & 0xE0) === 0xE0) ||  // MP3 frame sync
           (audioBytes[0] === 0x49 && audioBytes[1] === 0x44 && audioBytes[2] === 0x33));  // ID3 tag
        
        let blob: Blob;
        if (hasWavHeader || hasMp3Header) {
          // Real audio format (WAV or MP3)
          const mimeType = hasWavHeader ? "audio/wav" : "audio/mpeg";
          blob = new Blob([audioBytes], { type: mimeType });
        } else {
          // Raw PCM data - convert to WAV for playback
          // PCM format: 16kHz, mono, 16-bit signed little-endian
          const sampleRate = 16000;
          const numChannels = 1;
          const bitsPerSample = 16;
          const byteRate = sampleRate * numChannels * bitsPerSample / 8;
          const blockAlign = numChannels * bitsPerSample / 8;
          const dataSize = audioBytes.length;
          
          // Create WAV header (44 bytes)
          const wavHeader = new Uint8Array(44);
          
          // Helper to write string
          const writeString = (offset: number, str: string) => {
            for (let i = 0; i < str.length; i++) {
              wavHeader[offset + i] = str.charCodeAt(i);
            }
          };
          
          // Helper to write 32-bit little-endian
          const writeUint32LE = (offset: number, value: number) => {
            wavHeader[offset] = value & 0xff;
            wavHeader[offset + 1] = (value >> 8) & 0xff;
            wavHeader[offset + 2] = (value >> 16) & 0xff;
            wavHeader[offset + 3] = (value >> 24) & 0xff;
          };
          
          // Helper to write 16-bit little-endian
          const writeUint16LE = (offset: number, value: number) => {
            wavHeader[offset] = value & 0xff;
            wavHeader[offset + 1] = (value >> 8) & 0xff;
          };
          
          // RIFF header
          writeString(0, 'RIFF');
          writeUint32LE(4, 36 + dataSize);  // file size - 8
          writeString(8, 'WAVE');
          
          // fmt sub-chunk
          writeString(12, 'fmt ');
          writeUint32LE(16, 16);  // sub-chunk size (16 for PCM)
          writeUint16LE(20, 1);   // audio format (1 = PCM)
          writeUint16LE(22, numChannels);
          writeUint32LE(24, sampleRate);
          writeUint32LE(28, byteRate);
          writeUint16LE(32, blockAlign);
          writeUint16LE(34, bitsPerSample);
          
          // data sub-chunk
          writeString(36, 'data');
          writeUint32LE(40, dataSize);
          
          // Combine header and PCM data
          const wavBytes = new Uint8Array(44 + audioBytes.length);
          wavBytes.set(wavHeader, 0);
          wavBytes.set(audioBytes, 44);
          
          console.log(`[TTS] Playing PCM audio: ${audioBytes.length} bytes, ${audioBytes.length / 32000}s`);

          blob = new Blob([wavBytes], { type: "audio/wav" });
        }

        const url = URL.createObjectURL(blob);
        const audio = new Audio();
        audio.preload = "auto";

        audio.onloadedmetadata = () => {
          audioReadyRef.current = true;
          maybeStartSyncedPlayback();
        };

        audio.oncanplay = () => {
          audioReadyRef.current = true;
          maybeStartSyncedPlayback();
        };

        audio.onended = () => {
          audioEndedRef.current = true;
          audioStartedRef.current = false;
          stopPlaybackLoop();
          clearAudio();
        };

        audio.onerror = (e) => {
          console.warn("Audio playback failed:", e);
          audioEndedRef.current = true;
          audioStartedRef.current = false;
          audioReadyRef.current = false;
          fallbackModeRef.current = true;
          stopPlaybackLoop();
          clearAudio();
          speakFallback(latestLLMTextRef.current);
        };

        audio.src = url;
        audioRef.current = audio;
        audioUrlRef.current = url;
        maybeStartSyncedPlayback();
      } catch (e) {
        console.error("TTS audio processing failed:", e);
        fallbackModeRef.current = true;
        speakFallback(latestLLMTextRef.current);
      }
    };

    const handleComplete = (msg: WebSocketMessage) => {
      setMessages((prev) => [...prev, msg]);
      setIsProcessing(false);
      isDigitalHumanSpeakingRef.current = false;
    };

    const handleError = (msg: WebSocketMessage) => {
      setMessages((prev) => [...prev, msg]);
      setIsProcessing(false);
      isDigitalHumanSpeakingRef.current = false;
      setIsGeneratingJob(false);
    };

    // 处理流式 TTS 音频块
    const handleTTSAudioChunk = async (msg: WebSocketMessage) => {
      // 检查面试状态
      if (interviewState === "ended") {
        return;
      }

      if (msg.is_final) {
        // 最后一个块，不需要处理数据
        console.log("[TTS Streaming] 收到最终标记");
        return;
      }

      if (!msg.data) {
        return;
      }

      try {
        // 解码 base64 音频数据
        const audioData = atob(msg.data);
        const audioBytes = new Uint8Array(audioData.length);
        for (let i = 0; i < audioData.length; i++) {
          audioBytes[i] = audioData.charCodeAt(i);
        }

        // 播放流式音频
        await playStreamingAudioChunk(audioBytes.buffer);

        if (msg.is_first) {
          console.log("[TTS Streaming] 开始流式播放");
          isDigitalHumanSpeakingRef.current = true;
          // 若视频帧已提前到达队列，现在可以启动同步循环
          maybeStartStreamingSyncedPlayback();
        }
      } catch (e) {
        console.warn("[TTS Streaming] 处理音频块失败:", e);
      }
    };

    // 处理打断响应
    const handleInterrupted = (msg: WebSocketMessage) => {
      console.log("[Interrupt] 收到打断确认:", msg.message);
      setIsProcessing(false);
      isDigitalHumanSpeakingRef.current = false;
      stopStreamingAudio();
      // Use stopPlaybackOnly instead of resetPlaybackState to keep video visible
      stopPlaybackOnly();
    };

    // 处理面试结束消息
    const handleInterviewEnded = (msg: WebSocketMessage) => {
      console.log("[Interview] 面试已结束:", msg.message);
      setInterviewState("ended");
      setIsGeneratingEvaluation(true);
      // 停止所有音频和视频播放
      stopStreamingAudio();
      stopPlaybackOnly();
      setIsProcessing(false);
      isDigitalHumanSpeakingRef.current = false;
    };

    // 处理评价结果消息
    const handleEvaluationResult = (msg: WebSocketMessage) => {
      console.log("[Evaluation] 收到评价结果");
      const evalMsg = msg as any;
      if (evalMsg.data) {
        setEvaluationResult(evalMsg.data);
        setIsGeneratingEvaluation(false);
        setShowEvaluationModal(true);
      }
    };

    const handleResumeContext = (msg: WebSocketMessage) => {
      if (msg.message) {
        setResumeStatus(msg.message);
      }
    };

    const handleJobContext = (msg: WebSocketMessage) => {
      if (msg.message) {
        setJobStatus(msg.message);
        setIsGeneratingJob(false);
      }
    };

    // 注册消息处理器
    on("status", handleStatus);
    on("asr_result", handleASRResult);
    on("llm_result", handleLLMResult);
    on("video_chunk", handleVideoChunk);
    on("tts_audio", handleTTSAudio);
    on("tts_audio_chunk", handleTTSAudioChunk);
    on("complete", handleComplete);
    on("error", handleError);
    on("interrupted", handleInterrupted);
    on("interview_ended", handleInterviewEnded);
    on("evaluation_result", handleEvaluationResult);
    on("resume_context", handleResumeContext);
    on("job_context", handleJobContext);

    // 清理函数
    return () => {
      off("status", handleStatus);
      off("asr_result", handleASRResult);
      off("llm_result", handleLLMResult);
      off("video_chunk", handleVideoChunk);
      off("tts_audio", handleTTSAudio);
      off("tts_audio_chunk", handleTTSAudioChunk);
      off("complete", handleComplete);
      off("error", handleError);
      off("interrupted", handleInterrupted);
      off("interview_ended", handleInterviewEnded);
      off("evaluation_result", handleEvaluationResult);
      off("resume_context", handleResumeContext);
      off("job_context", handleJobContext);
    };
  }, [clearAudio, maybeStartSyncedPlayback, maybeStartStreamingSyncedPlayback, off, on, playStreamingAudioChunk, resetPlaybackState, scheduleUiUpdate, speakFallback, stopPlaybackLoop, stopPlaybackOnly, stopStreamingAudio, interviewState]);

  useEffect(() => {
    if (!isConnected) {
      return;
    }

    if (resumeId && resumeSentRef.current !== resumeId) {
      send({ type: "resume_context", resume_id: resumeId });
      resumeSentRef.current = resumeId;
      return;
    }

    if (!resumeId && resumeSentRef.current) {
      send({ type: "resume_context", resume_id: "" });
      resumeSentRef.current = null;
    }
  }, [isConnected, resumeId, send]);

  // 处理听悟结果（移到组件顶层，使用useCallback）
  const handleTingwuResult = useCallback((msg: WebSocketMessage) => {
    const tMsg = msg as TingwuResultMessage;
    
    // 使用工具函数处理听悟消息
    setTingwuSegments((prev) => {
      const result = processTingwuMessage(prev, tMsg);
      
      // 如果需要触发 ASR 流程，发送到主消息流
      if (result.shouldTriggerASR && result.asrText) {
        send({
          type: "asr_result",
          text: result.asrText,
          enable_qa: llmQaEnabled,  // 包含LLM实时问答开关状态
        });
      }
      
      return result.segments;
    });
  }, [llmQaEnabled, send]);

  // 处理听悟 WebSocket 消息
  useEffect(() => {
    const handleTingwuStatus = (msg: WebSocketMessage) => {
      setMessages((prev) => [...prev, msg]);
    };

    const handleTingwuError = (msg: WebSocketMessage) => {
      setMessages((prev) => [...prev, msg]);
    };

    onTingwu("status", handleTingwuStatus);
    onTingwu("tingwu_result", handleTingwuResult);
    onTingwu("error", handleTingwuError);

    return () => {
      offTingwu("status", handleTingwuStatus);
      offTingwu("tingwu_result", handleTingwuResult);
      offTingwu("error", handleTingwuError);
    };
  }, [onTingwu, offTingwu, handleTingwuResult]);

  // 处理 VAD 检测结果
  const handleVoiceActivity = useCallback(
    (isActive: boolean, energy: number) => {
      userVoiceActiveRef.current = isActive;

      // 如果用户开始说话且数字人正在播放，发送打断信号
      if (isActive && isDigitalHumanSpeakingRef.current) {
        console.log(`[VAD] 检测到用户说话 (能量: ${energy.toFixed(4)})，触发打断。当前数字人状态: ${isDigitalHumanSpeakingRef.current}`);
        sendInterrupt();
      }
    },
    [sendInterrupt]
  );

  // 处理音频块
  const handleAudioChunk = useCallback(
    (chunk: string) => {
      // 检查面试状态
      if (interviewState === "ended") {
        return;
      }

      // 优先走听悟实时转写链路，避免主 WS 同时收音频导致重复处理与卡顿
      if (isTingwuConnected) {
        sendTingwu({
          type: "audio_chunk",
          data: chunk,
        });
      } else {
        send({
          type: "audio_chunk",
          data: chunk,
        });
      }
    },
    [isTingwuConnected, send, sendTingwu, interviewState]
  );

  // 处理录音开始
  const handleRecordingStart = useCallback(() => {
    // 清空之前的状态
    resetPlaybackState();
    setMessages([]);
    setTingwuSegments([]);
    setLastVideoFrame(null);
    setVideoFrameCount(0);
    lastVideoFrameRef.current = null;
    videoFrameCountRef.current = 0;
    setIsProcessing(true); // 标记为处理中，这样状态会开始更新
    
    // 如果面试状态为idle，设置为in_progress
    if (interviewState === "idle") {
      setInterviewState("in_progress");
    }
  }, [resetPlaybackState, interviewState]);

  // 处理音频结束
  const handleAudioEnd = useCallback(() => {
    setIsProcessing(true);
    if (isTingwuConnected) {
      // 通知听悟链路结束
      sendTingwu({
        type: "audio_end",
      });
    } else {
      send({
        type: "audio_end",
      });
    }
  }, [isTingwuConnected, send, sendTingwu]);

  // 重置状态
  const handleReset = () => {
    resetPlaybackState();
    setMessages([]);
    setTingwuSegments([]);
    setLastVideoFrame(null);
    setVideoFrameCount(0);
    lastVideoFrameRef.current = null;
    videoFrameCountRef.current = 0;
    setIsProcessing(false);
    setInputText("");
  };

  // 处理文本输入提交
  const handleTextSubmit = useCallback(() => {
    const text = inputText.trim();
    console.log("[TextInput] 提交文本:", { text, isConnected, isProcessing });
    
    if (!text) {
      console.warn("[TextInput] 文本为空，无法提交");
      return;
    }
    
    if (!isConnected) {
      console.warn("[TextInput] WebSocket 未连接，无法提交");
      return;
    }
    
    if (isProcessing) {
      console.warn("[TextInput] 正在处理中，无法提交");
      return;
    }

    // 检查面试状态
    if (interviewState === "ended") {
      console.warn("[TextInput] 面试已结束，无法提交");
      return;
    }

    // 如果面试状态为idle，设置为in_progress
    if (interviewState === "idle") {
      setInterviewState("in_progress");
    }

    // 清空之前的状态（保留视频帧，只重置音频和消息）
    resetPlaybackState();  // 重置音频播放状态
    setMessages([]);
    setTingwuSegments([]);
    // 不重置视频帧，让视频继续显示并直接绘制新帧
    setIsProcessing(true);
    setInputText("");

    // 发送文本输入消息
    const message: WebSocketMessage = {
      type: "text_input",
      text: text,
      enable_qa: llmQaEnabled,  // 包含LLM实时问答开关状态
    };
    console.log("[TextInput] 发送消息:", message);
    send(message);
  }, [inputText, isConnected, isProcessing, llmQaEnabled, resetPlaybackState, send, interviewState]);

  // 处理结束面试
  const handleEndInterview = useCallback(() => {
    if (!isConnected) {
      console.warn("[Interview] WebSocket 未连接，无法结束面试");
      return;
    }

    if (interviewState === "ended") {
      console.warn("[Interview] 面试已经结束");
      return;
    }

    console.log("[Interview] 发送结束面试请求");
    send({ type: "end_interview" });
  }, [isConnected, interviewState, send]);

  // 关闭评价模态框并重置状态
  const handleCloseEvaluationModal = useCallback(() => {
    setShowEvaluationModal(false);
    setEvaluationResult(null);
    setIsGeneratingEvaluation(false);
    // 重置面试状态为idle，清空对话历史
    setInterviewState("idle");
    setMessages([]);
    setTingwuSegments([]);
    // 重置播放状态
    resetPlaybackState();
  }, [resetPlaybackState]);

  // 处理文本输入框键盘事件
  const handleTextKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && !e.ctrlKey && !e.metaKey && !e.shiftKey) {
        e.preventDefault();
        handleTextSubmit();
      }
    },
    [handleTextSubmit]
  );

  return (
    <div className="app">
      <header className="app-header">
        <h1>数字人应用</h1>
        <div className="connection-status">
          <span className={`status-indicator ${isConnected ? "connected" : "disconnected"}`}>{isConnected ? "已连接" : "未连接"}</span>
        </div>
      </header>

      <main className="app-main">
        <div className="left-panel">
          <div className="recorder-section">
            <h2>录音区域</h2>
            <AudioRecorder onAudioChunk={handleAudioChunk} onAudioEnd={handleAudioEnd} onRecordingStart={handleRecordingStart} onVoiceActivity={handleVoiceActivity} disabled={!isConnected} />
            {isProcessing && (
              <div className="processing-indicator">
                <div className="spinner"></div>
                <span>处理中...</span>
              </div>
            )}
          </div>

          <div className="text-input-section">
            <h2>文本输入</h2>
            <div className="llm-qa-toggle">
              <label>
                <input
                  type="checkbox"
                  checked={llmQaEnabled}
                  onChange={(e) => setLlmQaEnabled(e.target.checked)}
                  disabled={!isConnected || isProcessing}
                />
                <span>LLM 实时问答</span>
              </label>
            </div>
            <div className="text-input-container">
              <textarea
                className="text-input"
                value={inputText}
                onChange={(e) => setInputText(e.target.value)}
                onKeyDown={handleTextKeyDown}
                placeholder="输入文本进行测试（按 Enter 提交，Ctrl+Enter 换行）"
                disabled={!isConnected || isProcessing}
                rows={4}
              />
              <div className="text-input-actions">
                <button
                  className="submit-button"
                  onClick={handleTextSubmit}
                  disabled={!isConnected || isProcessing || !inputText.trim()}
                >
                  提交
                </button>
                <button
                  className="clear-button"
                  onClick={() => setInputText("")}
                  disabled={!inputText || isProcessing}
                >
                  清空
                </button>
              </div>
            </div>
          </div>

          <div className="job-section">
            <h2>目标岗位</h2>
            <div className="job-input">
              <input
                type="text"
                value={jobTitle}
                onChange={(e) => setJobTitle(e.target.value)}
                placeholder="例如：前端开发、产品经理、数据分析"
                disabled={isGeneratingJob}
              />
              <div className="job-actions">
                <button
                  className="submit-button"
                  onClick={handleJobGenerate}
                  disabled={isGeneratingJob || !jobTitle.trim()}
                >
                  生成岗位JD
                </button>
                {(jobTitle || jobStatus !== "请输入目标岗位名称") && (
                  <button
                    className="clear-button"
                    onClick={handleJobClear}
                    disabled={isGeneratingJob}
                  >
                    清除
                  </button>
                )}
              </div>
              {jobStatus && <div className="job-status">{jobStatus}</div>}
              {jobError && <div className="job-error">{jobError}</div>}
            </div>
          </div>

          <div className="resume-section">
            <h2>简历上传</h2>
            <div className="resume-upload">
              <input
                ref={resumeFileInputRef}
                type="file"
                accept="application/pdf"
                onChange={handleResumeFileChange}
                disabled={isUploadingResume}
              />
              <div className="resume-actions">
                <button
                  className="submit-button"
                  onClick={handleResumeUpload}
                  disabled={isUploadingResume || !resumeFile}
                >
                  上传并解析
                </button>
                {resumeId && (
                  <button
                    className="clear-button"
                    onClick={handleResumeClear}
                    disabled={isUploadingResume}
                  >
                    清除
                  </button>
                )}
              </div>
              {resumeFileName && <div className="resume-filename">已选择：{resumeFileName}</div>}
              {resumeStatus && <div className="resume-status">{resumeStatus}</div>}
              {resumeError && <div className="resume-error">{resumeError}</div>}
            </div>
          </div>

          <div className="status-section">
            <StatusPanel messages={messages} tingwuSegments={tingwuSegments} isTingwuConnected={isTingwuConnected} />
          </div>
        </div>

        <div className="right-panel">
          <div className="video-section">
            <h2>视频输出</h2>
            {/* 流程步骤指示 */}
            <ProcessSteps messages={messages} />
            <VideoPlayer lastFrame={lastVideoFrame} frameCount={videoFrameCount} />
            <div className="video-actions">
              {videoFrameCount > 0 && (
                <button className="reset-button" onClick={handleReset}>
                  重置
                </button>
              )}
              {interviewState === "in_progress" && (
                <button 
                  className="end-interview-button" 
                  onClick={handleEndInterview}
                  disabled={!isConnected}
                >
                  结束面试
                </button>
              )}
            </div>
            {isGeneratingEvaluation && (
              <div className="evaluation-loading">
                <div className="spinner"></div>
                <span>正在生成评价...</span>
              </div>
            )}
          </div>
        </div>
      </main>

      {/* 评价模态框 */}
      {showEvaluationModal && evaluationResult && (
        <EvaluationModal
          evaluationResult={evaluationResult}
          onClose={handleCloseEvaluationModal}
        />
      )}

      <footer className="app-footer">
        <p>数字人应用 - 测试版本 | 当前使用 Mock 服务</p>
      </footer>
    </div>
  );
}

export default App;
