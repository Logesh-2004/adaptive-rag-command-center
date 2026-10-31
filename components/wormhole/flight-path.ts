import { CatmullRomCurve3, Color, Vector3 } from "three";

export type FlightPhase = "idle" | "travel" | "landing" | "arrived" | "error";

export type Universe = {
  numeral: string;
  name: string;
  layer: string;
  tagline: string;
  /** Deep and bright tones of this universe's dust, used inside the tunnel. */
  deep: Color;
  bright: Color;
};

/** One universe per pipeline layer. The ship crosses a gate into each one as that step starts. */
export const UNIVERSES: Universe[] = [
  { numeral: "I", name: "The Archive", layer: "Retrieve", tagline: "Searching the local corpus", deep: new Color("#1c1206"), bright: new Color("#c9984f") },
  { numeral: "II", name: "The Sorting Drift", layer: "Rank", tagline: "Weighing every passage", deep: new Color("#06191a"), bright: new Color("#5aa898") },
  { numeral: "III", name: "The Narrows", layer: "Compress", tagline: "Folding context to fit", deep: new Color("#1a0712"), bright: new Color("#a8506f") },
  { numeral: "IV", name: "The Forge", layer: "Generate", tagline: "Shaping the answer", deep: new Color("#1f0b03"), bright: new Color("#e0773a") },
  { numeral: "V", name: "The Proving Ground", layer: "Ground", tagline: "Checking every claim", deep: new Color("#080e1d"), bright: new Color("#93a9d6") },
];

/** The space between the wormhole mouth and the first gate. */
export const APPROACH = { deep: new Color("#050a18"), bright: new Color("#4a6aa8") };

export const LAYERS = UNIVERSES.map((universe) => universe.layer);

/** Where the ship waits before launch, and where it hovers after landing. */
export const LAUNCH_POINT = new Vector3(2.4, 0.2, 5);
export const ARRIVAL_POINT = new Vector3(1.4, 0.4, -98);

export const TUNNEL_RADIUS = 4;

const MOUTH = new Vector3(0, 0, -6);
const EXIT = new Vector3(0, 0, -72);

/** The wormhole itself: from its mouth to its exit. */
export const tunnelCurve = new CatmullRomCurve3([
  MOUTH,
  new Vector3(-2.5, 1.2, -18),
  new Vector3(2.2, -1.2, -31),
  new Vector3(-1.8, 1.0, -45),
  new Vector3(1.4, -0.6, -58),
  EXIT,
]);

/** The ship's whole route: launch pad, through the tunnel, to the arrival pad. */
export const flightCurve = new CatmullRomCurve3([
  LAUNCH_POINT,
  new Vector3(1.2, 0.1, 0),
  ...tunnelCurve.getSpacedPoints(40),
  new Vector3(0.8, 0.3, -82),
  new Vector3(1.2, 0.4, -90),
  ARRIVAL_POINT,
]);

/** The five gates, as fractions along the tunnel. */
export const RING_TUNNEL_FRACTIONS = [0.14, 0.31, 0.48, 0.65, 0.82];

export const ringPositions = RING_TUNNEL_FRACTIONS.map((fraction) => tunnelCurve.getPointAt(fraction));

function nearestFlightFraction(point: Vector3) {
  let best = 0;
  let bestDistance = Infinity;
  const samples = 800;
  for (let index = 0; index <= samples; index += 1) {
    const fraction = index / samples;
    const distance = flightCurve.getPointAt(fraction).distanceTo(point);
    if (distance < bestDistance) {
      bestDistance = distance;
      best = fraction;
    }
  }
  return best;
}

/** The same gates as fractions along the ship's route, so ship progress can be compared with them. */
export const ringFlightFractions = ringPositions.map(nearestFlightFraction);
export const mouthFlightFraction = nearestFlightFraction(MOUTH);
export const exitFlightFraction = nearestFlightFraction(EXIT);

/**
 * How many steps have started -> where the ship should be.
 * Once step N starts the ship crosses gate N and cruises most of the way through universe N,
 * then waits there until the next step starts.
 */
export function targetProgress(started: number): number {
  if (started <= 0) return ringFlightFractions[0] - 0.04;
  if (started > UNIVERSES.length) return 1;
  const gate = ringFlightFractions[started - 1];
  const next = started < UNIVERSES.length ? ringFlightFractions[started] : exitFlightFraction;
  return gate + (next - gate) * 0.8;
}
