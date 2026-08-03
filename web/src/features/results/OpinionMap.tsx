import { extent } from "d3-array";
import { scaleLinear } from "d3-scale";
import { motion, useReducedMotion } from "framer-motion";
import { useMemo } from "react";

import type { OpinionMapPoint } from "../../lib/api";

const MAP_SIZE = 560;
const PADDING = 40;
const STROKE_LENGTH = 10;
const SETTLE_DURATION_SECONDS = 0.24; // --dur-settle
const EASE: [number, number, number, number] = [0.2, 0, 0.13, 1]; // --ease

const FACTION_COLOURS = [
  "var(--faction-1)",
  "var(--faction-2)",
  "var(--faction-3)",
  "var(--faction-4)",
  "var(--faction-5)",
];

export function factionColour(cluster: number): string {
  return FACTION_COLOURS.at(cluster % FACTION_COLOURS.length) ?? "var(--faction-1)";
}

interface Scales {
  x: (value: number) => number;
  y: (value: number) => number;
}

function buildScales(points: OpinionMapPoint[]): Scales {
  const xs = points.map((p) => p.factor[0]);
  const ys = points.map((p) => p.factor[1]);
  const [xMin, xMax] = extent(xs.length ? xs : [0]);
  const [yMin, yMax] = extent(ys.length ? ys : [0]);
  const maxAbs = Math.max(
    Math.abs(xMin ?? 0),
    Math.abs(xMax ?? 0),
    Math.abs(yMin ?? 0),
    Math.abs(yMax ?? 0),
    0.5,
  );
  const domain: [number, number] = [-maxAbs, maxAbs];
  return {
    x: scaleLinear().domain(domain).range([PADDING, MAP_SIZE - PADDING]),
    y: scaleLinear().domain(domain).range([MAP_SIZE - PADDING, PADDING]),
  };
}

function angleDegrees(factor: readonly [number, number]): number {
  return (Math.atan2(factor[1], factor[0]) * 180) / Math.PI;
}

interface OpinionMapProps {
  points: OpinionMapPoint[];
}

/**
 * A field of tally strokes, not a scatter plot: each participant is a
 * short line rotated by their own factor angle and positioned by their
 * factor coordinates. Every stroke but the participant's own is a plain
 * SVG element with no motion component wrapping it, which is what keeps
 * two thousand of them cheap to paint; only the self stroke, at most
 * one per render, ever animates, on a refit that moves its position.
 */
export function OpinionMap({ points }: OpinionMapProps) {
  const prefersReducedMotion = useReducedMotion();
  const scales = useMemo(() => buildScales(points), [points]);

  const selfPoint = points.find((p) => p.is_self) ?? null;
  const otherPoints = points.filter((p) => !p.is_self);

  return (
    <svg
      className="opinion-map"
      viewBox={`0 0 ${MAP_SIZE} ${MAP_SIZE}`}
      width={MAP_SIZE}
      height={MAP_SIZE}
      aria-hidden="true"
    >
      {otherPoints.map((point) => {
        const x = scales.x(point.factor[0]);
        const y = scales.y(point.factor[1]);
        return (
          <line
            key={point.participant_id}
            x1={-STROKE_LENGTH / 2}
            y1={0}
            x2={STROKE_LENGTH / 2}
            y2={0}
            stroke={factionColour(point.cluster)}
            strokeWidth={1.5}
            opacity={0.7}
            transform={`translate(${x} ${y}) rotate(${angleDegrees(point.factor)})`}
          />
        );
      })}
      {selfPoint ? (
        <motion.g
          animate={{
            x: scales.x(selfPoint.factor[0]),
            y: scales.y(selfPoint.factor[1]),
            rotate: angleDegrees(selfPoint.factor),
          }}
          transition={
            prefersReducedMotion
              ? { duration: 0 }
              : { duration: SETTLE_DURATION_SECONDS, ease: EASE }
          }
        >
          <line
            x1={-STROKE_LENGTH / 2}
            y1={0}
            x2={STROKE_LENGTH / 2}
            y2={0}
            stroke="var(--ink)"
            strokeWidth={2.5}
          />
        </motion.g>
      ) : null}
    </svg>
  );
}
