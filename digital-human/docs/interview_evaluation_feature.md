# 面试评价功能实现文档

## 1. 需求总结

### 1.1 核心功能
1. **结束面试按钮**
   - 在面试界面添加"结束面试"按钮
   - 按钮随时可见且可点击（不受处理状态限制）
   - 点击后立即停止所有音频播放和视频推理

2. **评价界面**
   - 点击结束面试后弹出评价界面（模态框）
   - 显示多维度评价雷达图
   - 评分范围：0-100分，评分标准严格
   - 显示面试总结文本
   - 显示改进建议文本
   - 界面主题与面试界面保持一致（深色主题）

3. **LLM评价生成**
   - 使用LLM分析整个面试对话历史
   - 生成多维度评分（0-100分）
   - 生成面试总结
   - 生成改进建议
   - 不使用死板规则，基于对话内容智能评价

### 1.2 功能约束
- 面试结束后，禁止执行音频播放和视频推理
- 评价界面关闭后，自动重新开始新一轮面试，自动清空对话历史
- 评价数据需要保存（可选，用于后续分析）

## 2. 逻辑漏洞补充

### 2.1 面试状态管理
**问题**：当前代码中没有明确的"面试进行中"状态标识，需要添加面试会话状态管理。

**解决方案**：
- 在WebSocket连接中维护面试状态（`interview_state: "idle" | "in_progress" | "ended"`）
- 面试开始时设置为 `in_progress`
- 点击结束面试后设置为 `ended`
- 状态为 `ended` 时，拒绝所有音频和视频处理请求

### 2.2 对话历史收集
**问题**：需要收集完整的面试对话历史用于LLM评价，当前代码中对话历史可能分散在不同地方。

**解决方案**：
- 在WebSocket连接中维护对话历史列表
- 记录所有ASR结果（用户输入）和LLM结果（面试官输出）
- 格式：`[{role: "user" | "assistant", content: string, timestamp: number}]`
- 面试结束时，将完整对话历史发送给评价服务

### 2.3 评价维度定义
**问题**：需要明确评价维度，确保LLM生成的结构化评价。

**解决方案**：
- 定义标准评价维度：
  1. **技术能力**（Technical Skills）：专业技能、技术深度
  2. **沟通表达**（Communication）：表达清晰度、逻辑性
  3. **问题解决**（Problem Solving）：分析问题、解决方案
  4. **团队协作**（Teamwork）：协作能力、沟通技巧
  5. **学习能力**（Learning Ability）：学习意愿、适应能力
- LLM需要为每个维度生成0-100的评分和简短说明

### 2.4 评价生成Prompt设计
**问题**：需要设计专门的评价Prompt，确保LLM生成严格、客观的评价。

**解决方案**：
- 创建评价专用的system prompt
- Prompt要求：
  - 评分标准严格，避免高分泛滥
  - 基于事实和对话内容，避免主观臆断
  - 评分分布合理（优秀80-100，良好60-79，一般40-59，较差0-39）
  - 总结和改进建议要具体、可操作

### 2.5 前端状态同步
**问题**：面试结束后，前端需要立即停止音频播放和视频更新，但可能存在异步操作。

**解决方案**：
- 添加面试状态state：`const [interviewState, setInterviewState] = useState<"idle" | "in_progress" | "ended">("idle")`
- 在音频播放和视频更新逻辑中检查状态
- 收到结束面试消息后，立即停止所有播放和更新

### 2.6 评价数据格式
**问题**：需要定义评价数据的结构化格式，便于前端渲染雷达图。

**解决方案**：
- 后端返回JSON格式：
```json
{
  "dimensions": [
    {"name": "技术能力", "score": 75, "description": "..."},
    {"name": "沟通表达", "score": 82, "description": "..."},
    ...
  ],
  "summary": "面试总结文本...",
  "suggestions": "改进建议文本..."
}
```

## 3. 技术实现方案

### 3.1 后端实现

#### 3.1.1 WebSocket消息扩展
**文件**：`backend/app/api/websocket.py`

**新增消息类型**：
- 客户端发送：`{"type": "end_interview"}`
- 服务端响应：`{"type": "interview_ended"}`
- 服务端响应：`{"type": "evaluation_result", "data": {...}}`

**修改点**：
1. 在WebSocket连接中维护面试状态和对话历史
2. 处理 `end_interview` 消息，停止所有处理任务
3. 调用评价服务生成评价
4. 返回评价结果

#### 3.1.2 评价服务
**文件**：`backend/app/services/evaluation_service.py`（新建）

**功能**：
- 接收对话历史
- 调用LLM生成评价
- 返回结构化评价数据

**接口**：
```python
async def evaluate_interview(
    conversation_history: List[Dict[str, str]],
    job_description: Optional[str] = None
) -> Dict[str, Any]:
    """
    评价面试
    
    Args:
        conversation_history: 对话历史 [{role: str, content: str}]
        job_description: 岗位描述（可选）
    
    Returns:
        评价结果 {
            "dimensions": [...],
            "summary": str,
            "suggestions": str
        }
    """
```

#### 3.1.3 评价Prompt
**文件**：`backend/app/services/prompts/evaluation_prompt.txt`（新建）

**内容要求**：
- 定义评价角色（专业面试评价专家）
- 明确评价维度
- 严格评分标准
- 输出格式要求（JSON）

### 3.2 前端实现

#### 3.2.1 结束面试按钮
**文件**：`frontend/src/App.tsx`

**位置**：在视频区域或头部添加按钮

**功能**：
- 点击后发送 `end_interview` 消息
- 禁用所有音频和视频相关操作
- 显示加载状态（生成评价中）

#### 3.2.2 评价界面组件
**文件**：`frontend/src/components/EvaluationModal.tsx`（新建）

**功能**：
- 模态框显示评价结果
- 雷达图可视化（使用echarts或recharts）
- 显示总结和建议
- 关闭按钮

#### 3.2.3 雷达图组件
**文件**：`frontend/src/components/RadarChart.tsx`（新建）

**功能**：
- 接收评价维度数据
- 渲染雷达图
- 支持深色主题

#### 3.2.4 样式文件
**文件**：`frontend/src/App.css`

**新增样式**：
- `.end-interview-button`：结束面试按钮样式
- `.evaluation-modal`：评价模态框样式
- `.radar-chart-container`：雷达图容器样式
- 保持与现有深色主题一致

## 4. 详细任务清单

### 阶段一：后端基础功能

#### 任务1.1：创建评价服务文件
- [ ] 创建 `backend/app/services/evaluation_service.py`
- [ ] 实现 `EvaluationService` 类
- [ ] 实现 `evaluate_interview` 方法
- [ ] 添加日志记录

#### 任务1.2：创建评价Prompt文件
- [ ] 创建 `backend/app/services/prompts/evaluation_prompt.txt`
- [ ] 编写评价角色定义
- [ ] 定义评价维度和评分标准
- [ ] 定义输出格式要求（JSON）

#### 任务1.3：扩展WebSocket消息协议
- [ ] 在 `websocket.py` 中添加 `end_interview` 消息处理
- [ ] 维护面试状态变量（`interview_state`）
- [ ] 维护对话历史列表（`conversation_history`）
- [ ] 在收到 `asr_result` 和 `llm_result` 时记录对话历史
- [ ] 处理 `end_interview` 消息：
  - 设置状态为 `ended`
  - 取消所有处理任务
  - 停止空闲视频生成
  - 调用评价服务
  - 返回评价结果

#### 任务1.4：添加状态检查逻辑
- [ ] 在音频处理前检查面试状态
- [ ] 在视频推理前检查面试状态
- [ ] 状态为 `ended` 时拒绝处理并返回错误

### 阶段二：前端基础功能

#### 任务2.1：添加面试状态管理
- [ ] 在 `App.tsx` 中添加 `interviewState` state
- [ ] 初始化状态为 `"idle"`
- [ ] 录音开始时设置为 `"in_progress"`
- [ ] 收到 `interview_ended` 消息时设置为 `"ended"`

#### 任务2.2：添加结束面试按钮
- [ ] 在视频区域或头部添加"结束面试"按钮
- [ ] 按钮样式与现有主题一致
- [ ] 按钮始终可见（不受 `isProcessing` 限制）
- [ ] 点击后发送 `end_interview` 消息
- [ ] 显示加载状态（"正在生成评价..."）

#### 任务2.3：实现状态检查逻辑
- [ ] 在音频播放逻辑中检查 `interviewState`
- [ ] 在视频更新逻辑中检查 `interviewState`
- [ ] 状态为 `"ended"` 时停止所有播放和更新
- [ ] 在 `handleAudioChunk` 中检查状态
- [ ] 在 `handleVideoChunk` 中检查状态

#### 任务2.4：处理评价结果消息
- [ ] 在 `App.tsx` 中添加 `evaluation_result` 消息处理
- [ ] 保存评价结果到state
- [ ] 打开评价模态框

### 阶段三：评价界面实现

#### 任务3.1：创建评价模态框组件
- [ ] 创建 `frontend/src/components/EvaluationModal.tsx`
- [ ] 实现模态框基础结构
- [ ] 添加关闭按钮
- [ ] 应用深色主题样式

#### 任务3.2：安装雷达图库
- [ ] 选择雷达图库（推荐：recharts 或 echarts-for-react）
- [ ] 安装依赖：`npm install recharts` 或 `npm install echarts echarts-for-react`
- [ ] 在 `EvaluationModal` 中引入

#### 任务3.3：实现雷达图组件
- [ ] 创建 `frontend/src/components/RadarChart.tsx`
- [ ] 接收评价维度数据作为props
- [ ] 配置雷达图：
  - 8个维度（或动态）
  - 0-100分刻度
  - 深色主题配色
- [ ] 显示每个维度的分数标签

#### 任务3.4：集成雷达图到模态框
- [ ] 在 `EvaluationModal` 中引入 `RadarChart`
- [ ] 传递评价数据
- [ ] 调整布局和样式

#### 任务3.5：显示总结和建议
- [ ] 在模态框中添加总结区域
- [ ] 在模态框中添加建议区域
- [ ] 应用文本样式（可滚动、行高合适）

### 阶段四：样式和优化

#### 任务4.1：添加评价相关样式
- [ ] 在 `App.css` 中添加 `.end-interview-button` 样式
- [ ] 添加 `.evaluation-modal` 样式
- [ ] 添加 `.radar-chart-container` 样式
- [ ] 确保样式与现有主题一致

#### 任务4.2：响应式设计
- [ ] 确保评价模态框在移动端正常显示
- [ ] 雷达图在小屏幕上自适应
- [ ] 文本区域支持滚动

#### 任务4.3：错误处理
- [ ] 评价生成失败时显示错误提示
- [ ] 网络错误处理
- [ ] 超时处理（评价生成超过30秒）

#### 任务4.4：用户体验优化
- [ ] 评价生成时显示加载动画
- [ ] 评价结果淡入动画
- [ ] 关闭模态框后可以重新开始面试

### 阶段五：测试和文档

#### 任务5.1：功能测试
- [ ] 测试结束面试按钮功能
- [ ] 测试评价生成
- [ ] 测试状态检查（结束后不能播放音频/视频）
- [ ] 测试评价界面显示
- [ ] 测试重新开始面试

#### 任务5.2：边界情况测试
- [ ] 空对话历史（未开始面试就结束）
- [ ] 极短对话（只有1-2轮）
- [ ] 极长对话（50+轮）
- [ ] 网络中断情况

#### 任务5.3：更新文档
- [ ] 更新API文档（WebSocket消息协议）
- [ ] 更新README（新功能说明）
- [ ] 添加使用示例

## 5. 技术细节

### 5.1 评价维度定义

```typescript
interface EvaluationDimension {
  name: string;        // 维度名称
  score: number;       // 0-100分
  description: string; // 评分说明
}

interface EvaluationResult {
  dimensions: EvaluationDimension[];
  summary: string;     // 面试总结
  suggestions: string;  // 改进建议
}
```

### 5.2 LLM Prompt示例

```
你是一位专业的面试评价专家。请根据以下面试对话历史，对候选人进行多维度评价。

评价维度：
1. 技术能力（Technical Skills）：专业技能、技术深度、实践经验
2. 沟通表达（Communication）：表达清晰度、逻辑性、语言组织
3. 问题解决（Problem Solving）：分析问题能力、解决方案质量
4. 团队协作（Teamwork）：协作能力、沟通技巧、冲突处理
5. 学习能力（Learning Ability）：学习意愿、适应能力、成长潜力

评分标准（严格）：
- 优秀（80-100分）：表现突出，明显超出预期
- 良好（60-79分）：表现良好，基本符合预期
- 一般（40-59分）：表现一般，存在明显不足
- 较差（0-39分）：表现较差，不符合要求

请基于对话内容，客观、严格地评分，避免高分泛滥。

输出格式（JSON）：
{
  "dimensions": [
    {"name": "技术能力", "score": 75, "description": "..."},
    ...
  ],
  "summary": "面试总结（200-300字）",
  "suggestions": "改进建议（200-300字）"
}
```

### 5.3 WebSocket消息协议扩展

**客户端 → 服务端**：
```json
{
  "type": "end_interview"
}
```

**服务端 → 客户端**：
```json
{
  "type": "interview_ended",
  "message": "面试已结束，正在生成评价..."
}
```

```json
{
  "type": "evaluation_result",
  "data": {
    "dimensions": [...],
    "summary": "...",
    "suggestions": "..."
  }
}
```

### 5.4 状态管理流程

```
面试开始（录音/文本输入）
  ↓
interviewState = "in_progress"
  ↓
记录对话历史
  ↓
用户点击"结束面试"
  ↓
发送 end_interview 消息
  ↓
后端：设置状态为 ended，停止所有处理
  ↓
后端：调用评价服务
  ↓
后端：返回 evaluation_result
  ↓
前端：设置 interviewState = "ended"
  ↓
前端：显示评价界面
  ↓
用户关闭评价界面
  ↓
前端：重置 interviewState = "idle"
  ↓
可以开始新的面试
```

## 6. 文件清单

### 6.1 新建文件
- `backend/app/services/evaluation_service.py`
- `backend/app/services/prompts/evaluation_prompt.txt`
- `frontend/src/components/EvaluationModal.tsx`
- `frontend/src/components/RadarChart.tsx`

### 6.2 修改文件
- `backend/app/api/websocket.py`
- `frontend/src/App.tsx`
- `frontend/src/App.css`
- `frontend/package.json`（添加雷达图库依赖）

### 6.3 可选文件
- `backend/app/models/evaluation.py`（如果需要数据库存储）
- `frontend/src/types/evaluation.ts`（TypeScript类型定义）

## 7. 验收标准

### 7.1 功能验收
- [ ] 结束面试按钮可见且可点击
- [ ] 点击后立即停止音频播放和视频更新
- [ ] 评价界面正确弹出
- [ ] 雷达图正确显示8个维度
- [ ] 评分范围在0-100
- [ ] 总结和建议正确显示
- [ ] 界面主题与现有界面一致

### 7.2 性能验收
- [ ] 评价生成时间 < 10秒（正常情况）
- [ ] 评价生成时间 < 30秒（极端情况，需要超时处理）
- [ ] 雷达图渲染流畅（无卡顿）

### 7.3 质量验收
- [ ] 代码通过ESLint检查
- [ ] TypeScript类型检查通过
- [ ] 无控制台错误
- [ ] 响应式设计正常（移动端测试）

## 8. 注意事项

1. **评分严格性**：确保LLM生成的评分严格，避免高分泛滥。可以在prompt中强调"严格评分"和"基于事实"。

2. **对话历史完整性**：确保收集完整的对话历史，包括所有用户输入和面试官输出。

3. **状态一致性**：前后端状态要保持一致，避免状态不同步导致的问题。

4. **错误处理**：评价生成可能失败，需要完善的错误处理和用户提示。

5. **用户体验**：评价生成需要时间，要显示加载状态，避免用户等待焦虑。

6. **数据隐私**：如果涉及敏感信息，需要考虑数据存储和隐私保护。

## 9. 后续优化方向（可选）

1. **评价数据存储**：将评价结果保存到数据库，支持历史查询
2. **评价报告导出**：支持导出PDF格式的评价报告
3. **多岗位适配**：根据岗位类型调整评价维度
4. **评价对比**：支持多个候选人的评价对比
5. **评价模板**：支持自定义评价维度和标准
