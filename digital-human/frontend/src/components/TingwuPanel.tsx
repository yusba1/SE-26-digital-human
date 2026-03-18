import React, { useMemo } from "react";
import type { TingwuSegment } from "../utils/tingwuMessageProcessor";

interface TingwuPanelProps {
  segments: TingwuSegment[];
  isConnected: boolean;
}

export const TingwuPanel: React.FC<TingwuPanelProps> = ({ segments, isConnected }) => {
  // 处理文字显示：区分完整句子和中间结果
  const { finalText, currentPartial } = useMemo(() => {
    // 已确认的完整句子列表（去重，避免重复）
    const finalSentences: string[] = [];
    const seenFinalTexts = new Set<string>();
    // 当前中间结果（最后一个非完整句子的文本）
    let partial = "";

    // 从后往前遍历，找到最后一个非 final 的 segment 作为中间结果
    let lastNonFinalIndex = -1;
    for (let i = segments.length - 1; i >= 0; i--) {
      if (!segments[i].is_final) {
        lastNonFinalIndex = i;
        break;
      }
    }

    // 遍历所有 segments，收集 final sentences 和中间结果
    for (let i = 0; i < segments.length; i++) {
      const segment = segments[i];
      
      if (segment.is_final) {
        // 完整句子：追加到已确认列表（使用校准后的文字）
        // 去重：如果已经添加过相同的文本，跳过
        if (segment.text && segment.text.trim()) {
          const trimmedText = segment.text.trim();
          if (!seenFinalTexts.has(trimmedText)) {
            finalSentences.push(trimmedText);
            seenFinalTexts.add(trimmedText);
          }
        }
      } else if (i === lastNonFinalIndex) {
        // 只处理最后一个非 final 的 segment 作为中间结果
        // 忽略 SentenceBegin（text 为空）和空文本
        if (segment.text && segment.text.trim() && segment.message_name !== "SentenceBegin") {
          partial = segment.text.trim();
        }
      }
    }

    return {
      finalText: finalSentences.join(" "),
      currentPartial: partial,
    };
  }, [segments]);

  // 组合显示文本：已确认句子 + 当前中间结果
  const displayText = useMemo(() => {
    const parts: string[] = [];
    if (finalText) {
      parts.push(finalText);
    }
    if (currentPartial) {
      parts.push(currentPartial);
    }
    return parts.join(" ") || "等待转写结果...";
  }, [finalText, currentPartial]);

  const latest = segments[segments.length - 1];

  return (
    <div className="tingwu-panel">
      <div className="tingwu-header">
        <span className="tingwu-title">实时转写（听悟）</span>
        <span className={`tingwu-status ${isConnected ? "connected" : "disconnected"}`}>{isConnected ? "已连接" : "未连接"}</span>
      </div>

      <div className="tingwu-body">
        <div className="tingwu-text">
          <div className="tingwu-section-title">实时文字</div>
          <div className="tingwu-text-content">
            {displayText}
            {currentPartial && <span className="tingwu-partial-indicator">|</span>}
          </div>
        </div>

        <div className="tingwu-raw">
          <div className="tingwu-section-title">原始参数（raw JSON）</div>
          <div className="tingwu-raw-content">{latest ? <pre>{JSON.stringify(latest.raw, null, 2)}</pre> : <span>暂无数据</span>}</div>
        </div>
      </div>
    </div>
  );
};
