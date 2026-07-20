"use client";

import { useEffect, useState } from "react";
import type { Brand, BrandsResponse } from "@/lib/types";

interface BrandSelectProps {
  selected: string | null;
  onChange: (slug: string | null) => void;
}

export function BrandSelect({ selected, onChange }: BrandSelectProps) {
  const [brands, setBrands] = useState<Brand[]>([]);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/brands")
      .then((res) => res.json())
      .then((data: BrandsResponse) => {
        if (!cancelled) setBrands(data.brands ?? []);
      })
      .catch(() => {
        /* no brands available -- picker just stays empty */
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (brands.length === 0) return null;

  return (
    <div className="mt-2 flex flex-wrap items-center gap-1.5 text-xs">
      <span className="text-zinc-600">brand:</span>
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
      {brands.map((brand) => (
        <button
          key={brand.slug}
          type="button"
          onClick={() => onChange(brand.slug)}
          className={`border px-2 py-0.5 transition-colors ${
            selected === brand.slug
              ? "border-white bg-white text-black"
              : "border-zinc-700 text-zinc-500 hover:border-zinc-500"
          }`}
        >
          {brand.name}
        </button>
      ))}
    </div>
  );
}
