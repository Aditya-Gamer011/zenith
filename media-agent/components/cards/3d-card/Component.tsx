import React, { useRef, useState } from "react";

export const Card3D: React.FC<{ title?: string; children?: React.ReactNode }> = ({
  title = "3D Interactive Element",
  children,
}) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [rot, setRot] = useState({ x: 0, y: 0 });

  const handleMouseMove = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!cardRef.current) return;
    const rect = cardRef.current.getBoundingClientRect();
    const x = e.clientX - rect.left - rect.width / 2;
    const y = e.clientY - rect.top - rect.height / 2;
    setRot({ x: -y * 0.08, y: x * 0.08 });
  };

  const handleMouseLeave = () => setRot({ x: 0, y: 0 });

  return (
    <div style={{ perspective: "1000px" }}>
      <div
        ref={cardRef}
        onMouseMove={handleMouseMove}
        onMouseLeave={handleMouseLeave}
        className="p-8 rounded-2xl bg-neutral-900 border border-neutral-800 transition-transform duration-150 ease-out cursor-pointer"
        style={{
          transform: `rotateX(${rot.x}deg) rotateY(${rot.y}deg)`,
          transformStyle: "preserve-3d",
        }}
      >
        <div style={{ transform: "translateZ(40px)" }} className="text-xl font-bold text-white mb-2">
          {title}
        </div>
        <div style={{ transform: "translateZ(20px)" }} className="text-sm text-neutral-400">
          {children || "Physical depth layers responding to subtle pointer movements."}
        </div>
      </div>
    </div>
  );
};
