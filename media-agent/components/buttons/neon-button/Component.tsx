import React from "react";

export const NeonButton: React.FC<{ children?: React.ReactNode; onClick?: () => void }> = ({
  children = "Get Started",
  onClick
}) => {
  return (
    <button onClick={onClick} className="neon-glow-btn">
      <span>{children}</span>
    </button>
  );
};
