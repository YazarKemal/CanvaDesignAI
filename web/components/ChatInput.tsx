"use client";

import { KeyboardEvent, useRef } from "react";

interface ChatInputProps {
  value: string;
  onChange: (value: string) => void;
  onSubmit: () => void;
  onHistoryPrev: () => void;
  disabled?: boolean;
  /** Ghost-text suggestion shown as a dim overlay when the input is empty. */
  suggestion?: string;
  /** Called after the user accepts the current suggestion (→ key). */
  onSuggestionAccept?: () => void;
}

export function ChatInput({
  value,
  onChange,
  onSubmit,
  onHistoryPrev,
  disabled,
  suggestion,
  onSuggestionAccept,
}: ChatInputProps) {
  const inputRef = useRef<HTMLInputElement>(null);

  function handleKeyDown(event: KeyboardEvent<HTMLInputElement>) {
    if (event.key === "Enter") {
      event.preventDefault();
      onSubmit();
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      onHistoryPrev();
    } else if (event.key === "ArrowRight" && !value && suggestion) {
      // Accept ghost-text suggestion — fill input and move cursor to end.
      event.preventDefault();
      onChange(suggestion);
      onSuggestionAccept?.();
      // Place cursor at end on next render frame (React 19 controlled input).
      requestAnimationFrame(() => {
        const el = inputRef.current;
        if (el) {
          el.setSelectionRange(suggestion.length, suggestion.length);
        }
      });
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

        {/* Ghost-text overlay + input wrapper */}
        <div className="relative flex-1">
          {/* Ghost suggestion — sits behind the transparent input, only visible when value is empty */}
          {!value && suggestion && (
            <span className="pointer-events-none absolute inset-y-0 left-0 flex items-center overflow-hidden whitespace-nowrap pl-3 pr-3 text-sm text-zinc-700 select-none" aria-hidden="true">
              {suggestion}
            </span>
          )}

          <input
            ref={inputRef}
            autoFocus
            type="text"
            value={value}
            disabled={disabled}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={suggestion ? undefined : "a grand opening flyer for a specialty coffee shop"}
            className="relative z-10 flex-1 bg-transparent py-3 pl-3 pr-3 text-sm text-white outline-none disabled:opacity-50 w-full"
          />
        </div>

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
