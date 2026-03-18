/** WebSocket 消息类型定义 */

export type MessageType =
  | "audio_chunk"
  | "audio_end"
  | "resume_context"
  | "job_context"
  | "status"
  | "asr_result"
  | "llm_result"
  | "llm_stream"
  | "video_chunk"
  | "tingwu_result"
  | "tts_audio"
  | "tts_audio_chunk"
  | "text_input"
  | "interrupt"
  | "interrupted"
  | "complete"
  | "error"
  | "end_interview"
  | "interview_ended"
  | "evaluation_result";

export interface WebSocketMessage {
  type: MessageType;
  data?: string;
  stage?: "asr" | "llm" | "tts" | "thg" | "tingwu";
  message?: string;
  text?: string;
  resume_id?: string;
  job_title?: string;
  text_length?: number;
  frame_index?: number;
  timestamp_ms?: number;
  chunk_index?: number;
  is_first?: boolean;
  is_final?: boolean;
  sentence_index?: number;
  enable_qa?: boolean;
}

export interface AudioChunkMessage extends WebSocketMessage {
  type: "audio_chunk";
  data: string;
}

export interface AudioEndMessage extends WebSocketMessage {
  type: "audio_end";
}

export interface StatusMessage extends WebSocketMessage {
  type: "status";
  stage: "asr" | "llm" | "tts" | "thg";
  message: string;
}

export interface ASRResultMessage extends WebSocketMessage {
  type: "asr_result";
  text: string;
  enable_qa?: boolean;  // 是否启用LLM实时问答
}

export interface LLMResultMessage extends WebSocketMessage {
  type: "llm_result";
  text: string;
}

export interface VideoChunkMessage extends WebSocketMessage {
  type: "video_chunk";
  data: string;
  frame_index?: number;
  timestamp_ms?: number;
}

export interface TTSAudioMessage extends WebSocketMessage {
  type: "tts_audio";
  data: string;  // base64 encoded audio data
}

export interface TingwuResultMessage extends WebSocketMessage {
  type: "tingwu_result";
  text: string;
  is_final?: boolean;  // 是否为完整句子（SentenceEnd）
  message_name?: string;  // 消息类型名称
  raw: any;
}

export interface TextInputMessage extends WebSocketMessage {
  type: "text_input";
  text: string;
  enable_qa?: boolean;  // 是否启用LLM实时问答
}

export interface CompleteMessage extends WebSocketMessage {
  type: "complete";
}

export interface ErrorMessage extends WebSocketMessage {
  type: "error";
  message: string;
}

export interface TTSAudioChunkMessage extends WebSocketMessage {
  type: "tts_audio_chunk";
  data: string;  // base64 encoded audio chunk
  chunk_index: number;
  is_first: boolean;
  is_final: boolean;
  sentence_index?: number;
}

export interface LLMStreamMessage extends WebSocketMessage {
  type: "llm_stream";
  text: string;
  sentence_index: number;
  is_final: boolean;
}

export interface InterruptMessage extends WebSocketMessage {
  type: "interrupt";
}

export interface InterruptedMessage extends WebSocketMessage {
  type: "interrupted";
  message: string;
}

export interface EndInterviewMessage extends WebSocketMessage {
  type: "end_interview";
}

export interface InterviewEndedMessage extends WebSocketMessage {
  type: "interview_ended";
  message: string;
}

export interface EvaluationDimension {
  name: string;
  score: number;  // 0-100
  description: string;
}

export interface EvaluationResult {
  dimensions: EvaluationDimension[];
  summary: string;
  suggestions: string;
}

export interface EvaluationResultMessage extends WebSocketMessage {
  type: "evaluation_result";
  data: EvaluationResult;
}

export interface ResumeContextMessage extends WebSocketMessage {
  type: "resume_context";
  resume_id?: string;
  text_length?: number;
}

export interface JobContextMessage extends WebSocketMessage {
  type: "job_context";
  job_title?: string;
  text_length?: number;
}
