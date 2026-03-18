/** 状态面板组件 - 只显示听悟实时转写 */
import type { TingwuSegment } from "../utils/tingwuMessageProcessor";
import { TingwuPanel } from "./TingwuPanel";

interface StatusPanelProps {
  messages: any[];  // 保留接口兼容性，但不使用
  tingwuSegments?: TingwuSegment[];
  isTingwuConnected?: boolean;
}

export function StatusPanel({ tingwuSegments = [], isTingwuConnected }: StatusPanelProps) {
  return (
    <div className="status-panel">
      {/* 听悟实时转写 */}
      <TingwuPanel segments={tingwuSegments} isConnected={!!isTingwuConnected} />
    </div>
  );
}
