"""阿里云听悟（Tingwu）实时转写客户端

优先真实调用听悟 SDK，失败时自动回退到 Mock。
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterable, AsyncIterator, Dict, Optional

import websockets

# 加载 .env 文件
try:
    from dotenv import load_dotenv
    
    # 确保从 backend 目录加载 .env 文件
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path)
except ImportError:
    # dotenv 未安装时忽略
    pass

# 尝试导入阿里云听悟 SDK，失败则仅使用 Mock 实现，避免后端无法启动
try:  # pragma: no cover - 简单可选依赖导入
    from alibabacloud_tea_openapi import models as open_api_models  # type: ignore
    import alibabacloud_tea_util as tea_util  # type: ignore
    from alibabacloud_tingwu20230930.client import Client as TingwuClient  # type: ignore

    _TINGWU_SDK_AVAILABLE = True
except ImportError as e:  # pragma: no cover
    open_api_models = None  # type: ignore
    tea_util = None  # type: ignore
    TingwuClient = None  # type: ignore
    _TINGWU_SDK_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class TingwuConfig:
    """听悟配置（复用 PowerEI Web 的环境变量命名）"""

    access_key_id: Optional[str] = None
    access_key_secret: Optional[str] = None
    endpoint: Optional[str] = None
    app_key: Optional[str] = None
    project_id: Optional[str] = None

    def __post_init__(self):
        """在实例化后从环境变量读取配置（如果没有提供值）"""
        if self.access_key_id is None:
            self.access_key_id = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID")
        if self.access_key_secret is None:
            self.access_key_secret = os.getenv("ALIBABA_CLOUD_ACCESS_KEY_SECRET")
        if self.endpoint is None:
            self.endpoint = os.getenv("TINGWU_ENDPOINT")
        if self.app_key is None:
            self.app_key = os.getenv("TINGWU_APP_KEY")
        if self.project_id is None:
            self.project_id = os.getenv("TINGWU_PROJECT_ID")

    @property
    def is_valid(self) -> bool:
        return bool(self.access_key_id and self.access_key_secret and self.endpoint and self.app_key)


class TingwuRealtimeClient:
    """听悟实时转写客户端

    - 配置 & SDK 可用：真实接入听悟实时转写；
    - 否则：使用 Mock 打通链路。
    """

    def __init__(self, config: TingwuConfig | None = None) -> None:
        self.config = config or TingwuConfig()
        self._client: Optional["TingwuClient"] = None

        # 只有在 SDK 可用且配置完整时才尝试初始化真实客户端
        if _TINGWU_SDK_AVAILABLE and self.config.is_valid:
            try:
                self._client = self._init_client()
                logger.info("TingwuRealtimeClient initialized with real Tingwu SDK.")
            except Exception as e:  # noqa: BLE001
                logger.error("初始化听悟 SDK 失败，将回退到 Mock 实现: %s", e, exc_info=True)
                self._client = None
        else:
            logger.warning(
                "听悟 SDK 未安装或配置不完整（需要安装 alibabacloud-tea-openapi / "
                "alibabacloud-tea-util / alibabacloud-tingwu20230930 且设置 "
                "ALIBABA_CLOUD_ACCESS_KEY_ID / SECRET, TINGWU_ENDPOINT, TINGWU_APP_KEY），"
                "当前使用 Mock 实现。"
            )

    def _init_client(self) -> "TingwuClient":
        cfg = open_api_models.Config(
            access_key_id=self.config.access_key_id,
            access_key_secret=self.config.access_key_secret,
        )
        if self.config.endpoint:
            cfg.endpoint = self.config.endpoint
        return TingwuClient(cfg)

    async def stream_transcribe(
        self,
        audio_iter: AsyncIterable[bytes],
    ) -> AsyncIterator[Dict[str, Any]]:
        """将音频流发送到听悟，异步逐条返回转写结果 JSON。

        统一返回结构：
        {
            "text": "当前增量文本（可能为空）",
            "raw": {... 听悟原始 JSON ...}
        }
        """
        if self._client is None:
            logger.warning("使用 Mock 实现进行转写（_client 为 None）")
            async for item in self._mock_stream_transcribe(audio_iter):
                yield item
            return

        logger.info("使用真实听悟 SDK 进行转写")
        async for item in self._real_stream_transcribe(audio_iter):
            yield item

    # -------------------- 真实调用 --------------------
    async def _real_stream_transcribe(
        self,
        audio_iter: AsyncIterable[bytes],
    ) -> AsyncIterator[Dict[str, Any]]:
        # 1. 通过 OpenAPI 创建 realtime 任务，获取 WebSocket 地址
        try:
            from alibabacloud_tingwu20230930 import models as tingwu_models
            
            # 设置转写参数，开启中间结果返回（OutputLevel=2）
            transcription_params = tingwu_models.CreateTaskRequestParametersTranscription(
                output_level=2,  # 2：识别出中间结果及完整句子时返回识别结果
            )
            parameters = tingwu_models.CreateTaskRequestParameters(
                transcription=transcription_params,
            )
            
            create_req = tingwu_models.CreateTaskRequest(
                type="realtime",
                app_key=self.config.app_key,
                input=tingwu_models.CreateTaskRequestInput(
                    source_language="cn",
                    sample_rate=16000,
                    format="pcm",  # 前端现在发送的是 PCM 格式
                ),
                parameters=parameters,
            )
            runtime = tea_util.models.RuntimeOptions()

            # Python SDK 使用同步方法，在异步环境中用 asyncio.to_thread 包装
            def _create_task_sync():
                return self._client.create_task_with_options(create_req, {}, runtime)

            resp = await asyncio.to_thread(_create_task_sync)
            body = resp.body

            # 提取 WebSocket URL
            data_obj = None
            if hasattr(body, "data"):
                data_obj = body.data
            elif hasattr(body, "Data"):
                data_obj = body.Data
            elif isinstance(body, dict):
                data_obj = body.get("data") or body.get("Data")

            ws_url = None
            if data_obj:
                # 尝试多种可能的属性名
                for attr in ("meetingJoinUrl", "MeetingJoinUrl", "meeting_join_url"):
                    if hasattr(data_obj, attr):
                        ws_url = getattr(data_obj, attr)
                        break
                    if isinstance(data_obj, dict) and attr in data_obj:
                        ws_url = data_obj.get(attr)
                        break

            if not ws_url:
                logger.error(f"听悟 createTask 返回数据结构: {body}")
                raise RuntimeError(f"听悟 createTask 返回中找不到 WebSocket 地址")

            logger.info(f"Tingwu realtime websocket url acquired: {ws_url[:50]}...")
        except Exception as e:  # noqa: BLE001
            logger.error(f"创建听悟实时转写任务失败: {e}", exc_info=True)
            raise

        # 2. 建立 WebSocket 连接，发送 StartTranscription + PCM 音频 + StopTranscription
        try:
            async with websockets.connect(ws_url) as ws:
                logger.info("已连接到听悟 WebSocket")
                
                # 发送开始转写命令
                # 前端现在使用 AudioContext 实时转换为 PCM 格式发送
                start_cmd = {
                    "header": {
                        "name": "StartTranscription",
                        "namespace": "SpeechTranscriber",
                    },
                    "payload": {
                        "format": "pcm",
                        "sample_rate": 16000,
                    },
                }
                await ws.send(json.dumps(start_cmd))
                logger.debug("已发送 StartTranscription 命令")

                # 启动音频发送任务
                send_task = asyncio.create_task(self._send_audio(ws, audio_iter))

                try:
                    # 接收转写结果
                    async for msg in ws:
                        try:
                            if isinstance(msg, bytes):
                                # 二进制消息，尝试解码
                                try:
                                    msg = msg.decode("utf-8")
                                except UnicodeDecodeError:
                                    logger.warning("收到无法解码的二进制消息，跳过")
                                    continue

                            data = json.loads(msg)
                            header_name = data.get("header", {}).get("name", "")
                            text = self._extract_text_from_tingwu_payload(data)
                            logger.debug(f"收到听悟消息: name={header_name}, extracted_text={text[:50] if text else 'empty'}...")
                            if text or header_name in {
                                "TranscriptionResultChanged",
                                "SentenceEnd",
                                "SentenceBegin",
                                "TranscriptionStarted",
                                "TranscriptionCompleted",
                            }:
                                yield {"text": text, "raw": data}
                        except json.JSONDecodeError as e:  # noqa: BLE001
                            logger.warning(f"解析听悟消息失败: {e}, 原始消息: {msg[:100]}")
                            yield {"text": "", "raw": {"_raw": msg, "_error": "parse_failed"}}
                        except Exception as e:  # noqa: BLE001
                            logger.error(f"处理听悟消息时出错: {e}", exc_info=True)
                            yield {"text": "", "raw": {"_error": str(e)}}
                finally:
                    # 清理音频发送任务
                    if not send_task.done():
                        send_task.cancel()
                        with contextlib.suppress(asyncio.CancelledError):
                            await send_task
                    logger.info("听悟 WebSocket 连接已关闭")
        except Exception as e:  # noqa: BLE001
            logger.error(f"听悟 WebSocket 连接或通信失败: {e}", exc_info=True)
            raise

    async def _send_audio(
        self,
        ws: "websockets.WebSocketClientProtocol",
        audio_iter: AsyncIterable[bytes],
    ) -> None:
        """发送音频到听悟 WebSocket。

        注意：前端发送的是 WebM 容器中的 Opus 编码数据，需要直接发送给听悟。
        听悟支持 opus 格式，但可能需要纯 Opus 流而不是 WebM 容器。
        """
        chunk_count = 0
        total_bytes = 0
        async for chunk in audio_iter:
            if not chunk:
                continue
            try:
                chunk_count += 1
                total_bytes += len(chunk)
                await ws.send(chunk)
                if chunk_count % 50 == 0:  # 每50个chunk记录一次
                    logger.debug(f"已发送 {chunk_count} 个音频块，总计 {total_bytes} 字节")
            except Exception as e:  # noqa: BLE001
                logger.error("发送音频到听悟 WebSocket 失败: %s", e)
                break
        
        logger.info(f"音频发送完成：共 {chunk_count} 个块，{total_bytes} 字节")

        stop_cmd = {
            "header": {
                "name": "StopTranscription",
                "namespace": "SpeechTranscriber",
            },
            "payload": {},
        }
        try:
            await ws.send(json.dumps(stop_cmd))
        except Exception as e:  # noqa: BLE001
            logger.error("发送 StopTranscription 失败: %s", e)

    def _extract_text_from_tingwu_payload(self, data: Dict[str, Any]) -> str:
        """从听悟返回 JSON 中抽取当前可读文本
        
        根据 PowerEI 项目的实现：
        - TranscriptionResultChanged: 中间结果，从 payload.result 获取
        - SentenceEnd: 句子结束，从 payload.result + payload.stash_result.text 获取完整句子
        """
        try:
            header = data.get("header") or {}
            payload = data.get("payload") or {}
            name = header.get("name")

            if name == "TranscriptionResultChanged":
                # 中间结果，返回当前识别到的文本
                result_text = payload.get("result") or ""
                return str(result_text)

            elif name == "SentenceEnd":
                # 句子结束，组合最终文本
                result_text = payload.get("result") or ""
                stash_result = payload.get("stash_result") or {}
                if isinstance(stash_result, dict):
                    stash_text = stash_result.get("text") or ""
                    result_text = result_text + stash_text
                return str(result_text)

            # 其他消息类型不返回文本
            return ""
        except Exception as e:  # noqa: BLE001
            logger.warning(f"提取听悟文本失败: {e}, data: {data}")
            return ""

    # -------------------- Mock 实现 --------------------
    async def _mock_stream_transcribe(
        self,
        audio_iter: AsyncIterable[bytes],
    ) -> AsyncIterator[Dict[str, Any]]:
        consumed_chunks = 0

        async for _chunk in audio_iter:
            consumed_chunks += 1
            await asyncio.sleep(0.05)

            if consumed_chunks == 5:
                yield self._build_mock_result(
                    partial_text="你好，这是听悟实时转写的第一段 Mock 文本。",
                    seq=1,
                )
            elif consumed_chunks == 10:
                yield self._build_mock_result(
                    partial_text="这里是第二段 Mock 文本，用于展示持续转写效果。",
                    seq=2,
                )
            elif consumed_chunks == 15:
                yield self._build_mock_result(
                    partial_text="最后一段 Mock 文本，实际接入听悟后会替换为真实结果。",
                    seq=3,
                    is_final=True,
                )

        if consumed_chunks < 5:
            yield self._build_mock_result(
                partial_text="音频较短，这是一个简单的 Mock 转写结果示例。",
                seq=1,
                is_final=True,
            )

    def _build_mock_result(
        self,
        partial_text: str,
        seq: int,
        is_final: bool = False,
    ) -> Dict[str, Any]:
        return {
            "text": partial_text,
            "raw": {
                "requestId": f"mock-request-{seq}",
                "sequence": seq,
                "isFinal": is_final,
                "result": {
                    "transcription": {
                        "text": partial_text,
                        "sentences": [
                            {
                                "id": seq,
                                "text": partial_text,
                                "startTime": (seq - 1) * 2.0,
                                "endTime": seq * 2.0,
                            }
                        ],
                    },
                    "summarization": {
                        "summary": "这是一个用于展示的 Mock 转写结果，实际接入听悟后会替换为真实数据。"
                    },
                },
                "debug": {
                    "source": "mock",
                    "note": "TingwuRealtimeClient 使用 Mock（配置或 SDK 不可用时）。",
                },
            },
        }


