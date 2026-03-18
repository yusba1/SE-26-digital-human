"""面试评价服务"""
import json
import logging
import asyncio
from typing import Dict, Any, List, Optional
from pathlib import Path

from app.services.llm_service import LLMService
from app.config import settings

logger = logging.getLogger(__name__)

# 尝试导入通义千问 LLM 服务
try:
    from app.services.llm_qwen import QwenLLMService, DASHSCOPE_AVAILABLE
    QWEN_LLM_AVAILABLE = DASHSCOPE_AVAILABLE
except ImportError:
    QwenLLMService = None
    QWEN_LLM_AVAILABLE = False


def load_evaluation_prompt() -> str:
    """加载评价Prompt"""
    prompt_path = Path(__file__).parent / "prompts" / "evaluation_prompt.txt"
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        logger.error(f"评价Prompt文件不存在: {prompt_path}")
        return ""


class EvaluationService:
    """面试评价服务"""
    
    def __init__(self, llm_service: Optional[LLMService] = None):
        """
        初始化评价服务
        
        Args:
            llm_service: LLM服务实例，如果为None则根据配置自动创建
        """
        self.evaluation_prompt = load_evaluation_prompt()
        if not self.evaluation_prompt:
            logger.warning("[Evaluation] 评价Prompt为空，将使用默认Prompt")
            self.evaluation_prompt = self._get_default_prompt()
        
        if llm_service is not None:
            self.llm_service = llm_service
            logger.info(f"[Evaluation] 使用提供的LLM服务: {type(self.llm_service).__name__}")
        else:
            logger.info("[Evaluation] 未提供LLM服务，根据配置自动创建")
            self._init_llm_service()
    
    def _init_llm_service(self):
        """初始化LLM服务"""
        if QWEN_LLM_AVAILABLE and settings.dashscope_api_key:
            logger.info("[Evaluation] 使用 QwenLLMService 进行评价生成")
            try:
                self.llm_service = QwenLLMService(
                    api_key=settings.dashscope_api_key,
                    model=getattr(settings, 'llm_model', 'qwen-turbo'),
                    system_prompt=self.evaluation_prompt
                )
                logger.info(f"[Evaluation] QwenLLMService 初始化成功，model: {getattr(settings, 'llm_model', 'qwen-turbo')}")
            except Exception as e:
                logger.error(f"[Evaluation] QwenLLMService 初始化失败: {e}", exc_info=True)
                from app.services.llm_service import MockLLMService
                self.llm_service = MockLLMService()
        else:
            if not QWEN_LLM_AVAILABLE:
                logger.warning("[Evaluation] QwenLLM不可用（dashscope未安装），使用MockLLMService")
            elif not settings.dashscope_api_key:
                logger.warning("[Evaluation] dashscope_api_key未配置，使用MockLLMService")
            from app.services.llm_service import MockLLMService
            self.llm_service = MockLLMService()
    
    def _get_default_prompt(self) -> str:
        """获取默认评价Prompt"""
        return """你是一位专业的面试评价专家。请根据面试对话历史，对候选人进行多维度评价。

评价维度：
1. 技术能力（Technical Skills）
2. 沟通表达（Communication）
3. 问题解决（Problem Solving）
4. 团队协作（Teamwork）
5. 学习能力（Learning Ability）

评分标准（严格）：优秀80-100，良好60-79，一般40-59，较差0-39。

输出JSON格式：
{
  "dimensions": [
    {"name": "技术能力", "score": 75, "description": "..."},
    ...
  ],
  "summary": "面试总结（200-300字）",
  "suggestions": "改进建议（200-300字）"
}"""
    
    def _format_conversation_history(self, conversation_history: List[Dict[str, str]]) -> str:
        """
        格式化对话历史为文本
        
        Args:
            conversation_history: 对话历史列表 [{role: str, content: str}]
        
        Returns:
            格式化后的对话文本
        """
        if not conversation_history:
            return "对话历史为空"
        
        formatted_lines = []
        for i, msg in enumerate(conversation_history, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            role_name = "面试官" if role == "assistant" else "候选人"
            formatted_lines.append(f"{i}. [{role_name}] {content}")
        
        return "\n".join(formatted_lines)
    
    def _parse_evaluation_result(self, llm_output: str) -> Dict[str, Any]:
        """
        解析LLM输出为评价结果
        
        Args:
            llm_output: LLM原始输出
        
        Returns:
            解析后的评价结果
        """
        # 尝试提取JSON（可能包含markdown代码块）
        json_str = llm_output.strip()
        
        # 移除可能的markdown代码块标记
        if json_str.startswith("```json"):
            json_str = json_str[7:]
        elif json_str.startswith("```"):
            json_str = json_str[3:]
        
        if json_str.endswith("```"):
            json_str = json_str[:-3]
        
        json_str = json_str.strip()
        
        try:
            result = json.loads(json_str)
            
            # 验证结果格式
            if not isinstance(result, dict):
                raise ValueError("结果不是字典格式")
            
            if "dimensions" not in result:
                raise ValueError("缺少dimensions字段")
            
            if not isinstance(result["dimensions"], list):
                raise ValueError("dimensions不是列表")
            
            # 验证每个维度
            for dim in result["dimensions"]:
                if not isinstance(dim, dict):
                    raise ValueError("维度项不是字典")
                if "name" not in dim or "score" not in dim:
                    raise ValueError("维度缺少name或score字段")
                score = dim["score"]
                if not isinstance(score, (int, float)) or score < 0 or score > 100:
                    logger.warning(f"评分超出范围: {score}，将限制在0-100")
                    dim["score"] = max(0, min(100, int(score)))
            
            return result
            
        except json.JSONDecodeError as e:
            logger.error(f"[Evaluation] JSON解析失败: {e}")
            logger.error(f"[Evaluation] 原始输出: {llm_output[:500]}")
            # 返回默认结果
            return self._get_default_result()
        except ValueError as e:
            logger.error(f"[Evaluation] 结果验证失败: {e}")
            return self._get_default_result()
    
    def _get_default_result(self) -> Dict[str, Any]:
        """获取默认评价结果（用于错误情况）"""
        llm_service_name = type(self.llm_service).__name__ if hasattr(self, 'llm_service') and self.llm_service else "Unknown"
        error_msg = f"LLM服务({llm_service_name})调用失败，请检查配置和网络连接"
        return {
            "dimensions": [
                {"name": "技术能力", "score": 50, "description": error_msg},
                {"name": "沟通表达", "score": 50, "description": error_msg},
                {"name": "问题解决", "score": 50, "description": error_msg},
                {"name": "团队协作", "score": 50, "description": error_msg},
                {"name": "学习能力", "score": 50, "description": error_msg}
            ],
            "summary": f"由于技术原因，无法生成详细评价。{error_msg}",
            "suggestions": "请检查：1) LLM服务配置是否正确（dashscope_api_key） 2) 网络连接是否正常 3) 查看后端日志获取详细错误信息"
        }
    
    async def evaluate_interview(
        self,
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
                "dimensions": [
                    {"name": str, "score": int, "description": str},
                    ...
                ],
                "summary": str,
                "suggestions": str
            }
        """
        if not conversation_history:
            logger.warning("[Evaluation] 对话历史为空，返回默认评价")
            return self._get_default_result()
        
        try:
            # 格式化对话历史
            conversation_text = self._format_conversation_history(conversation_history)
            
            # 构建评价请求，包含完整的评价prompt
            # 这样即使llm_service的system_prompt是面试相关的，也能正确生成评价
            evaluation_request = f"""{self.evaluation_prompt}

以下是面试对话历史：

{conversation_text}

"""
            
            if job_description:
                evaluation_request += f"\n岗位要求：\n{job_description}\n\n"
            
            evaluation_request += "\n请根据以上对话历史，严格按照评分标准进行评价，输出JSON格式结果。"
            
            logger.info(f"[Evaluation] 开始生成评价，对话轮数: {len(conversation_history)}")
            logger.info(f"[Evaluation] 使用LLM服务: {type(self.llm_service).__name__}")
            
            # 检查LLM服务是否可用
            if isinstance(self.llm_service, type(None)):
                logger.error("[Evaluation] LLM服务未初始化")
                return self._get_default_result()
            
            # 调用LLM生成评价（使用与orchestrator相同的API）
            logger.debug(f"[Evaluation] 发送评价请求，请求长度: {len(evaluation_request)}")
            llm_output = await self.llm_service.optimize_text(evaluation_request)
            
            if not llm_output or not llm_output.strip():
                logger.error("[Evaluation] LLM返回空结果")
                return self._get_default_result()
            
            logger.info(f"[Evaluation] LLM输出长度: {len(llm_output)}")
            logger.debug(f"[Evaluation] LLM输出前500字符: {llm_output[:500]}")
            
            # 解析评价结果
            result = self._parse_evaluation_result(llm_output)
            
            # 检查解析结果是否是默认结果（说明解析失败）
            if result.get("summary") == "由于技术原因，无法生成详细评价。":
                logger.warning("[Evaluation] 评价解析失败，返回默认结果")
                logger.debug(f"[Evaluation] 原始LLM输出: {llm_output}")
            else:
                logger.info(f"[Evaluation] 评价生成完成，维度数: {len(result.get('dimensions', []))}")
            
            return result
            
        except Exception as e:
            logger.error(f"[Evaluation] 评价生成失败: {e}", exc_info=True)
            logger.error(f"[Evaluation] 异常类型: {type(e).__name__}")
            import traceback
            logger.error(f"[Evaluation] 异常堆栈: {traceback.format_exc()}")
            return self._get_default_result()
