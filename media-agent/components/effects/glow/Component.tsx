import React from "react";

export const GlowBacklight: React.FC<{ children?: React.ReactNode }> = ({ children }) => (
  <div className="relative group">
    <div className="absolute -inset-1 bg-gradient-to-r from-cyan-500 to-indigo-500 rounded-2xl blur-lg opacity-40 group-hover:opacity-80 transition duration-500" />
    <div className="relative">{children}</div>
  </div>
);
