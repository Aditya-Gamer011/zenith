import React from "react";

export const LiquidButton: React.FC<{ children?: React.ReactNode }> = ({ children = "Liquid Discover" }) => (
  <button className="liquid-btn">
    <span className="relative z-10">{children}</span>
    <div className="liquid-blob" />
  </button>
);
