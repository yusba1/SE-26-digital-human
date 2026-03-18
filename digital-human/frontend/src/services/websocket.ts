/** WebSocket 客户端服务 */
import type { WebSocketMessage } from "../types";

export class WebSocketClient {
  private ws: WebSocket | null = null;
  private url: string;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 5;
  private reconnectDelay = 1000;
  private messageHandlers: Map<string, ((message: WebSocketMessage) => void)[]> = new Map();
  private onOpenHandlers: (() => void)[] = [];
  private onCloseHandlers: (() => void)[] = [];
  private onErrorHandlers: ((error: Event) => void)[] = [];

  constructor(url: string = "ws://localhost:8000/api/ws") {
    this.url = url;
  }

  /**
   * 连接到 WebSocket 服务器
   */
  connect(): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      return;
    }

    try {
      this.ws = new WebSocket(this.url);

      this.ws.onopen = () => {
        console.log("WebSocket 连接已建立");
        this.reconnectAttempts = 0;
        this.onOpenHandlers.forEach((handler) => handler());
      };

      this.ws.onmessage = (event) => {
        try {
          const message: WebSocketMessage = JSON.parse(event.data);
          // 高频消息（如 video_chunk / tingwu_result）打印会显著拖慢页面
          if (message.type !== "video_chunk" && message.type !== "tingwu_result") {
            console.log("WebSocket 收到消息:", message.type, message);
          }
          const handlers = this.messageHandlers.get(message.type) || [];
          handlers.forEach((handler) => handler(message));
        } catch (error) {
          console.error("解析消息失败:", error);
        }
      };

      this.ws.onclose = () => {
        console.log("WebSocket 连接已关闭");
        this.onCloseHandlers.forEach((handler) => handler());
        this.attemptReconnect();
      };

      this.ws.onerror = (error) => {
        console.error("WebSocket 错误:", error);
        this.onErrorHandlers.forEach((handler) => handler(error));
      };
    } catch (error) {
      console.error("创建 WebSocket 连接失败:", error);
      this.attemptReconnect();
    }
  }

  /**
   * 尝试重连
   */
  private attemptReconnect(): void {
    if (this.reconnectAttempts >= this.maxReconnectAttempts) {
      console.error("达到最大重连次数，停止重连");
      return;
    }

    this.reconnectAttempts++;
    const delay = this.reconnectDelay * this.reconnectAttempts;

    console.log(`将在 ${delay}ms 后尝试重连 (${this.reconnectAttempts}/${this.maxReconnectAttempts})`);

    setTimeout(() => {
      this.connect();
    }, delay);
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }

  /**
   * 发送消息
   */
  send(message: WebSocketMessage): void {
    if (this.ws?.readyState === WebSocket.OPEN) {
      const messageStr = JSON.stringify(message);
      console.log("[WebSocket] 发送消息:", message.type, messageStr.substring(0, 100));
      this.ws.send(messageStr);
    } else {
      console.error("WebSocket 未连接，无法发送消息。当前状态:", this.ws?.readyState);
    }
  }

  /**
   * 注册消息处理器
   */
  on(type: string, handler: (message: WebSocketMessage) => void): void {
    if (!this.messageHandlers.has(type)) {
      this.messageHandlers.set(type, []);
    }
    this.messageHandlers.get(type)!.push(handler);
  }

  /**
   * 移除消息处理器
   */
  off(type: string, handler: (message: WebSocketMessage) => void): void {
    const handlers = this.messageHandlers.get(type);
    if (handlers) {
      const index = handlers.indexOf(handler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    }
  }

  /**
   * 注册连接打开处理器
   */
  onOpen(handler: () => void): void {
    this.onOpenHandlers.push(handler);
  }

  /**
   * 注册连接关闭处理器
   */
  onClose(handler: () => void): void {
    this.onCloseHandlers.push(handler);
  }

  /**
   * 注册错误处理器
   */
  onError(handler: (error: Event) => void): void {
    this.onErrorHandlers.push(handler);
  }

  /**
   * 获取连接状态
   */
  get readyState(): number {
    return this.ws?.readyState ?? WebSocket.CLOSED;
  }

  /**
   * 是否已连接
   */
  get isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}
