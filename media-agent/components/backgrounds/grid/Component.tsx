import React from "react";

export const RetroGrid: React.FC = () => (
  <div className="pointer-events-none absolute h-full w-full overflow-hidden opacity-30 [perspective:200px]">
    <div className="absolute inset-0 [transform:rotateX(35deg)]">
      <div className="animate-grid [background-repeat:repeat] [background-size:60px_60px] [height:300vh] [inset:0%_0px] [margin-left:-50%] [transform-origin:100%_0_0] [width:600vw] [background-image:linear-gradient(to_right,rgba(255,255,255,0.1)_1px,transparent_0),linear-gradient(to_bottom,rgba(255,255,255,0.1)_1px,transparent_0)]" />
    </div>
    <div className="absolute inset-0 bg-gradient-to-t from-black to-transparent to-90%" />
  </div>
);
