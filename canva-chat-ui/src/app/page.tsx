"use client";

import { useState, useRef, useCallback } from "react";
import type { ChatMessage as ChatMessageType } from "@/types";
import ChatMessage from "@/components/ChatMessage";
import ChatInput from "@/components/ChatInput";

function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).slice(2, 9)}`;
}

const WELCOME_MESSAGE: ChatMessageType = {
  id: "welcome",
  role: "assistant",
  content:
    "Merhaba! 👋 Ben **Canva Prompt Workbench**. Bana nasıl bir tasarım oluşturmak istediğini söyle, sana Canva için optimize edilmiş prompt'lar ve ipuçları hazırlayayım.",
  timestamp: Date.now(),
};

export default function Home() {
  const [messages, setMessages] = useState<ChatMessageType[]>([WELCOME_MESSAGE]);
  const [loading, setLoading] = useState(false);
  const chatContainerRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = useCallback(() => {
    requestAnimationFrame(() => {
      if (chatContainerRef.current) {
        chatContainerRef.current.scrollTop =
          chatContainerRef.current.scrollHeight;
      }
    });
  }, []);

  async function handleSend(text: string) {
    const userMsg: ChatMessageType = {
      id: generateId(),
      role: "user",
      content: text,
      timestamp: Date.now(),
    };

    setMessages((prev) => [...prev, userMsg]);
    setLoading(true);
    scrollToBottom();

    try {
      const res = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ prompt: text }),
      });

      const data = await res.json();

      const assistantMsg: ChatMessageType = {
        id: generateId(),
        role: "assistant",
        content: data.message,
        promptCard: data.promptCard,
        timestamp: Date.now(),
      };

      setMessages((prev) => [...prev, assistantMsg]);
    } catch {
      const errorMsg: ChatMessageType = {
        id: generateId(),
        role: "assistant",
        content: "⚠️ Bir hata oluştu. Lütfen tekrar dene.",
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
      scrollToBottom();
    }
  }

  return (
    <div className="flex h-dvh flex-col bg-dark-900">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-dark-700 bg-dark-900/80 backdrop-blur-sm">
        <div className="mx-auto flex max-w-2xl items-center gap-3 px-4 py-3">
          <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-accent-purple to-accent-cyan text-sm font-bold text-white">
            C
          </div>
          <div>
            <h1 className="text-sm font-semibold text-zinc-200">
              Canva Prompt Workbench
            </h1>
            <p className="text-xs text-dark-400">
              AI-powered design prompt generator
            </p>
          </div>
        </div>
      </header>

      {/* Chat messages */}
      <main
        ref={chatContainerRef}
        className="flex-1 overflow-y-auto px-4 py-6"
      >
        <div className="mx-auto flex max-w-2xl flex-col gap-4">
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}

          {/* Loading indicator */}
          {loading && (
            <div className="flex items-center gap-2 py-2">
              <span className="flex gap-1">
                <span className="h-2 w-2 animate-bounce rounded-full bg-accent-purple [animation-delay:0ms]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-accent-purple [animation-delay:150ms]" />
                <span className="h-2 w-2 animate-bounce rounded-full bg-accent-purple [animation-delay:300ms]" />
              </span>
              <span className="text-xs text-dark-400">
                Generating prompt...
              </span>
            </div>
          )}
        </div>
      </main>

      {/* Bottom input area */}
      <footer className="flex-shrink-0 border-t border-dark-700 bg-dark-900/80 backdrop-blur-sm px-4 py-4">
        <ChatInput onSend={handleSend} disabled={loading} />
      </footer>
    </div>
  );
}
