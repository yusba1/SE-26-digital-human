/** WebSocket Hook */
import { useEffect, useRef, useState, useCallback } from "react";
import { WebSocketClient } from "../services/websocket";
import type { WebSocketMessage } from "../types";

export interface UseWebSocketReturn {
  ws: WebSocketClient | null;
  isConnected: boolean;
  send: (message: WebSocketMessage) => void;
  on: (type: string, handler: (message: WebSocketMessage) => void) => void;
  off: (type: string, handler: (message: WebSocketMessage) => void) => void;
}

export function useWebSocket(url?: string): UseWebSocketReturn {
  const wsRef = useRef<WebSocketClient | null>(null);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    // 创建 WebSocket 客户端
    const ws = new WebSocketClient(url);
    wsRef.current = ws;

    // 注册连接状态处理器
    ws.onOpen(() => setIsConnected(true));
    ws.onClose(() => setIsConnected(false));

    // 连接
    ws.connect();

    // 清理函数
    return () => {
      ws.disconnect();
    };
  }, [url]);

  const send = useCallback((message: WebSocketMessage) => {
    wsRef.current?.send(message);
  }, []);

  const on = useCallback((type: string, handler: (message: WebSocketMessage) => void) => {
    wsRef.current?.on(type, handler);
  }, []);

  const off = useCallback((type: string, handler: (message: WebSocketMessage) => void) => {
    wsRef.current?.off(type, handler);
  }, []);

  return {
    ws: wsRef.current,
    isConnected,
    send,
    on,
    off,
  };
}

