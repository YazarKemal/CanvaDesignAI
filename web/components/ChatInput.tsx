"use client";

import { KeyboardEvent } from "react";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onHistoryPrev: () => void;
  disabled?: boolean;
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  onHistoryPrev,
  disabled,
}: ChatInputProps) {
  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      onSubmit();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      onHistoryPrev();
    }
  }

  return (
    <div className="relative w-full">
      {/* Label interrupting the top border, terminal-fieldset style. */}
      <span className="absolute -top-2 left-4 bg-black px-2 text-xs text-zinc-500">
        Describe a design
      </span>

      <div className="flex items-stretch border border-zinc-700">
        <span className="flex select-none items-center pl-4 pr-2 text-zinc-500">
          &gt;
        </span>
        <input
          autoFocus
          type="text"
          value={value}
          disabled={disabled}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="a grand opening flyer for a specialty coffee shop"
          className="flex-1 bg-transparent py-3 pr-3 text-sm text-white placeholder-zinc-600 outline-none disabled:opacity-50"
        />
        <button
          type="button"
          onClick={onSubmit}
          disabled={disabled}
          className="select-none border-l border-zinc-700 bg-white px-5 text-sm font-bold text-black transition-colors hover:bg-zinc-300 disabled:cursor-not-allowed disabled:bg-zinc-600 disabled:text-zinc-300"
        >
          generate
        </button>
      </div>
    </div>
  );
}
