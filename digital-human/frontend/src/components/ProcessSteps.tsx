/** 流程步骤指示组件 */
import { useEffect, useState } from "react";
import type { WebSocketMessage } from "../types";

interface ProcessStepsProps {
  messages: WebSocketMessage[];
}

type Stage = "asr" | "llm" | "tts" | "thg" | null;

export function ProcessSteps({ messages }: ProcessStepsProps) {
  const [currentStage, setCurrentStage] = useState<Stage>(null);
  const [asrText, setAsrText] = useState<string>("");
  const [llmText, setLlmText] = useState<string>("");
  const [isComplete, setIsComplete] = useState<boolean>(false);
  const [ttsCompleted, setTtsCompleted] = useState<boolean>(false);

  useEffect(() => {
    // 如果消息被清空，重置所有状态
    if (messages.length === 0) {
      setCurrentStage(null);
      setAsrText("");
      setLlmText("");
      setIsComplete(false);
      setTtsCompleted(false);
      return;
    }

    // 从后往前遍历，找到最新的状态
    let latestStatus: WebSocketMessage | null = null;
    let latestASR: WebSocketMessage | null = null;
    let latestLLM: WebSocketMessage | null = null;
    let latestComplete: WebSocketMessage | null = null;

    // 从最新消息开始查找（找到最新的即可）
    for (let i = messages.length - 1; i >= 0; i--) {
      const msg = messages[i];

      // 主流程只关心 asr/llm/tts/thg 的状态，忽略 tingwu 的 status
      if (msg.type === "status" && msg.stage !== "tingwu" && !latestStatus) {
        latestStatus = msg;
      }
      if (msg.type === "asr_result" && !latestASR) {
        latestASR = msg;
      }
      if (msg.type === "llm_result" && !latestLLM) {
        latestLLM = msg;
      }
      if (msg.type === "complete" && !latestComplete) {
        latestComplete = msg;
      }

      // 如果都找到了，可以提前退出
      if (latestStatus && latestASR && latestLLM && latestComplete) {
        break;
      }
    }

    // 更新状态
    if (latestComplete) {
      setCurrentStage(null);
      setIsComplete(true);
    } else if (latestStatus) {
      setIsComplete(false);
      const newStage = latestStatus.stage as Stage;
      setCurrentStage(newStage);

      // 如果进入 THG 阶段，说明 TTS 已完成
      if (newStage === "thg") {
        setTtsCompleted(true);
      }
    }

    if (latestASR) {
      setAsrText(latestASR.text || "");
    }

    if (latestLLM) {
      setLlmText(latestLLM.text || "");
    }
  }, [messages]);

  return (
    <div className="process-steps">
      <div className={`step ${currentStage === "asr" ? "active" : asrText || isComplete ? "completed" : ""}`}>
        <div className="step-number">1</div>
        <div className="step-label">ASR</div>
      </div>
      <div className="step-connector"></div>
      <div className={`step ${currentStage === "llm" ? "active" : llmText || isComplete ? "completed" : ""}`}>
        <div className="step-number">2</div>
        <div className="step-label">LLM</div>
      </div>
      <div className="step-connector"></div>
      <div className={`step ${currentStage === "tts" ? "active" : ttsCompleted || currentStage === "thg" || isComplete ? "completed" : ""}`}>
        <div className="step-number">3</div>
        <div className="step-label">TTS</div>
      </div>
      <div className="step-connector"></div>
      <div className={`step ${currentStage === "thg" ? "active" : isComplete ? "completed" : ""}`}>
        <div className="step-number">4</div>
        <div className="step-label">THG</div>
      </div>
    </div>
  );
}

