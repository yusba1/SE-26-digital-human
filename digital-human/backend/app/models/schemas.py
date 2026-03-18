"""数据模型定义"""
from pydantic import BaseModel
from typing import Optional, Literal


class WebSocketMessage(BaseModel):
    """WebSocket 消息基类"""
    type: str
    data: Optional[str] = None
    stage: Optional[str] = None
    message: Optional[str] = None
    text: Optional[str] = None


class AudioChunkMessage(BaseModel):
    """音频块消息"""
    type: Literal["audio_chunk"] = "audio_chunk"
    data: str  # base64 编码的音频数据


class AudioEndMessage(BaseModel):
    """音频结束消息"""
    type: Literal["audio_end"] = "audio_end"


class StatusMessage(BaseModel):
    """状态消息"""
    type: Literal["status"] = "status"
    stage: str  # asr, llm, tts, thg
    message: str


class ASRResultMessage(BaseModel):
    """ASR 识别结果"""
    type: Literal["asr_result"] = "asr_result"
    text: str


class LLMResultMessage(BaseModel):
    """LLM 处理结果"""
    type: Literal["llm_result"] = "llm_result"
    text: str


class VideoChunkMessage(BaseModel):
    """视频块消息"""
    type: Literal["video_chunk"] = "video_chunk"
    data: str  # base64 编码的视频数据


class CompleteMessage(BaseModel):
    """完成消息"""
    type: Literal["complete"] = "complete"


class ErrorMessage(BaseModel):
    """错误消息"""
    type: Literal["error"] = "error"
    message: str


class ResumeContextMessage(BaseModel):
    """简历上下文消息"""
    type: Literal["resume_context"] = "resume_context"
    resume_id: str


class JobContextMessage(BaseModel):
    """岗位上下文消息"""
    type: Literal["job_context"] = "job_context"
    job_title: str

