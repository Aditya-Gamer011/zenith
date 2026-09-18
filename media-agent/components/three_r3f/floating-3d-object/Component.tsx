import React, { useEffect, useRef } from "react";
import * as THREE from "three";

export const Floating3DTorus: React.FC = () => {
  const mountRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(75, mount.clientWidth / mount.clientHeight, 0.1, 1000);
    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });

    renderer.setSize(mount.clientWidth, mount.clientHeight);
    mount.appendChild(renderer.domElement);

    const geometry = new THREE.TorusGeometry(2, 0.6, 32, 100);
    const material = new THREE.MeshStandardMaterial({
      color: 0x38bdf8,
      metalness: 0.85,
      roughness: 0.2,
      wireframe: false,
    });
    const torus = new THREE.Mesh(geometry, material);
    scene.add(torus);

    const light1 = new THREE.DirectionalLight(0xffffff, 1.5);
    light1.position.set(5, 5, 5);
    scene.add(light1);

    const light2 = new THREE.PointLight(0x818cf8, 2, 50);
    light2.position.set(-5, -5, 2);
    scene.add(light2);

    camera.position.z = 5;

    let animId: number;
    const animate = () => {
      torus.rotation.x += 0.008;
      torus.rotation.y += 0.012;
      renderer.render(scene, camera);
      animId = requestAnimationFrame(animate);
    };
    animate();

    return () => {
      cancelAnimationFrame(animId);
      mount.removeChild(renderer.domElement);
    };
  }, []);

  return <div ref={mountRef} className="w-full h-[400px]" />;
};
