"use client";

import { useState, type FormEvent } from "react";
import { MessageCircle, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { getChatModels, sendChatMessage } from "@/lib/chatApi";
import type { ChatMessage, ChatModelInfo } from "@/lib/types";

function formatModelOption(model: ChatModelInfo): string {
  const parts = [model.label];
  if (model.context_window) {
    parts.push(`${Math.round(model.context_window / 1000)}K ctx`);
  }
  if (
    model.prompt_price_per_million != null &&
    model.completion_price_per_million != null
  ) {
    parts.push(
      `$${model.prompt_price_per_million}/$${model.completion_price_per_million} per 1M tok`
    );
  }
  return parts.join(" · ");
}

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [loaded, setLoaded] = useState(false);
  const [models, setModels] = useState<ChatModelInfo[]>([]);
  const [model, setModel] = useState("");
  const [conversationId, setConversationId] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  async function handleOpen() {
    setOpen(true);
    if (loaded) return;
    setLoaded(true);
    setConversationId(crypto.randomUUID());
    const result = await getChatModels();
    if (result.ok) {
      setModels(result.data);
      if (result.data.length > 0) {
        setModel(result.data[0].id);
      }
    }
  }

  function handleModelChange(value: string | null) {
    if (value) setModel(value);
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = input.trim();
    if (!trimmed || sending || !model) return;

    setMessages((prev) => [...prev, { role: "user", content: trimmed }]);
    setInput("");
    setSending(true);

    const result = await sendChatMessage({
      message: trimmed,
      conversationId,
      model,
    });

    if (result.ok) {
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: result.data.answer,
          sql: result.data.sql,
        },
      ]);
    } else {
      setMessages((prev) => [
        ...prev,
        { role: "assistant", content: "Error, please try again later." },
      ]);
    }
    setSending(false);
  }

  if (!open) {
    return (
      <Button
        onClick={handleOpen}
        size="icon-lg"
        className="fixed right-4 bottom-4 z-50 size-12 rounded-full shadow-[0_0_0_4px_var(--background),0_8px_24px_-4px_var(--primary)] hover:shadow-[0_0_0_4px_var(--background),0_8px_28px_-2px_var(--primary)]"
        aria-label="Open chat"
      >
        <MessageCircle className="size-5" />
      </Button>
    );
  }

  return (
    <div className="fixed right-4 bottom-4 z-50 flex h-[32rem] w-80 flex-col overflow-hidden rounded-xl border border-border bg-card text-card-foreground shadow-2xl sm:w-96">
      <div className="h-[3px] w-full bg-primary" />
      <div className="flex items-center justify-between border-b border-border p-3">
        <span className="font-heading text-sm font-semibold tracking-wide uppercase">Football Chat</span>
        <Button
          onClick={() => setOpen(false)}
          size="icon-sm"
          variant="ghost"
          aria-label="Close chat"
        >
          <X className="size-4" />
        </Button>
      </div>

      <div className="border-b border-border p-2">
        <Select value={model} onValueChange={handleModelChange}>
          <SelectTrigger className="w-full">
            <SelectValue placeholder="Select model" />
          </SelectTrigger>
          <SelectContent>
            {models.map((m) => (
              <SelectItem key={m.id} value={m.id}>
                {formatModelOption(m)}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="flex-1 space-y-3 overflow-y-auto p-3">
        {messages.length === 0 && (
          <p className="text-sm text-muted-foreground">
            Ask me about the Premier League or Ligue 1.
          </p>
        )}
        {messages.map((m, i) => (
          <div
            key={i}
            className={
              m.role === "user"
                ? "ml-auto max-w-[85%] rounded-lg bg-primary px-3 py-2 text-sm text-primary-foreground"
                : "mr-auto max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm"
            }
          >
            {m.role === "assistant" ? (
              <ReactMarkdown>{m.content}</ReactMarkdown>
            ) : (
              m.content
            )}
            {m.sql && (
              <details className="mt-2 text-xs">
                <summary className="cursor-pointer text-muted-foreground">
                  SQL ran
                </summary>
                <pre className="mt-1 overflow-x-auto rounded bg-background p-2">
                  {m.sql}
                </pre>
              </details>
            )}
          </div>
        ))}
        {sending && (
          <div className="mr-auto max-w-[85%] rounded-lg bg-muted px-3 py-2 text-sm text-muted-foreground">
            Responding...
          </div>
        )}
      </div>

      <form onSubmit={handleSubmit} className="flex gap-2 border-t p-2">
        <Input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question..."
          disabled={sending}
        />
        <Button type="submit" disabled={sending || !input.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}