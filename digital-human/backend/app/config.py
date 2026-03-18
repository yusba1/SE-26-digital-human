"""配置管理模块"""
try:
    from pydantic_settings import BaseSettings
except ImportError:
    from pydantic import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """应用配置"""
    
    # 应用基础配置
    app_name: str = "Digital Human API"
    debug: bool = True
    
    # 服务器配置
    host: str = "0.0.0.0"
    port: int = 8000
    
    # CORS 配置
    cors_origins: list[str] = ["http://localhost:5173", "http://localhost:3000"]
    
    # WebSocket 配置
    websocket_timeout: int = 300  # 5分钟
    
    # 服务配置（后续接入真实服务时使用）
    asr_service_url: Optional[str] = None
    llm_service_url: Optional[str] = None
    tts_service_url: Optional[str] = None
    thg_service_url: Optional[str] = None
    
    # TTS mode configuration
    tts_mode: str = "LOCAL"  # LOCAL or CLOUD
    
    # Aliyun TTS configuration (nls-gateway RESTful API)
    aliyun_tts_appkey: Optional[str] = None
    aliyun_tts_token: Optional[str] = None
    aliyun_tts_voice: str = "zhitian_emo"  # voice name, see: https://help.aliyun.com/document_detail/84435.html
    aliyun_tts_format: str = "wav"  # pcm/wav/mp3
    aliyun_tts_sample_rate: int = 16000  # 8000/16000
    
    # DashScope TTS configuration (CosyVoice)
    dashscope_api_key: Optional[str] = None
    dashscope_tts_model: str = "cosyvoice-v3-plus"  # 如果使用克隆声音（cosyvoice-v3-plus-*），请改为 "cosyvoice-v3-plus"
    dashscope_tts_voice: str = "longanyang"  # 可通过环境变量 DASHSCOPE_TTS_VOICE 覆盖
    dashscope_tts_format: str = "pcm"  # pcm/wav/mp3 (pcm recommended for best performance)
    dashscope_tts_sample_rate: int = 16000

    # LLM 配置
    llm_mode: str = "MOCK"  # MOCK, QWEN
    llm_model: str = "qwen-turbo"  # qwen-turbo, qwen-plus, qwen-max
    llm_system_prompt: Optional[str] = None  # 系统提示词
    llm_mock_delay: float = 0.0  # Mock LLM 延迟（秒），默认无延迟
    
    # 百炼应用配置
    bailian_app_id: str = "52ef7010e1ca4cf494ada4d65c9bce59"  # 百炼应用ID（默认值，可通过环境变量覆盖）
    bailian_enable_qa: bool = False  # 是否启用LLM实时问答（默认关闭，由前端控制）
    
    # 听悟（Tingwu）实时转写配置
    # 注意：tingwu_client.py 也支持从环境变量直接读取（ALIBABA_CLOUD_ACCESS_KEY_ID等）
    # 这里提供配置项，但优先使用环境变量（保持向后兼容）
    tingwu_api_base: Optional[str] = None  # 听悟实时转写 API 基址/endpoint (TINGWU_ENDPOINT)
    tingwu_access_key_id: Optional[str] = None  # 阿里云AccessKey ID (ALIBABA_CLOUD_ACCESS_KEY_ID)
    tingwu_access_key_secret: Optional[str] = None  # 阿里云AccessKey Secret (ALIBABA_CLOUD_ACCESS_KEY_SECRET)
    tingwu_app_key: Optional[str] = None  # 听悟AppKey (TINGWU_APP_KEY)
    tingwu_project_id: Optional[str] = None  # 听悟Project ID (TINGWU_PROJECT_ID)
    
    # THG 数字人生成配置
    thg_data_path: Optional[str] = None  # THG 数据文件路径（包含模型文件和数据文件）
    thg_use_gpu: bool = True  # 是否使用 GPU
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        # 允许额外的环境变量，这些变量会被 tingwu_client.py 直接通过 os.getenv() 读取
        extra = "ignore"


# 全局配置实例
settings = Settings()

