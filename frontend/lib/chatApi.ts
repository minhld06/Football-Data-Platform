import type { ChatModelInfo } from "./types";

const CHAT_API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type ChatResult<T> = { ok: true; data: T } | { ok: false; error: string };

export async function getChatModels(): Promise<ChatResult<ChatModelInfo[]>> {
  try {
    const res = await fetch(`${CHAT_API_URL}/api/chat/models`);
    if (!res.ok) {
      return { ok: false, error: `Failed to load models: ${res.status}` };
    }
    const data = (await res.json()) as ChatModelInfo[];
    return { ok: true, data };
  } catch {
    return { ok: false, error: "Network error while loading models" };
  }
}

export interface SendChatMessageArgs {
  message: string;
  conversationId: string;
  model: string;
}

export interface ChatApiResponse {
  conversation_id: string;
  answer: string;
  sql: string | null;
}

export async function sendChatMessage({
  message,
  conversationId,
  model,
}: SendChatMessageArgs): Promise<ChatResult<ChatApiResponse>> {
  try {
    const res = await fetch(`${CHAT_API_URL}/api/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        model,
      }),
    });
    if (!res.ok) {
      return { ok: false, error: `Chat request failed: ${res.status}` };
    }
    const data = (await res.json()) as ChatApiResponse;
    return { ok: true, data };
  } catch {
    return { ok: false, error: "Network error while sending message" };
  }
}