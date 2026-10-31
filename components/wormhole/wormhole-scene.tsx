"use client";

import { useEffect, useMemo, useRef, useState, type MutableRefObject } from "react";
import { Canvas, useFrame } from "@react-three/fiber";
import { Environment, Html, Lightformer, Stars } from "@react-three/drei";
import { Bloom, ChromaticAberration, EffectComposer, Noise, Vignette } from "@react-three/postprocessing";
import type { ChromaticAberrationEffect } from "postprocessing";
import {
  AdditiveBlending,
  BackSide,
  BoxGeometry,
  BufferAttribute,
  BufferGeometry,
  LineBasicMaterial,
  DirectionalLight,
  Group,
  InstancedMesh,
  MathUtils,
  MeshBasicMaterial,
  Object3D,
  PerspectiveCamera,
  ShaderMaterial,
  Vector2,
  Vector3,
} from "three";
import { GEAR_HEIGHT, Ship } from "./ship";
import { StatCard, type ShipStat } from "./relay-panels";
import { Gates, NOISE_GLSL, Pad, Tunnel, WormholeMouth, type FlightEffects } from "./tunnel";
import {
  ARRIVAL_POINT,
  LAUNCH_POINT,
  exitFlightFraction,
  flightCurve,
  mouthFlightFraction,
  ringFlightFractions,
  targetProgress,
  type FlightPhase,
} from "./flight-path";

type SceneProps = {
  phase: FlightPhase;
  /** How many pipeline steps have started (0 before launch). */
  stage: number;
  reducedMotion: boolean;
  onArrived: () => void;
  /** Called with the number of gates the ship has crossed whenever it changes. */
  onPassed: (count: number) => void;
  /** True when the backend ran a corrective retry: the ship flies a loop before exiting. */
  retry: boolean;
  /** Called once when the retry loop starts. */
  onRetry: () => void;
  /** Answer scores shown as call-outs around the ship once it has landed. */
  stats: ShipStat[];
  showStats: boolean;
};

const BASE_FOV = 46;
const IDLE_CAMERA = LAUNCH_POINT.clone().add(new Vector3(0.6, 3.0, 9.6));
const IDLE_LOOK = LAUNCH_POINT.clone().add(new Vector3(-3.4, -1.5, -1.8));
const ARRIVAL_CAMERA = ARRIVAL_POINT.clone().add(new Vector3(-1.2, 3.8, 10.2));
const ARRIVAL_LOOK = ARRIVAL_POINT.clone().add(new Vector3(3.3, -0.5, 0));
/** Hover point to pad surface, minus the gear: how far the ship sinks when it sets down. */
const PAD_DROP = 1.12 - GEAR_HEIGHT;

/** Where each call-out points on the ship (ship-local) and where its card sits (camera right/up). */
const STAT_LAYOUT: Record<string, { anchor: [number, number, number]; offset: [number, number] }> = {
  grounding: { anchor: [0, 0.18, 3.2], offset: [0.1, 1.15] },
  faithfulness: { anchor: [0, 0.5, 1.95], offset: [-1.3, 1.9] },
  relevance: { anchor: [-3.5, 0.05, -1.05], offset: [0.4, 1.9] },
  risk: { anchor: [3.5, 0.05, -1.05], offset: [-0.6, -1.5] },
  sources: { anchor: [0, 0.4, -1.5], offset: [2.2, 1.1] },
  roundtrip: { anchor: [0.6, 0.05, -2.55], offset: [0.3, -1.9] },
};
const MAX_SPEED = 0.16;
/** Seconds the ship stays in each universe at minimum, so its title card can be read. */
const MIN_DWELL = 1.4;
/** The corrective-retry loop: where on the route it starts, how long it takes, and its size. */
const LOOP_AT = exitFlightFraction - 0.045;
const LOOP_SECONDS = 2.4;
const LOOP_RADIUS = 1.3;
const WORLD_UP = new Vector3(0, 1, 0);
const SUN_OFFSET = new Vector3(-6, 7, 5);

const skyFragment = /* glsl */ `
  varying vec3 vDir;
  ${NOISE_GLSL}
  void main() {
    vec3 d = normalize(vDir);
    float clouds = fbm(d * 3.0 + vec3(0.0, 0.0, 1.7));
    float fine = fbm(d * 8.0 + 4.0);
    float band = exp(-pow(d.y * 2.4 + sin(d.x * 2.0) * 0.35, 2.0));
    vec3 color = vec3(0.004, 0.006, 0.013);
    color += vec3(0.16, 0.11, 0.24) * pow(clouds, 3.0) * 1.8 * band;
    color += vec3(0.04, 0.09, 0.13) * pow(fine, 4.0) * 1.4;
    color += vec3(0.42, 0.27, 0.15) * pow(max(dot(d, normalize(vec3(-0.6, 0.25, -0.75))), 0.0), 18.0) * 0.5;
    gl_FragColor = vec4(color, 1.0);
  }
`;

function Sky() {
  const material = useMemo(
    () =>
      new ShaderMaterial({
        side: BackSide,
        depthWrite: false,
        fog: false,
        vertexShader: /* glsl */ `
          varying vec3 vDir;
          void main() {
            vDir = normalize(position);
            gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
          }
        `,
        fragmentShader: skyFragment,
      }),
    [],
  );
  return (
    <mesh material={material} renderOrder={-2}>
      <sphereGeometry args={[280, 64, 32]} />
    </mesh>
  );
}

/** Star streaks that ride with the camera and stretch with speed while inside the wormhole. */
function WarpStreaks({ effects }: { effects: MutableRefObject<FlightEffects> }) {
  const count = 520;
  const group = useRef<Group>(null);
  const mesh = useRef<InstancedMesh>(null);
  const dummy = useMemo(() => new Object3D(), []);
  const geometry = useMemo(() => new BoxGeometry(0.012, 0.012, 1), []);
  const material = useMemo(() => new MeshBasicMaterial({ color: "#d6e4ff", transparent: true, opacity: 0, blending: AdditiveBlending, depthWrite: false }), []);
  const stars = useMemo(
    () =>
      Array.from({ length: count }, () => {
        const angle = Math.random() * Math.PI * 2;
        const radius = 0.7 + Math.random() * 3;
        return { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius, z: -Math.random() * 44 };
      }),
    [],
  );

  useFrame((state, rawDelta) => {
    const delta = Math.min(rawDelta, 0.05);
    const { progress, speed } = effects.current;
    const inside = progress > mouthFlightFraction && progress < exitFlightFraction;
    material.opacity = MathUtils.damp(material.opacity, inside ? 0.1 + speed * 0.4 : 0, 5, delta);
    if (!group.current || !mesh.current) return;
    group.current.visible = material.opacity > 0.01;
    group.current.position.copy(state.camera.position);
    group.current.quaternion.copy(state.camera.quaternion);
    const length = 0.08 + speed * 3.4;
    stars.forEach((star, index) => {
      star.z += delta * (4 + speed * 70);
      if (star.z > 2) star.z -= 46;
      dummy.position.set(star.x, star.y, star.z);
      dummy.scale.set(1, 1, length);
      dummy.updateMatrix();
      mesh.current!.setMatrixAt(index, dummy.matrix);
    });
    mesh.current.instanceMatrix.needsUpdate = true;
  });

  return (
    <group ref={group}>
      <instancedMesh ref={mesh} args={[geometry, material, count]} frustumCulled={false} />
    </group>
  );
}

/** Glass stat cards pinned to points on the landed ship by thin leader lines. */
function StatCallouts({
  ship,
  stats,
  show,
  effects,
}: {
  ship: MutableRefObject<Group | null>;
  stats: ShipStat[];
  show: boolean;
  effects: MutableRefObject<FlightEffects>;
}) {
  const [visible, setVisible] = useState(false);
  const visibleRef = useRef(false);
  const labels = useRef<Array<Group | null>>([]);
  const dots = useRef<Array<Group | null>>([]);
  const scratch = useMemo(() => ({ anchor: new Vector3(), label: new Vector3(), right: new Vector3(), up: new Vector3() }), []);
  const geometry = useMemo(() => {
    const lines = new BufferGeometry();
    lines.setAttribute("position", new BufferAttribute(new Float32Array(Object.keys(STAT_LAYOUT).length * 6), 3));
    return lines;
  }, []);
  const material = useMemo(() => new LineBasicMaterial({ color: "#e3e9ff", transparent: true, opacity: 0, depthTest: false }), []);

  useFrame((state, rawDelta) => {
    const delta = Math.min(rawDelta, 0.05);
    const ready = show && effects.current.landed;
    if (ready !== visibleRef.current) {
      visibleRef.current = ready;
      setVisible(ready);
    }
    material.opacity = MathUtils.damp(material.opacity, ready ? 0.5 : 0, 3, delta);
    if (!ship.current) return;
    const { anchor, label, right, up } = scratch;
    right.setFromMatrixColumn(state.camera.matrixWorld, 0);
    up.setFromMatrixColumn(state.camera.matrixWorld, 1);
    const positions = geometry.getAttribute("position") as BufferAttribute;
    stats.forEach((stat, index) => {
      const layout = STAT_LAYOUT[stat.key];
      if (!layout) return;
      ship.current!.localToWorld(anchor.set(...layout.anchor));
      label.copy(anchor).addScaledVector(right, layout.offset[0]).addScaledVector(up, layout.offset[1]);
      labels.current[index]?.position.copy(label);
      dots.current[index]?.position.copy(anchor);
      positions.setXYZ(index * 2, anchor.x, anchor.y, anchor.z);
      positions.setXYZ(index * 2 + 1, label.x, label.y, label.z);
    });
    positions.needsUpdate = true;
  });

  return (
    <>
      <lineSegments geometry={geometry} material={material} renderOrder={10} frustumCulled={false} />
      {stats.map((stat, index) => (
        <group key={stat.key}>
          <group
            ref={(node) => {
              dots.current[index] = node;
            }}
          >
            {visible ? (
              <mesh renderOrder={11}>
                <sphereGeometry args={[0.045, 12, 12]} />
                <meshBasicMaterial color="#ffffff" toneMapped={false} depthTest={false} />
              </mesh>
            ) : null}
          </group>
          <group
            ref={(node) => {
              labels.current[index] = node;
            }}
          >
            {visible ? (
              <Html zIndexRange={[20, 0]} style={{ pointerEvents: "none" }}>
                <StatCard stat={stat} index={index} align={(STAT_LAYOUT[stat.key]?.offset[0] ?? 1) < 0 ? "right" : "left"} />
              </Html>
            ) : null}
          </group>
        </group>
      ))}
    </>
  );
}

function FlightRig({
  phase,
  stage,
  reducedMotion,
  onArrived,
  onPassed,
  retry,
  onRetry,
  effects,
  thrust,
  gear,
  ship,
  sun,
  aberration,
}: Omit<SceneProps, "stats" | "showStats"> & {
  effects: MutableRefObject<FlightEffects>;
  thrust: MutableRefObject<number>;
  gear: MutableRefObject<number>;
  ship: MutableRefObject<Group | null>;
  sun: MutableRefObject<DirectionalLight | null>;
  aberration: MutableRefObject<ChromaticAberrationEffect | null>;
}) {
  const lift = useRef(0);
  const velocity = useRef(0);
  const previousPhase = useRef<FlightPhase>(phase);
  const arrivedSent = useRef(false);
  const passedSent = useRef(0);
  const lastCrossing = useRef(-Infinity);
  const loopStart = useRef(-1);
  const lookTarget = useRef(IDLE_LOOK.clone());
  const aim = useMemo(() => new Object3D(), []);
  const scratch = useMemo(() => ({ position: new Vector3(), ahead: new Vector3(), camera: new Vector3(), look: new Vector3() }), []);

  useFrame((state, rawDelta) => {
    const delta = Math.min(rawDelta, 0.05);
    const time = state.clock.elapsedTime;
    const fx = effects.current;

    if (phase !== previousPhase.current) {
      if (phase === "travel") {
        fx.progress = 0;
        velocity.current = 0;
        arrivedSent.current = false;
        passedSent.current = 0;
        lastCrossing.current = -Infinity;
        loopStart.current = -1;
      }
      previousPhase.current = phase;
    }

    const flying = phase === "travel" || phase === "landing";
    if (flying) {
      let target = phase === "landing" ? 1 : targetProgress(stage);
      // Hold the ship short of the next gate until it has spent MIN_DWELL in the current universe.
      const nextGate = ringFlightFractions[passedSent.current];
      if (nextGate !== undefined && time - lastCrossing.current < MIN_DWELL) target = Math.min(target, nextGate - 0.004);
      if (nextGate === undefined && time - lastCrossing.current < MIN_DWELL) target = Math.min(target, exitFlightFraction - 0.01);
      if (phase === "landing" && retry && loopStart.current < 0 && fx.progress >= LOOP_AT) {
        loopStart.current = time;
        fx.pulse = reducedMotion ? 0 : 0.7;
        fx.pulseGate = -1;
        onRetry();
      }
      if (loopStart.current >= 0 && time - loopStart.current < LOOP_SECONDS && !reducedMotion) {
        // Hold the route position while the ship flies its loop around it.
        velocity.current = MathUtils.damp(velocity.current, 0, 6, delta);
      } else {
        const limit = reducedMotion ? 10 : MAX_SPEED;
        const desired = MathUtils.clamp((target - fx.progress) * 2.4, -limit, limit);
        velocity.current = MathUtils.damp(velocity.current, desired, 3, delta);
        fx.progress = MathUtils.clamp(fx.progress + velocity.current * delta, 0, 1);
      }

      const crossed = ringFlightFractions.filter((fraction) => fx.progress >= fraction).length;
      if (crossed > passedSent.current) {
        passedSent.current = crossed;
        lastCrossing.current = time;
        fx.pulse = reducedMotion ? 0 : 1;
        fx.pulseGate = crossed - 1;
        onPassed(crossed);
      }
      if (phase === "landing" && fx.progress > 0.995 && !arrivedSent.current) {
        arrivedSent.current = true;
        onArrived();
      }
    } else {
      velocity.current = MathUtils.damp(velocity.current, 0, 4, delta);
    }
    fx.pulse = Math.max(0, fx.pulse - delta / 1.1);
    fx.speed = MathUtils.clamp(Math.abs(velocity.current) / MAX_SPEED, 0, 1);
    // Lift: 0 = parked on a pad on its gear, 1 = flying. Gear comes down near either pad.
    lift.current = MathUtils.damp(lift.current, flying || phase === "error" ? 1 : 0, flying ? 1.6 : 1.1, delta);
    const nearPad = !flying || fx.progress > 0.93;
    gear.current = MathUtils.damp(gear.current, nearPad || lift.current < 0.6 ? 1 : 0, 3, delta);
    fx.landed = phase === "arrived" && lift.current < 0.03;
    const idlePower = lift.current > 0.05 ? 0.22 : 0.02;
    thrust.current = MathUtils.damp(thrust.current, flying ? 0.3 + fx.speed * 0.7 : phase === "error" ? 0 : idlePower, 4, delta);

    const bob = reducedMotion ? 0 : Math.sin(time * 1.4) * 0.05 * lift.current;
    const drop = (1 - lift.current) * PAD_DROP;
    const { position, ahead, camera, look } = scratch;
    if (flying || phase === "error") {
      position.copy(flightCurve.getPointAt(fx.progress));
      position.y -= drop;
      ahead.copy(flightCurve.getPointAt(Math.min(fx.progress + 0.01, 1)));
    } else if (phase === "arrived") {
      position.copy(ARRIVAL_POINT).setY(ARRIVAL_POINT.y + bob - drop);
      ahead.copy(position).add(new Vector3(-2.2, 0, 1.1));
    } else {
      position.copy(LAUNCH_POINT).setY(LAUNCH_POINT.y + bob - drop);
      ahead.copy(position).add(new Vector3(-2.2, 0.1, -2));
    }

    const looping = flying && loopStart.current >= 0 && time - loopStart.current < LOOP_SECONDS && !reducedMotion;
    aim.up.copy(WORLD_UP);
    if (looping) {
      // A vertical loop in the plane of the route and "up": the ship climbs, goes inverted, and comes back down.
      const angle = ((time - loopStart.current) / LOOP_SECONDS) * Math.PI * 2;
      const tangent = flightCurve.getTangentAt(fx.progress);
      const up = WORLD_UP.clone().addScaledVector(tangent, -tangent.y).normalize();
      position.addScaledVector(up, LOOP_RADIUS * (1 - Math.cos(angle))).addScaledVector(tangent, LOOP_RADIUS * Math.sin(angle));
      ahead.copy(position).add(tangent.clone().multiplyScalar(Math.cos(angle)).addScaledVector(up, Math.sin(angle)));
      aim.up.copy(up).multiplyScalar(Math.cos(angle)).addScaledVector(tangent, -Math.sin(angle));
    }

    if (ship.current) {
      ship.current.position.copy(position);
      aim.position.copy(position);
      aim.lookAt(ahead);
      const roll = reducedMotion ? 0 : flying ? Math.sin(time * 1.8) * 0.06 * fx.speed : Math.sin(time * 0.8) * 0.03 * lift.current;
      aim.rotateZ(roll);
      ship.current.quaternion.slerp(aim.quaternion, 1 - Math.exp(-delta * (looping ? 14 : 5)));
    }

    if (sun.current) {
      sun.current.position.copy(position).add(SUN_OFFSET);
      sun.current.target.position.copy(position);
      sun.current.target.updateMatrixWorld();
    }

    // Narrower windows: pull the showcase camera back and centre the ship more.
    const aspect = state.size.width / Math.max(1, state.size.height);
    const pullBack = MathUtils.clamp(1.75 / aspect, 1, 1.45);
    const shift = MathUtils.clamp((aspect - 1) / 0.8, 0.25, 1);
    if (phase === "idle" || (flying && fx.progress < 0.02)) {
      camera.copy(IDLE_CAMERA).sub(LAUNCH_POINT).multiplyScalar(pullBack).add(LAUNCH_POINT);
      look.copy(IDLE_LOOK).sub(LAUNCH_POINT).multiply(new Vector3(shift, 1, 1)).add(LAUNCH_POINT);
    } else if (phase === "arrived" || (flying && fx.progress > 0.975)) {
      camera.copy(ARRIVAL_CAMERA).sub(ARRIVAL_POINT).multiplyScalar(pullBack).add(ARRIVAL_POINT);
      look.copy(ARRIVAL_LOOK).sub(ARRIVAL_POINT).multiply(new Vector3(shift, 1, 1)).add(ARRIVAL_POINT);
    } else {
      // During the retry loop, stand further back and higher so the whole loop stays in frame.
      camera.copy(flightCurve.getPointAt(Math.max(fx.progress - (looping ? 0.075 : 0.03), 0))).add(new Vector3(0, looping ? 1.3 : 0.6, 0));
      if (looping) look.copy(position);
      else look.copy(flightCurve.getPointAt(Math.min(fx.progress + 0.035, 1)));
    }
    const follow = reducedMotion ? 1 : 1 - Math.exp(-delta * (flying ? 4 : 2.2));
    state.camera.position.lerp(camera, follow);
    if (fx.pulse > 0) {
      const shake = fx.pulse * fx.pulse * 0.14;
      state.camera.position.x += (Math.random() - 0.5) * shake;
      state.camera.position.y += (Math.random() - 0.5) * shake;
    }
    lookTarget.current.lerp(look, follow);
    state.camera.lookAt(lookTarget.current);

    const perspective = state.camera as PerspectiveCamera;
    const fov = BASE_FOV + Math.sin(Math.min(fx.pulse, 1) * Math.PI) * 18;
    if (Math.abs(perspective.fov - fov) > 0.01) {
      perspective.fov = fov;
      perspective.updateProjectionMatrix();
    }
    const split = 0.0004 + fx.pulse * 0.0035;
    aberration.current?.offset.set(split, split * 0.6);
  });

  return <Ship ref={ship} thrust={thrust} gear={gear} />;
}

export function WormholeScene({ stats, showStats, ...props }: SceneProps) {
  const effects = useRef<FlightEffects>({ progress: 0, speed: 0, pulse: 0, pulseGate: -1, landed: false });
  const thrust = useRef(0.02);
  const gear = useRef(1);
  const ship = useRef<Group | null>(null);
  const sun = useRef<DirectionalLight | null>(null);
  const aberration = useRef<ChromaticAberrationEffect | null>(null);
  const aberrationOffset = useMemo(() => new Vector2(0.0005, 0.0003), []);

  useEffect(() => {
    if (sun.current) {
      sun.current.shadow.mapSize.set(1024, 1024);
      Object.assign(sun.current.shadow.camera, { left: -5, right: 5, top: 5, bottom: -5, near: 1, far: 30 });
      sun.current.shadow.bias = -0.0004;
    }
  }, []);

  return (
    <Canvas
      shadows
      dpr={[1, 1.75]}
      camera={{ fov: BASE_FOV, near: 0.1, far: 700, position: IDLE_CAMERA.toArray() }}
      gl={{ antialias: true, powerPreference: "high-performance" }}
    >
      <color attach="background" args={["#020309"]} />
      <fog attach="fog" args={["#020309", 45, 180]} />
      <Environment resolution={256} frames={1} environmentIntensity={0.9}>
        <Sky />
        <Lightformer form="circle" intensity={6} color="#fff1dc" position={[-8, 7, 6]} scale={3} />
        <Lightformer form="rect" intensity={1.4} color="#9fb8ff" position={[7, 1, -6]} scale={[10, 3, 1]} />
        {/* A bright planet-like glow below, a soft sky panel above and a warm rim: what the chrome reflects. */}
        <Lightformer form="rect" intensity={1.6} color="#e6eeff" position={[0, 8, 0]} rotation-x={Math.PI / 2} scale={[14, 14, 1]} />
        <Lightformer form="rect" intensity={1.8} color="#8fb7ff" position={[0, -6, 0]} rotation-x={Math.PI / 2} scale={[16, 16, 1]} />
        <Lightformer form="rect" intensity={2.2} color="#ffc48a" position={[9, 1.5, 2]} rotation-y={-Math.PI / 2} scale={[7, 10, 1]} />
      </Environment>
      <ambientLight intensity={0.05} />
      <directionalLight ref={sun} castShadow intensity={3.4} color="#fff0dc" position={LAUNCH_POINT.clone().add(SUN_OFFSET).toArray()} />
      <directionalLight intensity={0.9} color="#7f9cff" position={[6, 2, -10]} />

      <Sky />
      <Stars radius={200} depth={90} count={7000} factor={3.2} saturation={0.1} fade speed={0.3} />
      <Tunnel effects={effects} />
      <Gates effects={effects} />
      <WormholeMouth at={0} lensing />
      <WormholeMouth at={1} lensing={false} />
      <Pad position={LAUNCH_POINT} />
      <Pad position={ARRIVAL_POINT} />
      <WarpStreaks effects={effects} />
      <FlightRig {...props} effects={effects} thrust={thrust} gear={gear} ship={ship} sun={sun} aberration={aberration} />
      <StatCallouts ship={ship} stats={stats} show={showStats && props.phase === "arrived"} effects={effects} />

      <EffectComposer multisampling={4}>
        <Bloom mipmapBlur intensity={0.55} luminanceThreshold={1} luminanceSmoothing={0.15} />
        <ChromaticAberration
          // The library types this ref as the effect class rather than an instance, so take it via a callback.
          ref={(effect: unknown) => {
            aberration.current = effect as ChromaticAberrationEffect | null;
          }}
          offset={aberrationOffset}
          radialModulation={false}
          modulationOffset={0}
        />
        <Noise opacity={0.035} />
        <Vignette offset={0.28} darkness={0.72} />
      </EffectComposer>
    </Canvas>
  );
}
