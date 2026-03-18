/**
 * 听悟消息处理工具
 * 
 * 用于处理阿里云听悟实时转写返回的消息，支持：
 * - SentenceBegin: 句子开始
 * - TranscriptionResultChanged: 转写结果变化（中间结果）
 * - SentenceEnd: 句子结束（最终结果，可能包含校准后的文字）
 * 
 * 该工具可以在多个项目中复用。
 */

import type { TingwuResultMessage } from "../types";

export interface TingwuSegment {
  id: string;
  text: string;
  is_final?: boolean;
  message_name?: string;
  raw: any;
  timestamp: number;
}

export interface ProcessTingwuMessageResult {
  segments: TingwuSegment[];
  shouldTriggerASR: boolean; // 是否应该触发 ASR 流程（SentenceEnd 且有文本）
  asrText?: string; // 如果应该触发 ASR，返回的文本
}

/**
 * 处理听悟消息，更新 segments 列表
 * 
 * @param currentSegments 当前的 segments 列表
 * @param message 听悟消息
 * @returns 处理后的 segments 列表和是否需要触发 ASR 流程
 */
export function processTingwuMessage(
  currentSegments: TingwuSegment[],
  message: TingwuResultMessage
): ProcessTingwuMessageResult {
  const messageName = message.message_name || "";
  const messageText = message.text || "";
  const timestamp = Date.now();
  
  let newSegments: TingwuSegment[];
  let shouldTriggerASR = false;
  let asrText: string | undefined;

  // 生成唯一 ID
  const generateId = () => `${timestamp}-${Math.random()}`;

  // 根据消息类型处理
  if (messageName === "SentenceBegin") {
    // 句子开始：创建新的 segment（即使 text 为空）
    const newSegment: TingwuSegment = {
      id: generateId(),
      text: "", // SentenceBegin 时 text 为空
      is_final: false,
      message_name: messageName,
      raw: message.raw,
      timestamp,
    };
    newSegments = [...currentSegments, newSegment];
  } else if (messageName === "TranscriptionResultChanged") {
    // 转写结果变化：更新当前句子的中间结果
    const lastIndex = currentSegments.length - 1;
    if (lastIndex >= 0 && !currentSegments[lastIndex].is_final) {
      // 更新最后一个非 final 的 segment
      newSegments = [...currentSegments];
      newSegments[lastIndex] = {
        ...newSegments[lastIndex],
        text: messageText,
        message_name: messageName,
        raw: message.raw,
        timestamp,
      };
    } else {
      // 如果没有当前句子，创建新的 segment
      const newSegment: TingwuSegment = {
        id: generateId(),
        text: messageText,
        is_final: false,
        message_name: messageName,
        raw: message.raw,
        timestamp,
      };
      newSegments = [...currentSegments, newSegment];
    }
  } else if (messageName === "SentenceEnd") {
    // 句子结束：确认当前句子为最终结果
    const lastIndex = currentSegments.length - 1;
    if (lastIndex >= 0 && !currentSegments[lastIndex].is_final) {
      // 将最后一个 segment 标记为 final，并更新 text（可能包含校准后的文字）
      newSegments = [...currentSegments];
      const finalText = messageText || newSegments[lastIndex].text; // 使用校准后的文字，如果没有则保留之前的
      newSegments[lastIndex] = {
        ...newSegments[lastIndex],
        text: finalText,
        is_final: true,
        message_name: messageName,
        raw: message.raw,
        timestamp,
      };
      
      // 如果有文本，应该触发 ASR 流程
      if (finalText && finalText.trim()) {
        shouldTriggerASR = true;
        asrText = finalText.trim();
      }
    } else if (lastIndex >= 0 && currentSegments[lastIndex].is_final) {
      // 如果最后一个 segment 已经是 final，检查文本是否相同
      const lastSegment = currentSegments[lastIndex];
      const finalText = messageText || lastSegment.text;
      
      // 如果文本相同，只更新 raw 和 timestamp，不创建新 segment
      if (lastSegment.text.trim() === finalText.trim()) {
        newSegments = [...currentSegments];
        newSegments[lastIndex] = {
          ...lastSegment,
          raw: message.raw,
          timestamp,
        };
      } else {
        // 文本不同，创建新的 final segment
        const newSegment: TingwuSegment = {
          id: generateId(),
          text: finalText,
          is_final: true,
          message_name: messageName,
          raw: message.raw,
          timestamp,
        };
        newSegments = [...currentSegments, newSegment];
      }
      
      // 如果有文本，应该触发 ASR 流程
      if (finalText && finalText.trim()) {
        shouldTriggerASR = true;
        asrText = finalText.trim();
      }
    } else {
      // 如果没有当前句子，创建新的 final segment
      const newSegment: TingwuSegment = {
        id: generateId(),
        text: messageText,
        is_final: true,
        message_name: messageName,
        raw: message.raw,
        timestamp,
      };
      newSegments = [...currentSegments, newSegment];
      
      // 如果有文本，应该触发 ASR 流程
      if (messageText && messageText.trim()) {
        shouldTriggerASR = true;
        asrText = messageText.trim();
      }
    }
  } else {
    // 其他消息类型：根据 is_final 判断
    const newSegment: TingwuSegment = {
      id: generateId(),
      text: messageText,
      is_final: message.is_final || false,
      message_name: messageName,
      raw: message.raw,
      timestamp,
    };
    
    if (message.is_final) {
      newSegments = [...currentSegments, newSegment];
      // 如果是最终结果且有文本，应该触发 ASR 流程
      if (messageText && messageText.trim()) {
        shouldTriggerASR = true;
        asrText = messageText.trim();
      }
    } else {
      // 中间结果：更新最后一个非 final 的 segment
      const lastIndex = currentSegments.length - 1;
      if (lastIndex >= 0 && !currentSegments[lastIndex].is_final) {
        newSegments = [...currentSegments];
        newSegments[lastIndex] = newSegment;
      } else {
        newSegments = [...currentSegments, newSegment];
      }
    }
  }

  return {
    segments: newSegments,
    shouldTriggerASR,
    asrText,
  };
}

