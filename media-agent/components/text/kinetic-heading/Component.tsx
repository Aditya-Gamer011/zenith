import React from "react";

export const KineticHeading: React.FC<{ text?: string }> = ({ text = "Autonomous Sovereign Systems" }) => {
  return (
    <h1 className="text-5xl md:text-7xl font-extrabold tracking-tight text-white flex flex-wrap gap-x-3">
      {text.split(" ").map((word, i) => (
        <span
          key={i}
          className="inline-block transition-transform duration-500 hover:-translate-y-1 hover:text-cyan-400"
          style={{ animation: `fade-slide-up 0.6s cubic-bezier(0.16, 1, 0.3, 1) ${i * 0.12}s backwards` }}
        >
          {word}
        </span>
      ))}
    </h1>
  );
};
