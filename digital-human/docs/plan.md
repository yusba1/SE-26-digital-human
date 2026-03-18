# MVP 计划

LLM 真实服务接入（通义千问）+ 基础知识库（RAG）

知识库全靠大模型去做 LLM 生成

# 1 week

- [x] LLM + TTS 延迟问题
  - [x] 移除 LLM Mock 延迟 (llm_service.py)
  - [x] TTS 流式发送 (orchestrator.py, websocket.py)
  - [x] 前端流式音频播放 (App.tsx)
  - [x] 创建通义千问流式 LLM 服务 (llm_qwen.py)
  - [x] LLM + TTS 流水线并行 (orchestrator.py)

- [x] 窗口算法
  - [x] 减少前端音频缓冲 (AudioRecorder.tsx: 1600 -> 800)
  - [x] 降低 THG 处理阈值 (dihuman_core.py: 11040 -> 7200)

- [x] 抢话的算法
  - [x] 前端简单 VAD (AudioRecorder.tsx)
  - [x] 打断信号发送 (App.tsx)
  - [x] 后端打断处理 (websocket.py)
  - [x] 创建 VAD 服务 (vad_service.py)
  - [x] 创建会话状态管理器 (conversation_manager.py)
  - [x] 服务层快速取消 (thg_service.py)

# 3 Days
- 数字人不说话的时候静止，怎么处理
  - [x] 数字人不说话的时候插入一段空音频进行推理

- 嘴部抖动的问题
  - [x] 时序平滑处理（对推理前三帧渐进加权）
  - [x] 增加 syncNet 同步损失进行模型训练
  - [x] 提升模型训练时嘴部 mask 区域的权重


next week
小程序
