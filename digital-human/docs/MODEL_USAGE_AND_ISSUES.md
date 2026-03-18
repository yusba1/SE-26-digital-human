# 数字人应用 - 模型使用原理与问题分析

## 目录

1. [应用架构概览](#1-应用架构概览)
2. [模型驱动原理](#2-模型驱动原理)
3. [发现的问题与错误](#3-发现的问题与错误)
4. [嘴型与TTS同步问题分析](#4-嘴型与tts同步问题分析)
5. [优化建议](#5-优化建议)

---

## 1. 应用架构概览

### 1.1 整体数据流

```
用户输入 (音频/文本)
     ↓
┌────────────────────────────────────────────────────┐
│                  后端处理流程                        │
│                                                    │
│  ASR (语音识别) → LLM (文本优化) → TTS (语音合成)   │
│                                        ↓           │
│                                   THG (数字人生成)  │
│                                        ↓           │
│                                   视频帧流输出      │
└────────────────────────────────────────────────────┘
     ↓
前端接收 (音频 + 视频帧)
     ↓
同步播放 (requestAnimationFrame 驱动)
```

### 1.2 核心文件结构

| 模块 | 文件路径 | 职责 |
|------|----------|------|
| 模型推理核心 | `backend/app/services/dihuman_core.py` | ONNX 模型加载与推理 |
| THG 服务 | `backend/app/services/thg_service.py` | 音频到视频帧的转换 |
| TTS 服务 | `backend/app/services/tts_service.py` | 文本到语音合成 |
| 流程编排 | `backend/app/services/orchestrator.py` | 协调各服务的执行 |
| WebSocket API | `backend/app/api/websocket.py` | 前后端通信 |
| 前端同步 | `frontend/src/App.tsx` | 音视频同步播放 |

---

## 2. 模型驱动原理

### 2.1 DiHumanProcessor 工作原理

**文件**: `backend/app/services/dihuman_core.py`

#### 2.1.1 模型文件

```python
UNET_MODEL_NAME = "tao_48_unet.onnx"      # UNet 模型 - 生成口型图像
ENCODER_MODEL_NAME = "encoder.onnx"       # WenNet AudioEncoder - 音频特征提取
```

#### 2.1.2 音频处理参数

```python
AUDIO_SAMPLE_RATE = 16000    # 采样率 16kHz
AUDIO_FRAME_SIZE = 160       # 每帧 160 samples = 10ms
MAX_FRAMES = 500             # 最大加载 500 帧预设图像
```

#### 2.1.3 处理流程

```
┌──────────────────────────────────────────────────────────────────┐
│                     DiHumanProcessor.process()                   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. 输入: audio_frame (160 samples, 10ms)                        │
│     ↓                                                            │
│  2. 音频缓冲积累                                                  │
│     audio_queue_get_feat (需要积累 11040 samples = 690ms)        │
│     ↓                                                            │
│  3. Kaldi Fbank 特征提取                                         │
│     fbank.accept_waveform() → 80维 Mel 频谱特征                  │
│     ↓                                                            │
│  4. WenNet AudioEncoder 编码                                     │
│     ort_ae_session.run() → 音频语义特征                          │
│     ↓                                                            │
│  5. 特征积累 (需要 8 帧特征)                                      │
│     using_feat (shape: [8, 16, 512])                             │
│     ↓                                                            │
│  6. UNet 推理                                                    │
│     输入: 原始脸部图像 + 音频特征                                 │
│     输出: 带新口型的脸部图像                                      │
│     ↓                                                            │
│  7. 图像合成                                                      │
│     将口型区域合成到全身图像                                      │
│     ↓                                                            │
│  8. 输出: (视频帧, 播放音频, 有效标志)                            │
│                                                                  │
└──────────────────────────────────────────────────────────────────┘
```

#### 2.1.4 关键延迟机制

```python
# 初始音频缓冲 (840ms 空音频)
self.audio_play_list = [0] * 13440  # 行 126-127

# 积累阈值 (690ms 才开始处理)
if self.audio_queue_get_feat.shape[0] >= 11040:  # 行 245

# 特征积累阈值 (8帧特征才输出)
if self.using_feat.shape[0] >= 8:  # 行 272
```

**总延迟**: 约 1-2 秒（从音频输入到对应视频帧输出）

### 2.2 THG 服务调用流程

**文件**: `backend/app/services/thg_service.py`

```python
class RealTHGService(THGService):
    async def generate_video(self, audio_stream):
        # 1. 接收音频流
        async for audio_chunk in audio_stream:
            # 2. 转换为 16kHz int16 PCM
            audio_data = self._convert_audio_to_pcm16_16k(audio_chunk)

            # 3. 添加到缓冲区
            self.audio_buffer = np.concatenate([self.audio_buffer, audio_data])

            # 4. 按 10ms (160 samples) 处理
            while len(self.audio_buffer) >= 160:
                audio_frame = self.audio_buffer[:160]

                # 5. 调用 DiHumanProcessor
                return_img, playing_audio, check_img = self.processor.process(audio_frame)

                # 6. 如果有新图像，编码为 JPEG 输出
                if check_img == 1 and return_img is not None:
                    success, encoded_img = cv2.imencode('.jpg', return_img)
                    yield {
                        "data": encoded_img.tobytes(),
                        "timestamp_ms": timestamp_ms,
                        "frame_index": frame_index
                    }
```

### 2.3 TTS 服务集成

**文件**: `backend/app/services/tts_service.py`

支持的 TTS 引擎优先级:

| 优先级 | 引擎 | 配置条件 |
|--------|------|----------|
| 1 | DashScopeTTSService | TTS_MODE=CLOUD + dashscope_api_key |
| 2 | AliyunTTSService | aliyun_tts_appkey + token |
| 3 | EdgeTTSService | edge-tts 库可用 |
| 4 | MacOSTTSService | macOS 平台 |
| 5 | MockTTSService | 降级方案 |

**输出格式**: 16kHz, 16-bit PCM, 每块 3200 bytes (100ms)

### 2.4 前端同步机制

**文件**: `frontend/src/App.tsx`

```typescript
// 同步参数
const TARGET_FPS = 20;                    // 目标帧率
const START_BUFFER_MS = 600;              // 启动前缓冲
const MIN_BUFFER_FRAMES = 12;             // 最小缓冲帧数
const MAX_BUFFER_WAIT_MS = 2000;          // 最大等待时间

// 同步算法
const tick = () => {
  const audioTimeMs = audio.currentTime * 1000;

  while (queue.length > 0) {
    const frame = queue[0];
    const frameTimeMs = frame.timestampMs - videoTimeOffsetMs;

    if (frameTimeMs <= audioTimeMs) {
      // 显示该帧
      lastVideoFrame = frame.data;
      queue.shift();
    } else {
      break;  // 等待下一个 tick
    }
  }

  requestAnimationFrame(tick);
};
```

---

## 3. 发现的问题与错误

### 3.1 orchestrator.py 中 TTS 音频未发送 (潜在 BUG)

**位置**: `backend/app/services/orchestrator.py:171-175`

```python
# 问题代码
audio_stream = self.tts_service.synthesize(optimized_text)
video_stream = self.thg_service.generate_video(audio_stream)  # 直接传给 THG
```

**问题**: 当通过 `process_audio_stream` 方法处理时，TTS 音频直接传给 THG，没有发送给前端。

**对比**: `websocket.py:91-107` 中的 `process_from_text` 正确地先收集音频再发送:

```python
# 正确做法
tts_audio_chunks = []
async for audio_chunk in audio_stream:
    tts_audio_chunks.append(audio_chunk)

# 发送给前端
full_audio = b''.join(tts_audio_chunks)
await send_message({"type": "tts_audio", "data": base64.b64encode(full_audio)})
```

**影响**: 使用音频输入时，前端可能无法播放 TTS 音频。

### 3.2 时间戳计算不准确

**位置**: `backend/app/services/thg_service.py:206`

```python
# 当前计算方式
timestamp_ms = int(processed_samples * 1000 / self.target_sample_rate)
```

**问题**: 时间戳基于累计输入的音频样本数，没有考虑 DiHumanProcessor 内部的缓冲延迟。

**实际延迟来源**:
1. 初始缓冲: 840ms (`audio_play_list = [0] * 13440`)
2. 积累阈值: 690ms (`audio_queue_get_feat.shape[0] >= 11040`)
3. 特征积累: 约 400ms (`using_feat.shape[0] >= 8`)

**影响**: 视频帧的时间戳与实际对应的音频位置有 1-2 秒偏差。

### 3.3 静音检测逻辑问题

**位置**: `backend/app/services/dihuman_core.py:205-213`

```python
if not np.any(audio_frame):  # 全零检测
    if not self.silence:
        self.empty_audio_counter += 1
    if self.empty_audio_counter >= 100:  # 1秒静音
        self.silence = True
```

**问题**: 使用 `np.any()` 检测是否全零过于严格，低音量音频可能被误判为静音。

---

## 4. 嘴型与TTS同步问题分析

### 4.1 问题现象

嘴型动作与 TTS 语音不同步，通常表现为:
- 嘴型动作滞后于语音
- 或嘴型与发音不对应

### 4.2 根本原因

#### 4.2.1 后端时间戳偏差

```
音频输入时间线:
[0ms]----[690ms]----[1090ms]----[1490ms]---->
  │         │           │           │
  │         │           │           └── 输出第3帧，timestamp=1490
  │         │           └── 输出第2帧，timestamp=1090
  │         └── 输出第1帧，timestamp=690
  └── 音频开始输入

实际对应关系:
视频帧1 (timestamp=690) 实际对应音频位置 ≈ 320-370ms
视频帧2 (timestamp=1090) 实际对应音频位置 ≈ 370-420ms
...
偏差: 约 320-370ms
```

#### 4.2.2 dihuman_core 内部音频处理逻辑

```python
# 行 251: 取用于处理的音频片段
self.audio_play_list.extend(self.audio_queue_get_feat[32*160:32*160+800])
# 32*160 = 5120 samples = 320ms 偏移
# 800 samples = 50ms 音频片段
```

视频帧实际对应的是 **320ms 偏移后的 50ms 音频**，但时间戳没有反映这个关系。

#### 4.2.3 前端同步假设

```typescript
// App.tsx 行 188-191
const firstFrame = videoFrameQueueRef.current[0];
videoTimeOffsetMsRef.current = firstFrame.timestampMs;  // 使用第一帧时间戳作为偏移
```

前端假设 `timestampMs` 准确反映音频位置，但后端时间戳计算有误。

### 4.3 数据流时序图

```
时间 →  0    100   200   300   400   500   600   700   800   900ms
        ┃                                                    ┃
TTS:    ┣━━━━━━━━━━━━━━ 音频生成完成 ━━━━━━━━━━━━━━━━━━━━━━━━━┫
        ┃                                                    ┃
THG:    ┣━━ 积累中 ━━━━━━━━━━━━━━━━━━━┫ 开始输出帧            ┃
        ┃          (等待690ms)        ┃                      ┃
        ┃                             ┃                      ┃
前端:   ┣━━━━━ 等待缓冲 ━━━━━━━━━━━━━━━┫ 开始同步播放         ┃
        ┃    (600ms + 帧缓冲)         ┃                      ┃
```

---

## 5. 优化建议

### 5.1 修复 orchestrator.py 的 TTS 音频发送

```python
# orchestrator.py 修改建议
async def process_audio_stream(self, audio_data: bytes, send_message):
    # ... ASR 和 LLM 处理 ...

    # TTS: 收集并发送音频
    audio_stream = self.tts_service.synthesize(optimized_text)
    tts_audio_chunks = []
    async for chunk in audio_stream:
        tts_audio_chunks.append(chunk)

    # 发送 TTS 音频给前端
    if tts_audio_chunks:
        full_audio = b''.join(tts_audio_chunks)
        await send_message({
            "type": "tts_audio",
            "data": base64.b64encode(full_audio).decode('utf-8')
        })

    # THG: 使用收集的音频
    async def audio_stream_for_thg():
        for chunk in tts_audio_chunks:
            yield chunk

    video_stream = self.thg_service.generate_video(audio_stream_for_thg())
    # ...
```

### 5.2 修正时间戳计算

**方案 A: 在 thg_service.py 中调整时间戳**

```python
# thg_service.py 修改建议
AUDIO_PROCESSING_DELAY_MS = 320  # dihuman_core 的内部偏移

async def generate_video(self, audio_stream):
    # ...
    if check_img == 1 and return_img is not None:
        # 调整时间戳，减去内部处理延迟
        raw_timestamp = int(processed_samples * 1000 / self.target_sample_rate)
        adjusted_timestamp = max(0, raw_timestamp - AUDIO_PROCESSING_DELAY_MS)
        yield {
            "data": encoded_img.tobytes(),
            "timestamp_ms": adjusted_timestamp,
            "frame_index": frame_index
        }
```

**方案 B: 在 dihuman_core.py 中返回准确的音频位置**

```python
# dihuman_core.py 修改建议
def process(self, audio_frame):
    # ... 处理逻辑 ...

    # 返回当前处理的音频在原始流中的实际位置
    audio_position_ms = (self.total_processed_samples - 5120) * 1000 / AUDIO_SAMPLE_RATE

    return return_img, playing_audio, check_img, audio_position_ms
```

### 5.3 前端同步优化

```typescript
// App.tsx 优化建议

// 1. 增加可配置的同步偏移
const SYNC_OFFSET_MS = 0;  // 可调整的微调值

// 2. 改进同步算法
const tick = () => {
  const audioTimeMs = audio.currentTime * 1000 + SYNC_OFFSET_MS;

  // 添加丢帧逻辑，避免累积延迟
  while (queue.length > 2) {  // 保持最多2帧缓冲
    const frame = queue[0];
    const frameTimeMs = frame.timestampMs - videoTimeOffsetMs;
    if (frameTimeMs < audioTimeMs - 100) {  // 超过100ms的旧帧直接丢弃
      queue.shift();
      continue;
    }
    break;
  }

  // ... 正常同步逻辑 ...
};
```

### 5.4 整体架构优化建议

1. **统一时间基准**: 在后端维护一个全局时间戳，从 TTS 开始计时

2. **流式处理优化**: 考虑让 TTS 和 THG 并行处理，而不是串行

3. **自适应同步**: 前端可以测量实际延迟并动态调整 `SYNC_OFFSET_MS`

4. **添加同步调试工具**: 在开发模式下显示音视频时间差，方便调试

---

---

## 6. 已实施的修复

### 6.1 orchestrator.py - TTS 音频发送修复

**修改位置**: `backend/app/services/orchestrator.py:169-194`

**修改内容**: 在 `process_audio_stream` 方法中，先收集 TTS 音频块，发送给前端后再传给 THG。

```python
# 修复后的代码
tts_audio_chunks = []
async for audio_chunk in audio_stream:
    tts_audio_chunks.append(audio_chunk)

# 发送 TTS 音频给前端播放
if tts_audio_chunks:
    full_audio = b''.join(tts_audio_chunks)
    await send_message({"type": "tts_audio", "data": audio_base64})

# 创建新的生成器用于 THG
async def audio_stream_for_thg():
    for chunk in tts_audio_chunks:
        yield chunk
```

### 6.2 thg_service.py - 时间戳校正

**修改位置**: `backend/app/services/thg_service.py:86-91, 213-217, 244-246`

**修改内容**: 添加 `AUDIO_PROCESSING_DELAY_MS = 320` 常量，在计算时间戳时减去内部处理延迟。

```python
# 修复后的代码
AUDIO_PROCESSING_DELAY_MS = 320

# 计算时间戳并校正内部处理延迟
raw_timestamp_ms = int(processed_samples * 1000 / self.target_sample_rate)
timestamp_ms = max(0, raw_timestamp_ms - self.AUDIO_PROCESSING_DELAY_MS)
```

### 6.3 App.tsx - 前端同步优化

**修改位置**: `frontend/src/App.tsx:25-30, 144-178`

**修改内容**:
1. 添加可调节的同步偏移参数 `SYNC_OFFSET_MS`
2. 添加最大帧延迟参数 `MAX_FRAME_LAG_MS = 150`
3. 优化同步循环，自动丢弃过时的帧

```typescript
// 新增配置参数
const SYNC_OFFSET_MS = 0;        // 同步微调
const MAX_FRAME_LAG_MS = 150;    // 最大允许延迟

// 同步循环优化
const audioTimeMs = audio.currentTime * 1000 + SYNC_OFFSET_MS;

// 丢弃过时的帧
while (queue.length > 1) {
  if (frameTimeMs < audioTimeMs - MAX_FRAME_LAG_MS) {
    queue.shift();
    continue;
  }
  break;
}
```

---

## 附录: 关键代码位置索引

| 问题 | 文件 | 行号 |
|------|------|------|
| 时间戳计算 | thg_service.py | 213-217 |
| 音频缓冲延迟 | dihuman_core.py | 126-127, 245 |
| 音频位置偏移 | dihuman_core.py | 251 |
| 特征积累阈值 | dihuman_core.py | 272 |
| TTS 音频发送 | orchestrator.py | 169-194 |
| 前端时间偏移 | App.tsx | 208-211 |
| 前端同步循环 | App.tsx | 132-179 |
| 同步参数配置 | App.tsx | 25-30 |
