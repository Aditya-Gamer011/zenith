import React from "react";

export interface GlassCardProps {
  title?: string;
  subtitle?: string;
  badge?: string;
  children?: React.ReactNode;
  className?: string;
}

export const GlassCard: React.FC<GlassCardProps> = ({
  title = "Unified Context Engine",
  subtitle = "Maintains persistent awareness across tools, memory, and runtime sandboxes.",
  badge = "Autonomous",
  children,
  className = "",
}) => {
  return (
    <div
      className={`relative p-8 rounded-2xl transition-all duration-300 hover:-translate-y-1.5 ${className}`}
      style={{
        background: "var(--card-glass, rgba(24, 27, 32, 0.78))",
        backdropFilter: "blur(16px)",
        WebkitBackdropFilter: "blur(16px)",
        border: "1px solid var(--border-color, rgba(255, 255, 255, 0.08))",
        boxShadow: "0 20px 40px -15px rgba(0, 0, 0, 0.5)",
      }}
    >
      {badge && (
        <span
          className="inline-block px-3 py-1 text-xs font-mono tracking-wider rounded-full mb-4"
          style={{
            background: "rgba(212, 163, 115, 0.12)",
            color: "var(--accent-1, #d4a373)",
            border: "1px solid rgba(212, 163, 115, 0.25)",
          }}
        >
          {badge}
        </span>
      )}
      <h3 className="text-xl font-bold text-white mb-2 tracking-tight">{title}</h3>
      <p className="text-sm text-slate-400 leading-relaxed mb-4">{subtitle}</p>
      {children}
    </div>
  );
};
