# 数字人项目 - MVP开发计划

> **MVP目标**：快速实现核心功能，验证AI面试场景可行性，避免过度设计

## 一、项目现状分析

### 已完成功能
| 模块 | 状态 | 说明 |
|------|------|------|
| 前端框架 | 完成 | React + TypeScript + Vite，完整UI组件 |
| 商业使用前端设计，小程序 | 未开始 | 待设计 |
| 后端框架 | 完成 | FastAPI + WebSocket，模块化服务架构 |
| WebSocket通信 | 完成 | 双WebSocket架构（主WS `/api/ws` + 听悟WS `/api/tingwu/ws`），实时双向通信 |
| ASR 服务 | 完成 | 听悟（Tingwu）实时转写已集成，已统一到orchestrator |
| TTS 服务 | 完成 | 5种实现：DashScope/阿里云/Edge/macOS/Mock，支持降级链 |
| THG 服务 | 完成 | RealTHGService 基于 ONNX 推理，支持 GPU/CPU |
| 流程编排 | 完成 | DigitalHumanOrchestrator 协调各服务 |
| 音视频同步 | 完成 | 已实现同步机制，时间戳已校正（320ms偏差已修复） |

### 已知问题
| 问题 | 影响 | 优先级 |
|------|------|--------|
| LLM 服务为 Mock | 无法进行真实对话 | P0 |
| 缺少容器化部署 | 无Dockerfile和docker-compose配置 | P0 |
| THG 推理性能 | CPU推理较慢 | P1 |

### MVP核心待办
- LLM 真实服务接入（通义千问）+ 基础知识库（RAG）
- AI面试核心功能（问题生成、基础评估）
- 基础部署方案（Docker Compose）

### 后续优化（非MVP）
- THG 性能优化（TensorRT/量化）
- ASR 备选方案（讯飞/Whisper）
- 多数字人形象支持
- 高级面试功能（详细报告、数据分析）

---

## 二、MVP开发计划

### 第一阶段：核心功能（MVP必须）

#### 1.1 LLM 服务接入 [阻塞项]
**目标**：接入真实大模型，实现基础对话和面试问题生成

| 任务 | 优先级 | 技术方案 |
|------|--------|----------|
| 通义千问接入 | P0 | DashScope API（已有SDK） |
| 基础知识库（RAG） | P0 | Chroma（轻量级）+ BGE-M3嵌入模型 |

**MVP功能范围**：
- 基础对话能力（LLM直接调用）
- 根据岗位JD生成面试问题（RAG检索相关题库）
- 基础评估（LLM直接评估，不依赖复杂规则）

**技术方案（MVP简化）**：
- **向量数据库**：Chroma（轻量级，单机部署）
- **嵌入模型**：BGE-M3（中文优化，本地推理）
- **检索策略**：简单语义检索（Top-3）
- **RAG流程**：检索相关文档 → 构建Prompt → LLM生成

**知识库内容（MVP最小集）**：
- 基础面试题库（技术类30题、通用类20题）
- 岗位JD模板（2-3个常见岗位示例）
- 基础评估提示词（LLM直接评估，无需复杂规则）

```
开发内容：
├── backend/app/services/
│   ├── llm_qwen.py           # 通义千问实现（DashScope）
│   ├── knowledge_base.py     # 知识库服务（Chroma，简化版）
│   └── interview_service.py  # AI面试服务（问题生成+基础评估）
├── backend/app/config.py     # 添加LLM和知识库配置
└── backend/knowledge_data/   # 知识库数据（最小集）
    ├── questions.txt         # 基础面试题库（文本文件）
    └── jd_examples.txt       # 岗位JD示例（文本文件）
```

**MVP实现要点**：
- 知识库使用简单文本文件存储，手动维护
- 评估直接使用LLM，不构建复杂规则引擎
- 前端UI保持简洁，以功能验证为主

#### 1.2 ASR架构统一 [已完成]
**目标**：统一ASR接口，解决听悟独立端点与orchestrator不统一的问题

| 任务 | 优先级 | 技术方案 | 状态 |
|------|--------|----------|------|
| 听悟集成到ASRService | P1 | 创建TingwuASRService，继承ASRService基类 | 已完成 |
| 统一ASR调用流程 | P1 | 修改orchestrator，支持流式ASR和批量ASR | 已完成 |
| 移除冗余ASR调用 | P1 | 优化WebSocket流程 | 已完成 |

**实现内容**：
- 创建 `TingwuASRService` 类，实现 `ASRService` 接口
- 扩展 `ASRService` 基类，添加 `recognize_stream` 方法（可选实现）
- 在 `orchestrator.py` 中统一ASR调用，听悟优先，Mock降级
- 优化 `websocket.py`，添加 `using_tingwu` 标记，避免冗余处理
- 改进代码质量：添加类型注解、使用logging、完善错误处理

**已修改文件**：
```
├── backend/app/services/
│   ├── asr_service.py         # 扩展ASRService接口，支持流式识别
│   ├── asr_tingwu.py          # 新增：TingwuASRService实现
│   └── orchestrator.py        # 统一ASR调用，听悟优先
└── backend/app/api/
    └── websocket.py           # 优化流程，移除冗余
```

#### 1.3 THG 基础优化
**目标**：确保THG服务可用，基础性能优化

| 任务 | 优先级 | 技术方案 |
|------|--------|----------|
| ONNX Runtime GPU支持 | P0 | 启用GPU执行提供者（如可用） |
| 路径配置修复 | P0 | 修复数据路径配置问题 |

**说明**：MVP阶段不进行深度性能优化，确保功能可用即可

---

### 第二阶段：MVP前端功能

#### 2.1 AI面试核心功能
| 任务 | 优先级 | 说明 |
|------|--------|------|
| 面试配置页面 | P0 | 岗位选择、JD输入（文本输入框） |
| 基础评估显示 | P0 | 显示LLM评估结果（文本形式） |
| 对话历史 | P0 | 当前会话历史显示（内存存储） |
| 错误处理 | P0 | 基础错误提示 |

**技术要点**：
- 保持现有组件结构
- 新增简单配置页面：`InterviewConfig.tsx`
- 评估结果直接显示在对话区域

**说明**：MVP阶段不做复杂UI，以功能验证为主

---

### 第三阶段：MVP部署

#### 3.1 基础容器化
| 任务 | 优先级 | 说明 |
|------|--------|------|
| Docker Compose | P0 | 本地开发环境一键启动 |
| 环境变量管理 | P0 | .env文件配置 |
| 健康检查 | P0 | 基础健康检查端点 |

**开发内容**：
```
├── docker-compose.yml      # 本地开发（后端+前端+Chroma）
└── .env.example            # 环境变量模板
```

**说明**：MVP阶段使用Docker Compose即可，不需要K8s等复杂部署

---

### 第四阶段：MVP安全基础

#### 4.1 基础安全
| 任务 | 优先级 | 说明 |
|------|--------|------|
| CORS 配置 | P0 | 开发/生产环境CORS白名单 |
| 输入验证 | P0 | 基础输入验证（文本长度、格式） |
| API Key保护 | P0 | 环境变量管理，不在代码中硬编码 |

**说明**：MVP阶段只做基础安全，复杂的安全和合规功能后续迭代

---

## 三、MVP产品形态

### 3.1 MVP功能范围
**目标**：验证AI面试场景可行性

**核心功能**：
- 语音输入 → ASR识别 → LLM生成问题/评估 → TTS合成 → THG生成视频
- 基础面试配置（岗位选择、JD输入）
- 实时对话面试
- 基础评估结果展示

**MVP不包含**：
- 多数字人形象切换（固定一个形象）
- 复杂评估报告（简单文本评估即可）
- 数据统计分析
- 面试记录持久化存储
- 多语言支持
- 高级UI特效

### 3.2 后续迭代方向
- 详细评估报告
- 面试记录管理
- 多数字人支持
- 数据统计分析
- API服务化

---

## 四、MVP技术债务（后续优化）

### 4.1 代码质量（MVP后）
- 单元测试
- 集成测试
- 文档完善

### 4.2 性能优化（MVP后）
- THG性能优化（TensorRT、量化）
- 音频缓冲优化
- 前端性能优化

### 4.3 功能扩展（MVP后）
- ASR备选方案
- 多数字人支持
- 详细评估报告
- 数据统计分析

---

## 五、MVP里程碑

### MVP Milestone 1: 核心功能
- LLM 服务接入（通义千问）
- 基础知识库（Chroma + BGE-M3）
- 面试服务开发（问题生成、基础评估）
- THG路径配置修复

### MVP Milestone 2: 前端功能
- 面试配置页面（岗位选择、JD输入）
- 基础评估显示
- 对话历史显示
- 错误处理

### MVP Milestone 3: 部署
- Docker Compose配置
- 环境变量管理
- 基础健康检查

**MVP完成后**：验证核心功能可行性，收集用户反馈，再决定后续迭代方向

---

## 六、MVP风险评估

| 风险 | 影响 | 应对措施 |
|------|------|----------|
| LLM API 成本 | 中 | MVP阶段控制调用量，后续考虑本地模型降级 |
| GPU 资源不足 | 中 | 支持CPU降级，MVP阶段可接受较慢速度 |
| 知识库数据质量 | 中 | MVP使用基础题库，后续持续优化 |
| 第三方服务依赖 | 低 | MVP阶段依赖听悟，后续再考虑备选方案 |

---

## 七、代码审查发现的问题

### 7.1 架构问题

1. **双WebSocket架构** [已优化]
   - 当前使用两个WebSocket连接：主WS (`/api/ws`) 和听悟WS (`/api/tingwu/ws`)
   - 前端需要维护两个连接，增加复杂度
   - 听悟结果通过前端转发到主WS，存在延迟和潜在的数据丢失风险
   - **优化方案**：保留双连接架构（听悟需要独立连接），但优化主WS逻辑，避免冗余处理

2. **ASR服务不统一** [已解决]
   - ~~`orchestrator.process_audio_stream` 中调用 `asr_service.recognize`（Mock实现）~~
   - ~~实际使用听悟时，ASR已在独立端点完成，导致重复调用~~
   - **解决方案**：
     - 创建 `TingwuASRService`，继承 `ASRService` 基类
     - 在 `orchestrator` 中统一ASR服务选择（听悟优先，Mock降级）
     - 支持流式和批量两种识别模式

3. **流程冗余** [已解决]
   - ~~`websocket.py` 中的 `stream_processing_pipeline` 调用 `process_audio_stream`，会触发Mock ASR~~
   - **解决方案**：
     - 优化 `websocket.py`，添加 `using_tingwu` 标记
     - 当收到 `asr_result` 时，取消备用处理流程，直接使用听悟结果
     - `stream_processing_pipeline` 仅作为不使用听悟时的备用方案

### 7.2 代码质量问题

1. **缺少类型注解** [已解决]
   - ~~`orchestrator.py` 中部分函数缺少完整的类型提示~~
   - ~~`websocket.py` 中消息处理逻辑复杂，缺少类型定义~~
   - **解决方案**：
     - 为所有函数添加完整的类型注解
     - 使用 `Optional`, `Dict`, `AsyncGenerator` 等类型提示
     - 改进代码可读性和IDE支持

2. **错误处理不完善** [已解决]
   - ~~WebSocket断开时的资源清理不完整~~
   - ~~异步任务取消逻辑需要优化~~
   - **解决方案**：
     - 添加 `asyncio.CancelledError` 处理
     - 在WebSocket断开时正确清理异步任务
     - 使用 `logging` 替代 `print`，统一日志管理
     - 完善异常处理和错误消息

3. **配置管理** [已优化]
   - 环境变量分散在多个地方（`config.py` 和直接 `os.getenv`）
   - **优化方案**：
     - `TingwuConfig` 保持从环境变量读取（向后兼容）
     - `config.py` 中添加配置项说明
     - 配置验证在 `TingwuConfig.is_valid` 中统一处理

### 7.3 性能问题（MVP可接受）

1. **音频缓冲**
   - `orchestrator.process_audio_stream` 需要完整音频数据，无法真正流式处理
   - MVP阶段可接受，后续优化

2. **视频生成延迟**
   - THG推理在CPU上较慢，需要GPU优化
   - MVP阶段可接受较慢速度，后续优化

### 7.4 部署问题

1. **缺少容器化** [MVP待解决]
   - 无Dockerfile和docker-compose配置
   - MVP阶段需要添加基础Docker Compose配置

2. **环境依赖** [已部分解决]
   - THG模型文件路径已配置化（通过config.py）
   - MVP阶段可手动检查环境，后续添加验证脚本