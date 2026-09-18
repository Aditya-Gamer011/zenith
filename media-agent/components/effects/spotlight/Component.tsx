import React, { useRef, useState } from "react";

export const SpotlightContainer: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState({ x: 0, y: 0, opacity: 0 });

  return (
    <div
      ref={containerRef}
      onMouseMove={(e) => {
        const rect = containerRef.current?.getBoundingClientRect();
        if (!rect) return;
        setPos({ x: e.clientX - rect.left, y: e.clientY - rect.top, opacity: 1 });
      }}
      onMouseLeave={() => setPos((prev) => ({ ...prev, opacity: 0 }))}
      className="relative overflow-hidden rounded-2xl bg-neutral-950 p-8 border border-neutral-800"
    >
      <div
        className="pointer-events-none absolute -inset-px transition-opacity duration-300"
        style={{
          opacity: pos.opacity,
          background: `radial-gradient(600px circle at ${pos.x}px ${pos.y}px, rgba(56, 189, 248, 0.15), transparent 40%)`,
        }}
      />
      <div className="relative z-10">{children}</div>
    </div>
  );
};
