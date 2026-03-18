# 数字人应用

一个完整的数字人应用，包含前端和后端，实现音频输入 → ASR → 大模型 → TTS → THG 数字人生成的完整流程。

## 项目架构

```
前端 (React + TypeScript + Vite)
    ↓ WebSocket (实时双向通信)
后端 (FastAPI + Python)
    ↓
流式处理流程
ASR → LLM → TTS → THG
```

## 核心特性

- **流式处理**: 边录音边处理，无需等待停止录音
- **并行执行**: ASR、LLM、TTS、THG 在录音过程中并行执行
- **实时反馈**: WebSocket 实时更新处理状态和结果
- **视频流生成**: 在录音过程中就开始流式生成视频块

## 技术栈

### 后端
- **FastAPI**: 现代、快速的 Python Web 框架
- **WebSocket**: 实时双向通信
- **Python 3.8+**: 编程语言
- **异步处理**: 支持流式处理和并行执行

### 前端
- **React 18**: UI 框架
- **TypeScript**: 类型安全
- **Vite**: 构建工具
- **WebSocket API**: 实时通信
- **MediaRecorder API**: 浏览器录音

## 快速开始

### 一键启动（推荐）

```bash
# 启动所有服务（自动安装依赖）
./start.sh
```

脚本会自动：
- 检查并创建虚拟环境
- 安装后端和前端依赖
- 同时启动后端和前端服务

### 手动启动

#### 后端启动

```bash
# 进入后端目录
cd backend

# 创建并激活虚拟环境
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt

# 启动服务
python -m uvicorn app.main:app --reload
```

后端服务将在 `http://localhost:8000` 启动。

#### 前端启动

```bash
# 进入前端目录
cd frontend

# 安装依赖
npm install

# 启动开发服务器
npm run dev
```

前端应用将在 `http://localhost:5173` 启动。

### 停止服务

```bash
# 停止所有服务并释放端口
./stop.sh
```

## 项目结构

```
digital-human/
├── backend/                    # Python 后端
│   ├── app/
│   │   ├── main.py            # FastAPI 应用入口
│   │   ├── config.py           # 配置管理
│   │   ├── api/
│   │   │   └── websocket.py   # WebSocket 端点
│   │   ├── services/          # 业务逻辑层
│   │   │   ├── asr_service.py      # ASR 服务接口
│   │   │   ├── llm_service.py     # 大模型服务接口
│   │   │   ├── tts_service.py     # TTS 服务接口
│   │   │   ├── thg_service.py     # THG 服务接口
│   │   │   └── orchestrator.py    # 流程编排器
│   │   ├── models/            # 数据模型
│   │   └── utils/             # 工具函数
│   ├── requirements.txt
│   └── README.md
├── frontend/                   # React 前端
│   ├── src/
│   │   ├── App.tsx            # 主应用组件
│   │   ├── components/        # UI 组件
│   │   │   ├── AudioRecorder.tsx    # 录音组件
│   │   │   ├── VideoPlayer.tsx      # 视频播放组件
│   │   │   └── StatusPanel.tsx      # 状态面板
│   │   ├── hooks/             # 自定义 Hooks
│   │   │   └── useWebSocket.ts
│   │   ├── services/          # 前端服务
│   │   │   └── websocket.ts
│   │   └── types/             # TypeScript 类型
│   └── package.json
├── start.sh                    # 一键启动脚本
├── stop.sh                     # 停止服务脚本
└── README.md
```

## 功能特性

### 核心功能
- ✅ **实时音频录制**: 点击开始/停止录音
- ✅ **流式处理**: 边录音边处理，无需等待
- ✅ **并行执行**: ASR、LLM、TTS、THG 在录音过程中并行执行
- ✅ **实时状态更新**: WebSocket 实时更新处理状态
- ✅ **视频流生成**: 在录音过程中流式生成视频块
- ✅ **步骤指示器**: 实时显示处理进度，完成的步骤保持绿色

### 服务支持（当前为 Mock）
- ✅ ASR 语音识别（Mock）
- ✅ 大模型文本优化（Mock）
- ✅ TTS 语音合成（Mock）
- ✅ THG 数字人生成（Mock）

### UI 特性
- ✅ 现代化深色主题设计
- ✅ 响应式布局
- ✅ 实时状态面板
- ✅ 流程步骤可视化

## 工作流程

1. **开始录音**: 点击"开始录音"按钮
2. **流式处理启动**: 收到第一个音频块后，立即启动处理流程
3. **并行执行**: 
   - ASR: 识别语音 → 显示识别结果
   - LLM: 优化文本 → 显示优化结果
   - TTS: 合成语音
   - THG: 流式生成视频块（20个块）
4. **实时更新**: 处理过程中实时更新状态和显示结果
5. **停止录音**: 点击"停止录音"，等待处理完成
6. **完成**: 显示最终结果和视频信息

## 开发说明

当前版本使用 **Mock 服务**进行测试。所有服务都有对应的抽象基类，后续开发者可以：

1. 继承对应的服务基类
2. 实现真实的服务逻辑
3. 在配置中切换实现类

详细说明请参考：
- [后端开发指南](backend/README.md)
- [前端开发指南](frontend/README.md)