"use client";

import { useEffect, useState } from "react";
import type { Style, StylesResponse } from "@/lib/types";

interface StyleSelectProps {
  selected: string | null;
  onChange: (slug: string | null) => void;
}

export function StyleSelect({ selected, onChange }: StyleSelectProps) {
  const [styles, setStyles] = useState<Style[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/styles")
      .then((res) => res.json())
      .then((data: StylesResponse) => {
        if (!cancelled) setStyles(data.styles ?? []);
      })
      .catch(() => {
        /* no styles available -- picker just stays empty */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (styles.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-zinc-600">style:</span>
      <button
        type="button"
        onClick={() => onChange(null)}
        className={`border px-2 py-0.5 transition-colors ${
          selected === null
            ? "border-white bg-white text-black"
            : "border-zinc-700 text-zinc-500 hover:border-zinc-500"
        }`}
      >
        none
      </button>
      {styles.map((style) => (
        <button
          key={style.slug}
          type="button"
          title={style.description}
          onClick={() => onChange(style.slug)}
          className={`border px-2 py-0.5 transition-colors ${
            selected === style.slug
              ? "border-white bg-white text-black"
              : "border-zinc-700 text-zinc-500 hover:border-zinc-500"
          }`}
        >
          {style.name}
        </button>
      ))}
    </div>
  );
}
