# 前端开发指南

## 项目结构

```
frontend/
├── src/
│   ├── App.tsx              # 主应用组件
│   ├── main.tsx             # 入口文件
│   ├── components/          # UI 组件
│   │   ├── AudioRecorder.tsx    # 录音组件
│   │   ├── VideoPlayer.tsx      # 视频播放组件
│   │   └── StatusPanel.tsx      # 状态面板
│   ├── hooks/               # 自定义 Hooks
│   │   └── useWebSocket.ts      # WebSocket Hook
│   ├── services/            # 前端服务
│   │   └── websocket.ts         # WebSocket 客户端
│   └── types/               # TypeScript 类型
│       └── index.ts
├── package.json
├── vite.config.ts
└── README.md
```

## 技术栈

- **React 18**: UI 框架
- **TypeScript**: 类型安全
- **Vite**: 构建工具和开发服务器
- **WebSocket API**: 实时通信
- **MediaRecorder API**: 浏览器录音

## 安装依赖

```bash
npm install
```

## 开发

```bash
npm run dev
```

应用将在 `http://localhost:5173` 启动。

## 构建

```bash
npm run build
```

构建产物将输出到 `dist/` 目录。

## 预览构建结果

```bash
npm run preview
```

## 组件说明

### AudioRecorder

录音组件，支持点击开始/停止录音。

**功能**:
- 使用浏览器 MediaRecorder API
- 点击"开始录音"开始录制
- 点击"停止录音"停止录制并发送数据
- 实时发送音频块到后端（每 100ms 发送一次）
- 显示录音时长

**Props**:
- `onAudioChunk`: 音频块回调（录音过程中持续调用）
- `onAudioEnd`: 录音结束回调（停止录音时调用）
- `onRecordingStart`: 录音开始回调（可选）
- `disabled`: 是否禁用（仅在未连接时禁用）

**交互方式**:
- 点击"开始录音" → 开始录制
- 点击"停止录音" → 停止录制并发送 `audio_end` 消息

### VideoPlayer

视频播放组件，接收并显示视频流。

**功能**:
- 接收 WebSocket 传来的视频块
- 实时显示已接收的视频块数量
- 当前为 Mock 数据占位（实际接入 THG 服务后将显示真实视频）

**Props**:
- `videoChunks`: 视频块数组（base64 字符串）

**显示逻辑**:
- `videoChunks.length === 0`: 显示"等待视频流..."
- `videoChunks.length > 0`: 显示"已接收 X 个视频块"

### StatusPanel

状态面板组件，显示处理流程的实时状态。

**功能**:
- 显示当前处理阶段和状态消息
- 显示 ASR 识别结果
- 显示 LLM 优化结果
- 显示流程步骤进度（实时更新）
- 完成的步骤显示为绿色
- 显示错误信息

**Props**:
- `messages`: WebSocket 消息数组

**步骤指示器**:
- **ASR**: 显示识别结果时变为绿色
- **LLM**: 显示优化结果时变为绿色
- **TTS**: 进入 THG 阶段时变为绿色
- **THG**: 处理完成时变为绿色

## WebSocket 客户端

### WebSocketClient

位于 `src/services/websocket.ts`，提供：

- 连接管理
- 自动重连（最多 5 次）
- 消息发送/接收
- 事件处理器注册

### useWebSocket Hook

位于 `src/hooks/useWebSocket.ts`，React Hook 封装：

```typescript
const { isConnected, send, on, off } = useWebSocket();
```

**返回值**:
- `isConnected`: 连接状态
- `send`: 发送消息
- `on`: 注册消息处理器
- `off`: 移除消息处理器

## 消息处理

### 消息类型

所有消息类型定义在 `src/types/index.ts`：

- `status`: 状态更新
- `asr_result`: ASR 识别结果
- `llm_result`: LLM 优化结果
- `video_chunk`: 视频块
- `complete`: 处理完成
- `error`: 错误信息

### 消息处理流程

1. **开始录音**: 发送 `audio_chunk` 消息（持续发送）
2. **接收状态**: 实时接收 `status` 消息，更新 UI
3. **接收结果**: 接收 `asr_result`、`llm_result`，显示结果
4. **接收视频**: 接收 `video_chunk`，更新视频块数量
5. **停止录音**: 发送 `audio_end` 消息
6. **完成**: 接收 `complete` 消息，标记处理完成

## 自定义配置

### Vite 配置

`vite.config.ts` 中已配置代理，将 `/api` 请求代理到后端：

```typescript
server: {
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true,
    },
  },
}
```

### WebSocket 地址

默认连接 `ws://localhost:8000/api/ws`，可在 `useWebSocket` Hook 中自定义：

```typescript
const { ... } = useWebSocket("ws://your-server.com/api/ws");
```

## 样式

使用 CSS 模块化，主要样式文件：
- `src/index.css`: 全局样式（深色主题背景）
- `src/App.css`: 应用样式（现代化 UI 设计）

**设计特点**:
- 深色主题（深蓝灰色渐变背景）
- 毛玻璃效果（backdrop-filter）
- 蓝色系主色调
- 响应式设计，适配移动端和桌面端

## 类型定义

所有 TypeScript 类型定义在 `src/types/index.ts`，包括：

- `WebSocketMessage`: 基础消息类型
- `AudioChunkMessage`: 音频块消息
- `StatusMessage`: 状态消息
- `ASRResultMessage`: ASR 结果消息
- `LLMResultMessage`: LLM 结果消息
- `VideoChunkMessage`: 视频块消息
- `CompleteMessage`: 完成消息
- `ErrorMessage`: 错误消息

## 开发建议

1. **组件拆分**: 保持组件小而专注
2. **类型安全**: 充分利用 TypeScript 类型
3. **错误处理**: 妥善处理 WebSocket 连接错误
4. **用户体验**: 提供清晰的加载和错误状态
5. **性能优化**: 注意视频流的处理，避免内存泄漏
6. **状态管理**: 使用 React Hooks 管理状态，保持组件简洁

## 部署

### 构建生产版本

```bash
npm run build
```

### 静态文件部署

将 `dist/` 目录部署到任何静态文件服务器，如：
- Nginx
- Apache
- Vercel
- Netlify
- GitHub Pages

### 环境变量

如需配置不同环境，可在 `vite.config.ts` 中使用环境变量：

```typescript
const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';
```

创建 `.env` 文件：

```env
VITE_API_URL=http://your-api-server.com
VITE_WS_URL=ws://your-api-server.com/api/ws
```

## 调试

### 浏览器控制台

应用包含调试日志，可在浏览器控制台查看：
- WebSocket 消息接收日志
- 视频块接收日志
- 错误信息

### 开发工具

- React DevTools: 检查组件状态
- Network 标签: 查看 WebSocket 连接
- Console 标签: 查看日志和错误
