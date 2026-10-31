"use client";

import { forwardRef, useMemo, useRef, type MutableRefObject, type ReactNode } from "react";
import { useFrame } from "@react-three/fiber";
import { RoundedBox } from "@react-three/drei";
import {
  AdditiveBlending,
  CanvasTexture,
  Color,
  ConeGeometry,
  DoubleSide,
  ExtrudeGeometry,
  Group,
  LatheGeometry,
  Mesh,
  MeshBasicMaterial,
  Object3D,
  RepeatWrapping,
  Shape,
  SpotLight,
  SRGBColorSpace,
  Vector2,
} from "three";

/** How far below the ship's origin its landing-gear feet reach when fully deployed. */
export const GEAR_HEIGHT = 0.62;
/** Where the gear legs attach under the hull. */
const GEAR_MOUNT_Y = -0.2;

export type ShipControls = {
  /** Engine power, 0 (off) to 1 (full burn). */
  thrust: MutableRefObject<number>;
  /** Landing gear, 0 (stowed) to 1 (down). */
  gear: MutableRefObject<number>;
};

const EXHAUST = new Color("#cfe6ff");
const DIAMOND = new Color("#9fc4ff");

function seeded(seed: number) {
  let value = seed;
  return () => {
    value = (value * 16807) % 2147483647;
    return value / 2147483647;
  };
}

/** Fine panel seams and rivets: a subtle bump on the polished plating. */
function panelTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 1024;
  canvas.height = 1024;
  const context = canvas.getContext("2d")!;
  const random = seeded(7);
  context.fillStyle = "rgb(150,150,150)";
  context.fillRect(0, 0, 1024, 1024);
  context.strokeStyle = "rgb(60,60,60)";
  context.lineWidth = 2;
  const split = (x: number, y: number, width: number, height: number, depth: number) => {
    if (depth === 0 || width < 80 || height < 60) {
      context.strokeRect(x, y, width, height);
      context.fillStyle = "rgb(90,90,90)";
      for (let rivet = 6; rivet < width - 4; rivet += 16) context.fillRect(x + rivet, y + 4, 2, 2);
      return;
    }
    const horizontal = width > height;
    const cut = (horizontal ? width : height) * (0.3 + random() * 0.4);
    if (horizontal) {
      split(x, y, cut, height, depth - 1);
      split(x + cut, y, width - cut, height, depth - 1);
    } else {
      split(x, y, width, cut, depth - 1);
      split(x, y + cut, width, height - cut, depth - 1);
    }
  };
  split(0, 0, 1024, 1024, 6);
  const texture = new CanvasTexture(canvas);
  texture.wrapS = texture.wrapT = RepeatWrapping;
  texture.repeat.set(0.35, 0.35);
  return texture;
}

/** Wing livery: a gold band, a roundel and the registration. */
function liveryTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 256;
  const context = canvas.getContext("2d")!;
  context.clearRect(0, 0, 512, 256);
  context.fillStyle = "rgba(212,137,42,0.95)";
  context.beginPath();
  context.moveTo(330, 0);
  context.lineTo(400, 0);
  context.lineTo(330, 256);
  context.lineTo(260, 256);
  context.closePath();
  context.fill();
  context.beginPath();
  context.arc(110, 128, 56, 0, Math.PI * 2);
  context.fillStyle = "rgba(240,244,250,0.95)";
  context.fill();
  context.beginPath();
  context.arc(110, 128, 42, 0, Math.PI * 2);
  context.fillStyle = "rgba(36,83,158,0.95)";
  context.fill();
  context.beginPath();
  context.arc(110, 128, 16, 0, Math.PI * 2);
  context.fillStyle = "rgba(212,137,42,0.95)";
  context.fill();
  context.fillStyle = "rgba(24,32,52,0.85)";
  context.font = "bold 54px 'Segoe UI', Arial, sans-serif";
  context.textBaseline = "middle";
  context.fillText("RAG-01", 410, 128);
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  texture.anisotropy = 8;
  return texture;
}

/** Hot white centre fading to blue: the inside of an engine nozzle. */
function exhaustTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 128;
  const context = canvas.getContext("2d")!;
  const gradient = context.createRadialGradient(64, 64, 4, 64, 64, 64);
  gradient.addColorStop(0, "#ffffff");
  gradient.addColorStop(0.35, "#bfe0ff");
  gradient.addColorStop(0.7, "#3c6cff");
  gradient.addColorStop(1, "#0b1030");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 128, 128);
  const texture = new CanvasTexture(canvas);
  texture.colorSpace = SRGBColorSpace;
  return texture;
}

function lathe(points: number[][], segments: number) {
  return new LatheGeometry(points.map(([radius, y]) => new Vector2(radius, y)), segments);
}

/** A flat outline (x across, y forward) given thickness. Laid flat by rotating it a quarter turn about X. */
function plate(points: number[][], depth: number, bevel: number, segments = 3) {
  const shape = new Shape();
  shape.moveTo(points[0][0], points[0][1]);
  points.slice(1).forEach(([x, y]) => shape.lineTo(x, y));
  shape.closePath();
  return new ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelThickness: bevel, bevelSize: bevel, bevelSegments: segments });
}

/** Mirror a right-hand outline (x >= 0) into a full symmetric outline. */
function symmetric(half: number[][]) {
  const mirrored = half
    .slice(1, -1)
    .reverse()
    .map(([x, y]) => [-x, y]);
  return [...half, ...mirrored];
}

function buildGeometries() {
  const plume = new ConeGeometry(0.2, 1.6, 24, 1, true);
  plume.translate(0, 0.8, 0);
  return {
    // Flat arrowhead body in three layers: the wide lower hull, a raised deck and a central spine.
    hull: plate(symmetric([[0, 3.3], [0.18, 2.6], [0.42, 1.6], [0.62, 0.4], [0.78, -0.9], [0.72, -1.9], [0.5, -2.3], [0.18, -2.15], [0, -2.25]]), 0.26, 0.07),
    deck: plate(symmetric([[0, 2.75], [0.2, 2.0], [0.36, 1.0], [0.5, -0.4], [0.55, -1.6], [0.38, -2.05], [0, -2.0]]), 0.14, 0.05),
    spine: plate(symmetric([[0, 1.2], [0.09, 0.6], [0.12, -1.6], [0, -1.9]]), 0.1, 0.03),
    chevron: plate([[0, 0.5], [0.44, -0.3], [0.44, -0.5], [0, 0.26], [-0.44, -0.5], [-0.44, -0.3]], 0.02, 0.008, 1),
    noseBand: plate(symmetric([[0, 3.05], [0.12, 2.62], [0.17, 2.45], [0, 2.82]]), 0.02, 0.006, 1),
    // Main wing with a forward-kicked tip, and its blue leading edge.
    wing: plate([[0, 0.5], [1.5, -0.6], [2.75, -1.25], [3.05, -0.95], [3.0, -1.55], [2.2, -1.75], [0.9, -1.55], [0, -1.9]], 0.07, 0.025),
    leadingEdge: plate([[0, 0.5], [1.5, -0.6], [2.75, -1.25], [2.75, -1.36], [1.5, -0.72], [0, 0.36]], 0.075, 0.012, 1),
    blade: plate([[0, 0.4], [1.7, -1.3], [1.95, -1.55], [1.6, -1.6], [0, -0.9]], 0.04, 0.015),
    canard: plate([[0, 0.2], [0.5, -0.25], [0.55, -0.4], [0, -0.25]], 0.03, 0.01),
    tail: plate([[0, 0], [0.95, 0], [0.25, 0.8], [-0.1, 0.8]], 0.04, 0.012),
    nozzle: lathe([[0.22, 0], [0.25, -0.1], [0.3, -0.34], [0.26, -0.34], [0.21, -0.1], [0.19, 0]], 32),
    plume,
  };
}

function Gear({ position, gear }: { position: [number, number, number]; gear: MutableRefObject<number> }) {
  const leg = useRef<Group>(null);
  // Length from the mount to the ground, so the feet land exactly GEAR_HEIGHT below the ship.
  const length = GEAR_HEIGHT + position[1];
  useFrame(() => {
    if (!leg.current) return;
    leg.current.visible = gear.current > 0.02;
    // Folds back flat under the hull when stowed.
    leg.current.rotation.x = (1 - gear.current) * (Math.PI / 2);
  });
  return (
    <group position={position}>
      <group ref={leg}>
        <mesh position={[0, -length / 2, 0]}>
          <cylinderGeometry args={[0.032, 0.038, length, 12]} />
          <meshStandardMaterial color="#52575f" metalness={0.9} roughness={0.35} />
        </mesh>
        <mesh position={[0, -length * 0.4, -0.06]} rotation={[0.5, 0, 0]}>
          <cylinderGeometry args={[0.016, 0.016, length * 0.7, 8]} />
          <meshStandardMaterial color="#8b9099" metalness={1} roughness={0.25} />
        </mesh>
        <mesh position={[0, -length + 0.025, 0]}>
          <cylinderGeometry args={[0.12, 0.14, 0.05, 20]} />
          <meshStandardMaterial color="#25282d" metalness={0.7} roughness={0.6} />
        </mesh>
      </group>
    </group>
  );
}

function Engine({
  position,
  radius = 1,
  shapes,
  glow,
  register,
}: {
  position: [number, number, number];
  radius?: number;
  shapes: ReturnType<typeof buildGeometries>;
  glow: CanvasTexture;
  register: (core: MeshBasicMaterial, plume: Mesh, diamonds: Mesh[]) => void;
}) {
  const parts = useRef<{ core?: MeshBasicMaterial; plume?: Mesh; diamonds: Mesh[] }>({ diamonds: [] });
  const done = () => {
    const { core, plume, diamonds } = parts.current;
    if (core && plume && diamonds.length === 4) register(core, plume, diamonds);
  };
  return (
    <group position={position} scale={radius}>
      <mesh geometry={shapes.nozzle} rotation={[Math.PI / 2, 0, 0]}>
        <meshStandardMaterial color="#2b2d31" metalness={1} roughness={0.4} side={DoubleSide} />
      </mesh>
      <mesh position={[0, 0, -0.05]}>
        <torusGeometry args={[0.17, 0.025, 10, 32]} />
        <meshStandardMaterial color="#1a1c20" metalness={1} roughness={0.3} />
      </mesh>
      <mesh position={[0, 0, -0.08]} rotation={[0, Math.PI, 0]}>
        <circleGeometry args={[0.19, 32]} />
        <meshBasicMaterial
          map={glow}
          toneMapped={false}
          ref={(material) => {
            if (material && !parts.current.core) {
              parts.current.core = material;
              done();
            }
          }}
        />
      </mesh>
      <mesh
        geometry={shapes.plume}
        position={[0, 0, -0.1]}
        rotation={[-Math.PI / 2, 0, 0]}
        ref={(mesh) => {
          if (mesh && !parts.current.plume) {
            parts.current.plume = mesh;
            done();
          }
        }}
      >
        <meshBasicMaterial color="#8fb8ff" transparent opacity={0.1} blending={AdditiveBlending} depthWrite={false} side={DoubleSide} />
      </mesh>
      {[0, 1, 2, 3].map((index) => (
        <mesh
          key={index}
          position={[0, 0, -0.35 - index * 0.36]}
          scale={[0.055, 0.055, 0.14]}
          ref={(mesh) => {
            if (mesh && !parts.current.diamonds.includes(mesh)) {
              parts.current.diamonds.push(mesh);
              done();
            }
          }}
        >
          <sphereGeometry args={[1, 16, 12]} />
          <meshBasicMaterial transparent blending={AdditiveBlending} depthWrite={false} toneMapped={false} />
        </mesh>
      ))}
    </group>
  );
}

/** Lays a flat outline into the ship: outline y becomes forward (+Z), thickness hangs downward from `y`. */
const FLAT: [number, number, number] = [Math.PI / 2, 0, 0];

/**
 * An original sleek starfighter: a flat chrome arrowhead with layered blade wings, a forward
 * bubble canopy and a blue and gold livery. Its nose points along +Z, so lookAt() aims it.
 */
export const Ship = forwardRef<Group, ShipControls>(function Ship({ thrust, gear }, ref) {
  const shapes = useMemo(buildGeometries, []);
  const panels = useMemo(panelTexture, []);
  const livery = useMemo(liveryTexture, []);
  const glow = useMemo(exhaustTexture, []);
  const engines = useRef<Array<{ core: MeshBasicMaterial; plume: Mesh; diamonds: Mesh[] }>>([]);
  const strobes = useRef<MeshBasicMaterial[]>([]);
  const navLights = useRef<MeshBasicMaterial[]>([]);
  const landingLights = useRef<SpotLight[]>([]);
  const landingCones = useRef<MeshBasicMaterial[]>([]);
  const lightTargets = useMemo(() => [new Object3D(), new Object3D()], []);
  const greebles = useMemo(() => {
    const random = seeded(42);
    return Array.from({ length: 18 }, () => ({
      position: [(random() - 0.5) * 0.7, 0.3, -0.7 - random() * 1.2] as [number, number, number],
      size: [0.05 + random() * 0.12, 0.025 + random() * 0.04, 0.05 + random() * 0.18] as [number, number, number],
      dark: random() < 0.5,
    }));
  }, []);

  useFrame(({ clock }) => {
    const time = clock.elapsedTime;
    const power = thrust.current;
    const flicker = 0.93 + Math.sin(time * 41) * 0.035 + Math.sin(time * 27) * 0.035;
    engines.current.forEach(({ core, plume, diamonds }) => {
      core.color.copy(EXHAUST).multiplyScalar((0.25 + power * 4.5) * flicker);
      plume.visible = power > 0.15;
      plume.scale.set(1, 0.3 + (power - 0.15) * 2.2 * flicker, 1);
      (plume.material as MeshBasicMaterial).opacity = 0.05 + power * 0.1;
      diamonds.forEach((diamond, index) => {
        diamond.visible = power > 0.35;
        const fade = Math.max(0, 1 - index * 0.25);
        (diamond.material as MeshBasicMaterial).color.copy(DIAMOND).multiplyScalar(power * 1.3 * fade * flicker);
      });
    });
    const strobe = time % 1.6 < 0.06 ? 14 : 0;
    strobes.current.forEach((material) => material.color.setScalar(strobe));
    const blink = Math.sin(time * 3.2) > 0.7 ? 6 : 0.15;
    // Facing +Z, the ship's port (left) side is +X: red there, green on starboard.
    navLights.current.forEach((material, index) => material.color.set(index === 0 ? "#ff3b30" : "#30d158").multiplyScalar(blink));
    const lights = gear.current;
    landingLights.current.forEach((light) => (light.intensity = lights * 28));
    landingCones.current.forEach((material) => (material.opacity = lights * 0.015));
  });

  const chrome = (
    <meshPhysicalMaterial color="#dde2ea" metalness={1} roughness={0.13} clearcoat={0.5} clearcoatRoughness={0.1} bumpMap={panels} bumpScale={0.25} envMapIntensity={2.8} />
  );
  const blue = <meshPhysicalMaterial color="#24539e" metalness={0.55} roughness={0.26} clearcoat={1} clearcoatRoughness={0.08} bumpMap={panels} bumpScale={0.2} />;
  const gold = <meshPhysicalMaterial color="#d4892a" metalness={0.9} roughness={0.2} clearcoat={0.6} clearcoatRoughness={0.1} />;
  const carbon = <meshStandardMaterial color="#23262c" metalness={0.75} roughness={0.45} />;
  const steel = <meshStandardMaterial color="#6b7079" metalness={1} roughness={0.3} />;
  const box = (args: [number, number, number], position: [number, number, number], material: ReactNode, radius = 0.03) => (
    <RoundedBox key={position.join(",")} args={args} radius={radius} smoothness={3} position={position} castShadow receiveShadow>
      {material}
    </RoundedBox>
  );

  return (
    <group ref={ref}>
      {/* Body: chrome lower hull, blue deck, chrome spine, gold chevrons and nose band */}
      <mesh geometry={shapes.hull} position={[0, 0.08, 0]} rotation={FLAT} castShadow receiveShadow>
        {chrome}
      </mesh>
      <mesh geometry={shapes.deck} position={[0, 0.24, 0]} rotation={FLAT} castShadow receiveShadow>
        {blue}
      </mesh>
      <mesh geometry={shapes.spine} position={[0, 0.36, 0]} rotation={FLAT} castShadow>
        {chrome}
      </mesh>
      {[0.2, -0.45].map((z) => (
        <mesh key={z} geometry={shapes.chevron} position={[0, 0.315, z]} rotation={FLAT}>
          {gold}
        </mesh>
      ))}
      <mesh geometry={shapes.noseBand} position={[0, 0.17, 0]} rotation={FLAT}>
        {gold}
      </mesh>
      {box([0.5, 0.12, 0.9], [0, -0.2, 0.6], carbon, 0.04)}

      {/* Forward bubble canopy */}
      <mesh position={[0, 0.3, 1.95]} scale={[0.3, 0.2, 0.85]} castShadow>
        <sphereGeometry args={[1, 40, 28]} />
        <meshPhysicalMaterial color="#0c2a3a" metalness={0.1} roughness={0.02} clearcoat={1} clearcoatRoughness={0.02} envMapIntensity={3} emissive="#39c6e6" emissiveIntensity={0.22} />
      </mesh>
      {box([0.025, 0.035, 1.1], [0, 0.49, 1.9], steel, 0.01)}

      {/* Canards */}
      {[-1, 1].map((side) => (
        <mesh key={`canard-${side}`} geometry={shapes.canard} position={[side * 0.4, 0.14, 1.35]} rotation={FLAT} scale={[side, 1, 1]} castShadow>
          {blue}
        </mesh>
      ))}

      {/* Main wings with slight anhedral, blue leading edges, livery and nav lights */}
      {[-1, 1].map((side) => (
        <group key={`wing-${side}`} position={[side * 0.55, 0.02, 0]} rotation={[0, 0, -side * 0.06]}>
          <mesh geometry={shapes.wing} rotation={FLAT} scale={[side, 1, 1]} castShadow receiveShadow>
            {chrome}
          </mesh>
          <mesh geometry={shapes.leadingEdge} position={[0, 0.016, 0]} rotation={FLAT} scale={[side, 1, 1]}>
            {blue}
          </mesh>
          <mesh position={[side * 1.75, 0.03, -1.25]} rotation={[-Math.PI / 2, 0, side > 0 ? -0.42 : Math.PI - 0.42]}>
            <planeGeometry args={[1.2, 0.55]} />
            <meshStandardMaterial map={livery} transparent roughness={0.3} metalness={0.4} polygonOffset polygonOffsetFactor={-2} />
          </mesh>
          <mesh position={[side * 3.0, 0.03, -1.0]}>
            <sphereGeometry args={[0.03, 10, 10]} />
            <meshBasicMaterial
              toneMapped={false}
              ref={(material) => {
                if (material) navLights.current[side > 0 ? 0 : 1] = material;
              }}
            />
          </mesh>
        </group>
      ))}

      {/* Upper gold blades, swept back and angled up */}
      {[-1, 1].map((side) => (
        <group key={`blade-${side}`} position={[side * 0.42, 0.32, -0.35]} rotation={[0, 0, side * 0.42]}>
          <mesh geometry={shapes.blade} rotation={FLAT} scale={[side, 1, 1]} castShadow>
            {gold}
          </mesh>
        </group>
      ))}

      {/* Canted tail blades with strobes */}
      {[-1, 1].map((side) => (
        <group key={`tail-${side}`} position={[side * 0.5, 0.3, -1.45]} rotation={[0, 0, side * -0.5]}>
          <mesh geometry={shapes.tail} rotation={[0, -Math.PI / 2, 0]} position={[-0.02, 0, 0]} castShadow>
            {chrome}
          </mesh>
          <mesh position={[0, 0.82, 0.05]}>
            <sphereGeometry args={[0.024, 10, 10]} />
            <meshBasicMaterial
              toneMapped={false}
              ref={(material) => {
                if (material) strobes.current[side > 0 ? 0 : 1] = material;
              }}
            />
          </mesh>
        </group>
      ))}

      {/* Engine nacelles and nozzles, built into the tail */}
      {[-1, 1].map((side) => box([0.52, 0.3, 1.25], [side * 0.6, 0.05, -1.75], carbon, 0.08))}
      {[-1, 1].map((side) => box([0.4, 0.06, 1.0], [side * 0.6, 0.22, -1.7], blue, 0.025))}
      {[
        { position: [-0.6, 0.05, -2.4] as [number, number, number], radius: 0.95 },
        { position: [0.6, 0.05, -2.4] as [number, number, number], radius: 0.95 },
        { position: [0, 0.12, -2.3] as [number, number, number], radius: 0.5 },
      ].map((engine, index) => (
        <Engine
          key={index}
          position={engine.position}
          radius={engine.radius}
          shapes={shapes}
          glow={glow}
          register={(core, plume, diamonds) => {
            engines.current[index] = { core, plume, diamonds };
          }}
        />
      ))}

      {/* Small surface detail on the rear deck */}
      {greebles.map((greeble, index) => (
        <mesh key={index} position={greeble.position} castShadow>
          <boxGeometry args={greeble.size} />
          {greeble.dark ? carbon : steel}
        </mesh>
      ))}

      {/* Landing gear and landing lights */}
      <Gear position={[0, GEAR_MOUNT_Y, 1.7]} gear={gear} />
      <Gear position={[0.75, GEAR_MOUNT_Y, -1.05]} gear={gear} />
      <Gear position={[-0.75, GEAR_MOUNT_Y, -1.05]} gear={gear} />
      {[-0.18, 0.18].map((x, index) => (
        <group key={`landing-light-${x}`} position={[x, -0.18, 2.3]}>
          <primitive object={lightTargets[index]} position={[0, -3, 1.6]} />
          <spotLight
            ref={(light) => {
              if (light) {
                light.target = lightTargets[index];
                landingLights.current[index] = light;
              }
            }}
            angle={0.55}
            penumbra={0.7}
            distance={9}
            color="#fff4e0"
            intensity={0}
          />
          <mesh position={[0, -1.2, 0.65]} rotation={[0.5, 0, 0]}>
            <coneGeometry args={[0.7, 2.6, 24, 1, true]} />
            <meshBasicMaterial
              color="#fff1d6"
              transparent
              opacity={0}
              blending={AdditiveBlending}
              depthWrite={false}
              side={DoubleSide}
              ref={(material) => {
                if (material) landingCones.current[index] = material;
              }}
            />
          </mesh>
        </group>
      ))}
    </group>
  );
});
