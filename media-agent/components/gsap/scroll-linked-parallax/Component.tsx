import React from "react";

export const ScrollParallaxPrimitive: React.FC<{ children?: React.ReactNode }> = ({ children }) => {
  return <section className="relative overflow-hidden py-24">{children}</section>;
};
