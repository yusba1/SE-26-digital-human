# AI 面试官 Prompt 使用说明

## 文件说明

- `interview_prompt.md`: 完整的 AI 面试官 prompt 文档，包含详细说明和示例
- `interview_system_prompt.txt`: 精简版的系统提示词，可直接用于 LLM 的 system_prompt
- `__init__.py`: Prompt 管理模块，提供加载和使用 prompt 的工具函数

## 快速使用

### 方式一：通过配置文件使用

在 `.env` 文件中配置：

```bash
# 使用默认面试 prompt
LLM_MODE=QWEN
LLM_MODEL=qwen-turbo
LLM_SYSTEM_PROMPT="你是一位专业、友好、公正的 AI 面试官..."
```

或者直接使用文件内容：

```python
from app.services.prompts import get_interview_system_prompt

system_prompt = get_interview_system_prompt()
```

### 方式二：在代码中使用

```python
from app.services.prompts import get_interview_system_prompt, get_interview_prompt_with_context
from app.services.llm_qwen import QwenLLMService

# 基础使用
system_prompt = get_interview_system_prompt()
llm_service = QwenLLMService(
    api_key="your-api-key",
    model="qwen-turbo",
    system_prompt=system_prompt
)

# 带上下文使用（推荐）
job_description = "招聘 Python 后端工程师，要求 3 年以上经验..."
candidate_resume = "张三，5 年 Python 开发经验，熟悉 Django、Flask..."

system_prompt = get_interview_prompt_with_context(
    job_description=job_description,
    candidate_resume=candidate_resume,
    interview_stage="核心问题"
)

llm_service = QwenLLMService(
    api_key="your-api-key",
    model="qwen-turbo",
    system_prompt=system_prompt
)
```

### 方式三：在 orchestrator 中自动加载

修改 `backend/app/services/orchestrator.py`：

```python
from app.services.prompts import get_interview_system_prompt

def _init_llm_service(self) -> None:
    llm_mode = settings.llm_mode.upper()
    
    if llm_mode == "QWEN" and QWEN_LLM_AVAILABLE and settings.dashscope_api_key:
        # 如果配置中没有指定 system_prompt，使用面试 prompt
        system_prompt = settings.llm_system_prompt or get_interview_system_prompt()
        
        self.llm_service = QwenLLMService(
            api_key=settings.dashscope_api_key,
            model=getattr(settings, 'llm_model', 'qwen-turbo'),
            system_prompt=system_prompt,
        )
```

## Prompt 结构说明

### 角色定义
- 专业、友好、公正的 AI 面试官
- 职责：生成问题、评估回答、引导流程

### 核心原则
1. 专业性
2. 公平性
3. 引导性
4. 效率性
5. 自然性

### 面试流程
1. 开场与介绍（1-2 分钟）
2. 核心问题（15-20 分钟）
3. 候选人提问（3-5 分钟）
4. 结束（1 分钟）

### 问题类型
- 开放性问题
- 行为性问题（STAR 法则）
- 技术性问题
- 情景性问题

### 评估标准
- 评估维度：相关性、完整性、深度、逻辑性、真实性
- 评估等级：优秀、良好、一般、较差

## 自定义 Prompt

如果需要自定义 prompt，可以：

1. **修改 `interview_system_prompt.txt`**：直接编辑文件内容
2. **创建新的 prompt 文件**：在 `prompts/` 目录下创建新文件，然后在代码中加载
3. **动态生成 prompt**：使用 `get_interview_prompt_with_context()` 函数，根据岗位和候选人信息动态生成

## 示例场景

### 场景一：技术岗位面试

```python
job_description = """
岗位：Python 后端工程师
要求：
- 3 年以上 Python 开发经验
- 熟悉 Django、Flask 框架
- 熟悉 MySQL、Redis
- 有微服务架构经验
"""

system_prompt = get_interview_prompt_with_context(
    job_description=job_description,
    interview_stage="核心问题"
)

# 使用该 prompt 的 LLM 会自动生成针对 Python 后端工程师的面试问题
```

### 场景二：产品岗位面试

```python
job_description = """
岗位：产品经理
要求：
- 2 年以上产品经验
- 熟悉用户研究、需求分析
- 有 B 端产品经验
"""

system_prompt = get_interview_prompt_with_context(
    job_description=job_description,
    interview_stage="核心问题"
)
```

## 注意事项

1. **Prompt 长度**：系统 prompt 不宜过长，建议控制在 2000 字以内
2. **上下文管理**：使用 `get_interview_prompt_with_context()` 时，注意控制 JD 和简历的长度
3. **动态调整**：根据面试阶段（开场/核心问题/结束）动态调整 prompt
4. **测试验证**：在实际使用前，建议先用测试用例验证 prompt 效果

## 最佳实践

1. **根据岗位定制**：不同岗位使用不同的 prompt**
2. **分阶段管理**：** 将面试分为不同阶段，每个阶段使用不同的 prompt 或上下文
3. **持续优化**：根据实际使用效果，不断优化 prompt 内容
4. **A/B 测试**：可以准备多个版本的 prompt，进行 A/B 测试

## 相关文件

- `backend/app/services/llm_qwen.py`: LLM 服务实现
- `backend/app/services/orchestrator.py`: 服务编排，LLM 服务初始化
- `backend/app/config.py`: 配置文件，包含 `llm_system_prompt` 配置项
