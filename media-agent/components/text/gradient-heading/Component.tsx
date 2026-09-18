import React from "react";

export const GradientHeading: React.FC<{ children?: React.ReactNode }> = ({ children = "Architectural Precision" }) => (
  <h2 className="text-4xl md:text-6xl font-black tracking-tighter bg-gradient-to-r from-cyan-400 via-indigo-400 to-amber-300 bg-clip-text text-transparent animate-gradient-x">
    {children}
  </h2>
);
