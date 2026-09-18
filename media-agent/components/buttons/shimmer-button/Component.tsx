import React from "react";

export const ShimmerButton: React.FC<{ children?: React.ReactNode; onClick?: () => void }> = ({
  children = "Explore Collection",
  onClick,
}) => {
  return (
    <button
      onClick={onClick}
      className="relative inline-flex h-12 overflow-hidden rounded-full p-[1px] focus:outline-none focus:ring-2 focus:ring-slate-400 focus:ring-offset-2 focus:ring-offset-slate-50"
    >
      <span className="absolute inset-[-1000%] animate-[spin_3s_linear_infinite] bg-[conic-gradient(from_90deg_at_50%_50%,var(--accent-1,#38bdf8)_0%,var(--accent-2,#818cf8)_50%,var(--accent-1,#38bdf8)_100%)]" />
      <span className="inline-flex h-full w-full cursor-pointer items-center justify-center rounded-full bg-slate-950 px-7 py-1 text-sm font-medium text-white backdrop-blur-3xl hover:bg-slate-900 transition-colors">
        {children}
      </span>
    </button>
  );
};
