# 后端开发指南

## 项目结构

```
backend/
├── app/
│   ├── main.py              # FastAPI 应用入口
│   ├── config.py            # 配置管理
│   ├── api/
│   │   └── websocket.py     # WebSocket 端点（流式处理核心）
│   ├── services/            # 业务逻辑层
│   │   ├── asr_service.py      # ASR 服务接口
│   │   ├── llm_service.py      # 大模型服务接口
│   │   ├── tts_service.py      # TTS 服务接口
│   │   ├── thg_service.py      # THG 服务接口
│   │   └── orchestrator.py     # 流程编排器
│   ├── models/
│   │   └── schemas.py       # 数据模型
│   └── utils/               # 工具函数
├── requirements.txt
└── README.md
```

## 核心特性

### 流式处理架构

后端采用流式处理架构，实现边录音边处理：

1. **收到第一个音频块**: 立即启动并行处理流程
2. **并行执行**: ASR → LLM → TTS → THG 在录音过程中并行执行
3. **流式生成**: 视频块在录音过程中就开始流式生成
4. **实时反馈**: 通过 WebSocket 实时发送状态更新和结果

### 处理流程

```
开始录音
  ↓
收到第一个音频块
  ↓
启动并行处理流程（后台任务）
  ├─→ ASR: 识别语音 → 发送识别结果
  ├─→ LLM: 优化文本 → 发送优化结果
  ├─→ TTS: 合成语音
  └─→ THG: 流式生成视频块（20个）
  ↓
停止录音（audio_end）
  ↓
等待处理完成 → 发送完成消息
```

## 服务接口说明

### ASR 服务

**位置**: `app/services/asr_service.py`

**基类**: `ASRService`

**需要实现的方法**:

```python
async def recognize(self, audio_data: bytes) -> str:
    """识别音频为文字"""
    pass
```

**接入真实服务示例**:

```python
class RealASRService(ASRService):
    def __init__(self, api_url: str, api_key: str):
        self.api_url = api_url
        self.api_key = api_key

    async def recognize(self, audio_data: bytes) -> str:
        # 调用真实的 ASR API
        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.api_url,
                files={"audio": audio_data},
                headers={"Authorization": f"Bearer {self.api_key}"}
            )
            return response.json()["text"]
```

### LLM 服务

**位置**: `app/services/llm_service.py`

**基类**: `LLMService`

**需要实现的方法**:

```python
async def optimize_text(self, text: str) -> str:
    """优化文本"""
    pass
```

### TTS 服务

**位置**: `app/services/tts_service.py`

**基类**: `TTSService`

**需要实现的方法**:

```python
async def synthesize(self, text: str) -> AsyncGenerator[bytes, None]:
    """将文本合成为音频流"""
    pass
```

### THG 服务

**位置**: `app/services/thg_service.py`

**基类**: `THGService`

**需要实现的方法**:

```python
async def generate_video(
    self,
    audio_stream: AsyncGenerator[bytes, None]
) -> AsyncGenerator[bytes, None]:
    """根据音频流生成数字人视频流"""
    pass
```

## 切换服务实现

在 `app/api/websocket.py` 中，可以修改服务实例：

```python
# 根据配置选择服务实现
from app.config import settings

if settings.use_real_services:
    orchestrator = DigitalHumanOrchestrator(
        asr_service=RealASRService(api_url=settings.asr_service_url, api_key=settings.asr_api_key),
        llm_service=RealLLMService(api_url=settings.llm_service_url, api_key=settings.llm_api_key),
        tts_service=RealTTSService(api_url=settings.tts_service_url, api_key=settings.tts_api_key),
        thg_service=RealTHGService(api_url=settings.thg_service_url, api_key=settings.thg_api_key)
    )
else:
    orchestrator = DigitalHumanOrchestrator()  # 使用 Mock
```

## WebSocket API

### 端点

`ws://localhost:8000/api/ws`

### 消息协议

#### 客户端发送

```json
// 发送音频块（录音过程中持续发送）
{
  "type": "audio_chunk",
  "data": "base64_encoded_audio_data"
}

// 音频传输完成（停止录音时发送）
{
  "type": "audio_end"
}
```

#### 服务端响应

```json
// 状态更新（流式发送）
{
  "type": "status",
  "stage": "asr|llm|tts|thg",
  "message": "处理中..."
}

// ASR 识别结果
{
  "type": "asr_result",
  "text": "识别的文字"
}

// LLM 优化结果
{
  "type": "llm_result",
  "text": "优化后的文字"
}

// 视频块（流式发送，录音过程中开始）
{
  "type": "video_chunk",
  "data": "base64_encoded_video_data"
}

// 处理完成
{
  "type": "complete"
}

// 错误
{
  "type": "error",
  "message": "错误信息"
}
```

### 处理时序

1. **开始录音**: 客户端发送 `audio_chunk` 消息
2. **第一个音频块**: 服务端收到后立即启动并行处理流程
3. **录音过程中**: 
   - 持续接收 `audio_chunk`
   - 并行执行 ASR → LLM → TTS → THG
   - 流式发送状态更新、结果和视频块
4. **停止录音**: 客户端发送 `audio_end`
5. **完成**: 服务端等待处理完成，发送 `complete`

## 配置

创建 `.env` 文件（参考 `.env.example`）：

```env
# 应用配置
APP_NAME=Digital Human API
DEBUG=true
HOST=0.0.0.0
PORT=8000

# CORS 配置
CORS_ORIGINS=["http://localhost:5173","http://localhost:3000"]

# WebSocket 配置
WEBSOCKET_TIMEOUT=300

# 服务配置（接入真实服务时使用）
ASR_SERVICE_URL=https://your-asr-service.com
LLM_SERVICE_URL=https://your-llm-service.com
TTS_SERVICE_URL=https://your-tts-service.com
THG_SERVICE_URL=https://your-thg-service.com

# API Keys（接入真实服务时使用）
ASR_API_KEY=your-asr-api-key
LLM_API_KEY=your-llm-api-key
TTS_API_KEY=your-tts-api-key
THG_API_KEY=your-thg-api-key
```

## 运行

```bash
# 开发模式（自动重载）
python -m uvicorn app.main:app --reload

# 生产模式
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## API 文档

启动服务后，访问：
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## 测试

```bash
# 运行测试
pytest

# 带覆盖率
pytest --cov=app
```

## 注意事项

1. **流式处理**: 当前实现使用 Mock 服务，在录音过程中模拟流式处理。接入真实服务时，需要根据服务特性调整处理逻辑。

2. **视频生成**: Mock 服务生成 20 个视频块，每个块间隔 0.15 秒。真实服务需要根据实际视频格式和帧率调整。

3. **错误处理**: WebSocket 连接断开或处理异常时，会发送错误消息并清理资源。

4. **性能优化**: 大量并发连接时，注意资源管理和连接池配置。
