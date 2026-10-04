"use client";

import { useState } from "react";
import { IconBuilding } from "./ui/icons";

interface PropertyImageProps {
  src: string | null;
  alt: string;
  sourceName: string | null;
  className?: string;
}

export function PropertyImage({ src, alt, sourceName, className = "" }: PropertyImageProps) {
  const [failed, setFailed] = useState(false);

  if (!src || failed) {
    return (
      <div
        className={`flex flex-col items-center justify-center gap-2 bg-gradient-to-br from-surface-muted to-line text-ink-faint ${className}`}
      >
        <IconBuilding className="text-4xl opacity-70" />
        <span className="text-xs font-medium">{failed ? "Photo couldn't be loaded" : "No photo available"}</span>
      </div>
    );
  }

  return (
    <div className={`relative overflow-hidden bg-surface-muted ${className}`}>
      {/* eslint-disable-next-line @next/next/no-img-element -- third-party listing photos are shown as-is, not proxied through the Next.js optimizer */}
      <img
        src={src}
        alt={alt}
        loading="lazy"
        referrerPolicy="no-referrer"
        onError={() => setFailed(true)}
        ref={(img) => {
          // Errors that fire before hydration never reach onError.
          if (img?.complete && img.naturalWidth === 0) setFailed(true);
        }}
        className="h-full w-full object-cover"
      />
      <span className="absolute bottom-2 right-2 rounded-md bg-black/60 px-1.5 py-0.5 text-[11px] font-medium text-white">
        Photo: {sourceName ?? "source not recorded"}
      </span>
    </div>
  );
}
