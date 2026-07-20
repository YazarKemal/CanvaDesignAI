"use client";

import type { ChatMessage as ChatMessageType } from "@/types";
import ChatPromptCard from "./ChatPromptCard";
import { useEffect, useRef } from "react";

export default function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === "user";
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isUser && containerRef.current) {
      containerRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [isUser]);

  return (
    <div
      ref={containerRef}
      className={`message-enter flex w-full ${isUser ? "justify-end" : "justify-start"}`}
    >
      {isUser ? (
        <div className="max-w-[80%] rounded-2xl rounded-br-md bg-dark-600 px-4 py-3 md:max-w-2xl">
          <p className="text-sm leading-relaxed text-zinc-200 whitespace-pre-wrap">
            {message.content}
          </p>
        </div>
      ) : (
        <div className="flex w-full max-w-2xl flex-col gap-2">
          {message.content && (
            <p className="text-sm leading-relaxed text-zinc-400">
              {message.content}
            </p>
          )}
          {message.promptCard && <ChatPromptCard data={message.promptCard} />}
        </div>
      )}
    </div>
  );
}
