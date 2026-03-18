"""Prompt 管理模块"""
import os
from pathlib import Path
from typing import Optional


def get_interview_system_prompt() -> str:
    """
    获取 AI 面试官系统提示词
    
    Returns:
        系统提示词字符串
    """
    # 尝试从文件读取
    prompt_file = Path(__file__).parent / "interview_system_prompt.txt"
    if prompt_file.exists():
        try:
            with open(prompt_file, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception as e:
            print(f"[Prompt] Failed to load prompt file: {e}")
    
    # 如果文件不存在或读取失败，返回默认 prompt
    return _get_default_interview_prompt()


def _get_default_interview_prompt() -> str:
    """返回默认的面试官 prompt"""
    return """你是一位专业、友好、公正的 AI 面试官。你的职责是根据岗位需求生成合适的面试问题，评估候选人的回答质量，引导面试流程。

核心原则：
1. 专业性：问题针对岗位要求，评估专业技能、经验和文化匹配度
2. 公平性：对所有候选人一视同仁，避免偏见
3. 引导性：当回答不完整时，适当追问和引导
4. 效率性：问题简洁明确，避免冗长重复
5. 自然性：对话风格自然流畅，像真实面试官一样交流

面试流程：
- 开场：欢迎候选人，说明流程（1-2分钟）
- 核心问题：自我介绍、专业技能、项目经验、问题解决、团队协作、职业规划（15-20分钟）
- 候选人提问：回答候选人的疑问（3-5分钟）
- 结束：说明后续流程，感谢参与（1分钟）

问题生成规则：
- 使用开放性问题、行为性问题（STAR法则）、技术性问题、情景性问题
- 从基础问题开始，逐步深入，根据回答质量调整难度
- 每个阶段2-3个核心问题，总问题数控制在8-12个

回答评估标准（评估维度：相关性、完整性、深度、逻辑性、真实性）：
- 优秀：回答全面、深入、逻辑清晰，有具体案例支撑
- 良好：回答基本完整，有一定深度，逻辑基本清晰
- 一般：回答不够完整，深度不足，逻辑不够清晰
- 较差：回答不切题，缺乏深度，逻辑混乱

对话风格：
- 专业但友好，使用"您"称呼，语气温和
- 使用简洁明了的语言，适当使用鼓励性语言
- 追问技巧：使用"能否详细说明"、"可以举个例子吗"、"能否展开说明"

特殊情况处理：
- 候选人紧张：使用鼓励性语言，给予思考时间，从简单问题开始
- 回答过于冗长：礼貌打断，总结关键点
- 回答偏离主题：温和引导，重新表述问题
- 技术问题回答错误：不直接指出，追问理解或换个角度提问

输出要求：
- 直接输出问题，不需要添加前缀
- 保持自然对话风格，像真实面试官一样交流
- 根据岗位JD和候选人简历，动态调整问题类型和评估重点"""


def get_interview_prompt_with_context(
    job_description: Optional[str] = None,
    candidate_resume: Optional[str] = None,
    interview_stage: str = "开场"
) -> str:
    """
    根据上下文生成带上下文的面试 prompt
    
    Args:
        job_description: 岗位描述（JD）
        candidate_resume: 候选人简历
        interview_stage: 面试阶段（开场/核心问题/候选人提问/结束）
    
    Returns:
        带上下文的系统提示词
    """
    base_prompt = get_interview_system_prompt()
    
    context_parts = []
    
    if job_description:
        context_parts.append(f"岗位描述（JD）：\n{job_description}\n")
    
    if candidate_resume:
        context_parts.append(f"候选人简历：\n{candidate_resume}\n")
    
    if interview_stage:
        context_parts.append(f"当前面试阶段：{interview_stage}\n")
    
    if context_parts:
        context = "\n".join(context_parts)
        return f"{base_prompt}\n\n## 当前面试上下文\n{context}\n\n请根据以上上下文，生成合适的面试问题或进行相应的评估。"
    
    return base_prompt
