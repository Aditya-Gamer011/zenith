import React from "react";

export const AuroraBackground: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  return (
    <div className="relative flex flex-col h-screen items-center justify-center bg-zinc-950 text-slate-950 transition-bg overflow-hidden">
      <div className="absolute inset-0 overflow-hidden pointer-events-none opacity-40">
        <div
          className="filter blur-[80px] -inset-[10px] opacity-50 absolute animate-aurora"
          style={{
            backgroundImage: `radial-gradient(ellipse at 100% 0%, var(--accent-1, #38bdf8) 10%, transparent 40%),
                              radial-gradient(ellipse at 0% 100%, var(--accent-2, #818cf8) 15%, transparent 50%),
                              radial-gradient(ellipse at 50% 50%, #34d399 10%, transparent 45%)`,
          }}
        />
      </div>
      <div className="relative z-10">{children}</div>
    </div>
  );
};
