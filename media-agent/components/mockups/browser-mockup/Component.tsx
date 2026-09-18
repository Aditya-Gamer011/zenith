import React from "react";

export const BrowserMockup: React.FC<{ url?: string; children?: React.ReactNode }> = ({
  url = "zenith.local/dashboard",
  children,
}) => {
  return (
    <div className="w-full rounded-xl overflow-hidden border border-neutral-800 bg-neutral-950 shadow-2xl">
      <div className="flex items-center gap-2 px-4 py-3 bg-neutral-900/80 border-b border-neutral-800 backdrop-blur-md">
        <div className="flex gap-1.5">
          <div className="w-3 h-3 rounded-full bg-red-500/80" />
          <div className="w-3 h-3 rounded-full bg-yellow-500/80" />
          <div className="w-3 h-3 rounded-full bg-green-500/80" />
        </div>
        <div className="mx-auto px-6 py-1 rounded-md bg-neutral-950/70 border border-neutral-800 text-xs font-mono text-neutral-400">
          https://{url}
        </div>
      </div>
      <div className="p-6">{children}</div>
    </div>
  );
};
