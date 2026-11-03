"use client";

import { useMemo, useRef, type MutableRefObject } from "react";
import { useFrame } from "@react-three/fiber";
import { MeshTransmissionMaterial } from "@react-three/drei";
import { AdditiveBlending, BackSide, CanvasTexture, DoubleSide, FrontSide, MathUtils, MeshBasicMaterial, ShaderMaterial, TubeGeometry, Vector3 } from "three";
import {
  APPROACH,
  RING_TUNNEL_FRACTIONS,
  TUNNEL_RADIUS,
  UNIVERSES,
  exitFlightFraction,
  mouthFlightFraction,
  ringFlightFractions,
  ringPositions,
  tunnelCurve,
} from "./flight-path";

/** Values the flight rig updates every frame and the scenery reads. */
export type FlightEffects = { progress: number; speed: number; pulse: number; pulseGate: number; landed: boolean };

export const NOISE_GLSL = /* glsl */ `
  float hash3(vec3 p) { p = fract(p * 0.3183099 + 0.1); p *= 17.0; return fract(p.x * p.y * p.z * (p.x + p.y + p.z)); }
  float noise3(vec3 x) {
    vec3 i = floor(x); vec3 f = fract(x); f = f * f * (3.0 - 2.0 * f);
    return mix(mix(mix(hash3(i), hash3(i + vec3(1,0,0)), f.x), mix(hash3(i + vec3(0,1,0)), hash3(i + vec3(1,1,0)), f.x), f.y),
               mix(mix(hash3(i + vec3(0,0,1)), hash3(i + vec3(1,0,1)), f.x), mix(hash3(i + vec3(0,1,1)), hash3(i + vec3(1,1,1)), f.x), f.y), f.z);
  }
  float fbm(vec3 p) { float v = 0.0; float a = 0.5; for (int i = 0; i < 5; i++) { v += a * noise3(p); p = p * 2.03 + 11.7; a *= 0.5; } return v; }
`;

const passthroughVertex = /* glsl */ `
  varying vec2 vUv;
  varying vec3 vNormalView;
  varying vec3 vViewDir;
  void main() {
    vUv = uv;
    vec4 view = modelViewMatrix * vec4(position, 1.0);
    vNormalView = normalize(normalMatrix * normal);
    vViewDir = normalize(-view.xyz);
    gl_Position = projectionMatrix * view;
  }
`;

/** Each stretch of the tunnel is tinted by the universe it belongs to, so the next one shows through the gate ahead. */
export function Tunnel({ effects }: { effects: MutableRefObject<FlightEffects> }) {
  const geometry = useMemo(() => new TubeGeometry(tunnelCurve, 500, TUNNEL_RADIUS, 96, false), []);
  const material = useMemo(
    () =>
      new ShaderMaterial({
        vertexShader: passthroughVertex,
        fragmentShader: /* glsl */ `
          varying vec2 vUv;
          uniform float uFlow;
          uniform float uVisibility;
          uniform float uGates[5];
          uniform vec3 uDeep[6];
          uniform vec3 uBright[6];
          ${NOISE_GLSL}
          void main() {
            float along = vUv.x;
            vec3 deep = uDeep[0];
            vec3 bright = uBright[0];
            for (int i = 0; i < 5; i++) {
              float t = smoothstep(uGates[i] - 0.006, uGates[i] + 0.006, along);
              deep = mix(deep, uDeep[i + 1], t);
              bright = mix(bright, uBright[i + 1], t);
            }
            float angle = vUv.y * 6.28318;
            vec3 p = vec3(cos(angle) * 1.6, sin(angle) * 1.6, along * 60.0 - uFlow);
            float clouds = fbm(p);
            float wisps = fbm(p * 2.7 + vec3(0.0, 0.0, uFlow * 0.4));
            float density = smoothstep(0.35, 0.85, clouds * 0.75 + wisps * 0.45);
            float star = step(0.985, hash3(floor(vec3(vUv.y * 400.0, along * 2600.0, 3.0))));
            vec3 color = mix(deep, bright, density) * (0.25 + density * 0.6) + vec3(star) * 0.8;
            float fade = smoothstep(0.0, 0.03, along) * smoothstep(1.0, 0.97, along);
            gl_FragColor = vec4(color * 0.85, (0.42 + density * 0.38) * fade * uVisibility);
          }
        `,
        uniforms: {
          uFlow: { value: 0 },
          uVisibility: { value: 0 },
          uGates: { value: RING_TUNNEL_FRACTIONS },
          uDeep: { value: [APPROACH.deep, ...UNIVERSES.map((universe) => universe.deep)] },
          uBright: { value: [APPROACH.bright, ...UNIVERSES.map((universe) => universe.bright)] },
        },
        side: BackSide,
        transparent: true,
        depthWrite: false,
      }),
    [],
  );
  useFrame((_state, delta) => {
    const { progress, speed } = effects.current;
    // From outside, the mouth should show lensed space, not the tunnel: reveal it only as the ship goes in.
    const inside = progress > mouthFlightFraction - 0.03 && progress < exitFlightFraction + 0.01;
    material.uniforms.uFlow.value += delta * (0.15 + speed * 7);
    material.uniforms.uVisibility.value = MathUtils.damp(material.uniforms.uVisibility.value, inside ? 1 : 0, 3, delta);
  });
  return <mesh geometry={geometry} material={material} renderOrder={-1} />;
}

/** A thin shimmering membrane at each gate. It ripples as the ship approaches and flares on crossing. */
export function Gates({ effects }: { effects: MutableRefObject<FlightEffects> }) {
  const gates = useMemo(
    () =>
      ringPositions.map((position, index) => {
        const material = new ShaderMaterial({
          vertexShader: passthroughVertex,
          fragmentShader: /* glsl */ `
            varying vec2 vUv;
            uniform float uTime;
            uniform float uApproach;
            uniform float uBurst;
            uniform vec3 uColor;
            ${NOISE_GLSL}
            void main() {
              vec2 c = vUv - 0.5;
              float r = length(c) * 2.0;
              if (r > 1.0) discard;
              float n = fbm(vec3(c * 5.0, uTime * 0.25));
              float ripple = sin(r * 34.0 - uTime * 3.0 + n * 6.0) * 0.5 + 0.5;
              float rim = smoothstep(0.82, 1.0, r) * (1.0 - smoothstep(0.98, 1.0, r));
              float sheet = (0.025 + 0.11 * uApproach) * (0.4 + ripple * n * 1.6);
              float alpha = rim * (0.28 + uBurst * 0.5) + sheet * (1.0 - uBurst * 0.8);
              gl_FragColor = vec4(uColor * (0.6 + uBurst * 1.2), alpha);
            }
          `,
          uniforms: { uTime: { value: 0 }, uApproach: { value: 0 }, uBurst: { value: 0 }, uColor: { value: UNIVERSES[index].bright.clone() } },
          transparent: true,
          depthWrite: false,
          blending: AdditiveBlending,
          side: DoubleSide,
        });
        return { position, look: position.clone().add(tunnelCurve.getTangentAt(RING_TUNNEL_FRACTIONS[index])), material };
      }),
    [],
  );

  useFrame(({ clock }) => {
    const { progress, pulse, pulseGate } = effects.current;
    gates.forEach(({ material }, index) => {
      const distance = ringFlightFractions[index] - progress;
      material.uniforms.uTime.value = clock.elapsedTime;
      material.uniforms.uApproach.value = distance > 0 ? Math.max(0, 1 - distance / 0.08) : 0;
      material.uniforms.uBurst.value = pulseGate === index ? pulse : 0;
    });
  });

  return (
    <>
      {gates.map(({ position, look, material }, index) => (
        <mesh key={UNIVERSES[index].name} position={position} ref={(node) => node?.lookAt(look)} material={material}>
          <circleGeometry args={[TUNNEL_RADIUS * 0.97, 96]} />
        </mesh>
      ))}
    </>
  );
}

function haloTexture() {
  const canvas = document.createElement("canvas");
  canvas.width = canvas.height = 256;
  const context = canvas.getContext("2d")!;
  const gradient = context.createRadialGradient(128, 128, 40, 128, 128, 128);
  gradient.addColorStop(0, "rgba(255,255,255,0.0)");
  gradient.addColorStop(0.42, "rgba(210,225,255,0.55)");
  gradient.addColorStop(0.5, "rgba(170,190,255,0.25)");
  gradient.addColorStop(1, "rgba(120,140,255,0)");
  context.fillStyle = gradient;
  context.fillRect(0, 0, 256, 256);
  return new CanvasTexture(canvas);
}

/**
 * The wormhole mouth: a lensing sphere that bends the space behind it, with a thin bright
 * Einstein ring at its edge and a soft halo. Only the entrance refracts (it is the costly part).
 */
export function WormholeMouth({ at, lensing }: { at: number; lensing: boolean }) {
  const halo = useMemo(haloTexture, []);
  const rim = useMemo(
    () =>
      new ShaderMaterial({
        vertexShader: passthroughVertex,
        fragmentShader: /* glsl */ `
          varying vec3 vNormalView;
          varying vec3 vViewDir;
          void main() {
            float facing = clamp(dot(normalize(vNormalView), normalize(vViewDir)), 0.0, 1.0);
            float ring = pow(1.0 - facing, 5.0);
            gl_FragColor = vec4(vec3(0.85, 0.9, 1.0) * ring * 2.2, ring);
          }
        `,
        transparent: true,
        depthWrite: false,
        blending: AdditiveBlending,
        side: FrontSide,
      }),
    [],
  );
  const position = useMemo(() => tunnelCurve.getPointAt(at), [at]);
  const radius = TUNNEL_RADIUS * 0.95;

  return (
    <group position={position}>
      {lensing ? (
        <mesh>
          <sphereGeometry args={[radius, 96, 64]} />
          <MeshTransmissionMaterial
            resolution={512}
            samples={6}
            thickness={radius * 1.4}
            ior={1.3}
            roughness={0}
            chromaticAberration={0.035}
            anisotropicBlur={0.08}
            distortion={0.18}
            distortionScale={0.35}
            temporalDistortion={0.05}
            color="#c9d4f2"
            envMapIntensity={0.08}
            backside={false}
          />
        </mesh>
      ) : null}
      <mesh material={rim} scale={1.01}>
        <sphereGeometry args={[radius, 96, 64]} />
      </mesh>
      <sprite scale={[radius * 3.4, radius * 3.4, 1]}>
        <spriteMaterial map={halo} transparent depthWrite={false} blending={AdditiveBlending} opacity={0.32} />
      </sprite>
    </group>
  );
}

/** A metal landing platform with small edge lights, under the hovering ship. */
export function Pad({ position }: { position: Vector3 }) {
  const lights = useRef<MeshBasicMaterial[]>([]);
  useFrame(({ clock }) => {
    lights.current.forEach((material, index) => {
      const on = Math.sin(clock.elapsedTime * 2 - index * 0.8) > 0.2;
      material.color.set("#ffb547").multiplyScalar(on ? 3 : 0.4);
    });
  });
  return (
    <group position={[position.x, position.y - 1.2, position.z]}>
      <mesh receiveShadow>
        <cylinderGeometry args={[2.3, 2.45, 0.16, 64]} />
        <meshStandardMaterial color="#2b2f36" metalness={0.85} roughness={0.42} />
      </mesh>
      <mesh position={[0, 0.085, 0]} rotation={[-Math.PI / 2, 0, 0]} receiveShadow>
        <ringGeometry args={[1.05, 1.12, 64]} />
        <meshStandardMaterial color="#c8cdd6" metalness={0.6} roughness={0.5} />
      </mesh>
      {Array.from({ length: 10 }, (_, index) => {
        const angle = (index / 10) * Math.PI * 2;
        return (
          <mesh key={index} position={[Math.cos(angle) * 2.18, 0.1, Math.sin(angle) * 2.18]}>
            <sphereGeometry args={[0.035, 10, 10]} />
            <meshBasicMaterial
              ref={(material) => {
                if (material) lights.current[index] = material;
              }}
              toneMapped={false}
            />
          </mesh>
        );
      })}
      <mesh position={[0, -0.6, 0]}>
        <cylinderGeometry args={[0.25, 0.4, 1.1, 24]} />
        <meshStandardMaterial color="#1d2026" metalness={0.8} roughness={0.5} />
      </mesh>
    </group>
  );
}
