import React, { useRef, useState } from "react";

export interface MagneticNeonButtonProps {
  children?: React.ReactNode;
  onClick?: () => void;
  className?: string;
  glowColor?: string;
  borderColor?: string;
}

export const MagneticNeonButton: React.FC<MagneticNeonButtonProps> = ({
  children = "Launch Sovereign System",
  onClick,
  className = "",
  glowColor = "rgba(0, 243, 255, 0.45)",
  borderColor = "#00f3ff",
}) => {
  const btnRef = useRef<HTMLButtonElement>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const [hovered, setHovered] = useState(false);

  const handleMouseMove = (e: React.MouseEvent<HTMLButtonElement>) => {
    if (!btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    setOffset({ x: x * 0.28, y: y * 0.28 });
  };

  const handleMouseLeave = () => {
    setOffset({ x: 0, y: 0 });
    setHovered(false);
  };

  return (
    <button
      ref={btnRef}
      onClick={onClick}
      onMouseMove={handleMouseMove}
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={handleMouseLeave}
      className={`relative inline-flex items-center justify-center px-8 py-4 font-semibold rounded-xl text-white overflow-hidden transition-transform duration-200 ease-out active:scale-95 ${className}`}
      style={{
        transform: `translate3d(${offset.x}px, ${offset.y}px, 0)`,
        background: "linear-gradient(135deg, rgba(20, 25, 35, 0.95), rgba(10, 15, 22, 0.98))",
        border: `1px solid ${borderColor}`,
        boxShadow: hovered
          ? `0 0 35px ${glowColor}, inset 0 0 15px ${glowColor}`
          : `0 0 15px rgba(0, 243, 255, 0.15)`,
      }}
    >
      <span className="relative z-10 tracking-wider uppercase text-sm flex items-center gap-2">
        {children}
        <svg className="w-4 h-4 transition-transform duration-300 group-hover:translate-x-1" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14 5l7 7m0 0l-7 7m7-7H3" />
        </svg>
      </span>
      <div
        className="absolute inset-0 opacity-20 pointer-events-none transition-opacity duration-300"
        style={{
          background: `radial-gradient(circle at 50% 50%, ${glowColor} 0%, transparent 70%)`,
        }}
      />
    </button>
  );
};
