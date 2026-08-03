import { animate, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { Figure } from "../../components/Figure";

const DUR_TALLY_SECONDS = 0.4; // --dur-tally
const EASE: [number, number, number, number] = [0.2, 0, 0.13, 1]; // --ease

interface RollingFigureProps {
  value: number;
  decimals?: number;
  ariaLabel?: string;
}

/**
 * The one other half of the single orchestrated motion moment: a
 * statement's bridging figure rolls to its new value rather than
 * snapping, when a refit changes it. Only rolls on a change after
 * mount; the first paint is never animated.
 */
export function RollingFigure({ value, decimals = 2, ariaLabel }: RollingFigureProps) {
  const prefersReducedMotion = useReducedMotion();
  const [display, setDisplay] = useState(value);
  const previous = useRef(value);

  useEffect(() => {
    if (previous.current === value) return;
    if (prefersReducedMotion) {
      setDisplay(value);
      previous.current = value;
      return;
    }
    const controls = animate(previous.current, value, {
      duration: DUR_TALLY_SECONDS,
      ease: EASE,
      onUpdate: setDisplay,
    });
    previous.current = value;
    return () => controls.stop();
  }, [value, prefersReducedMotion]);

  return (
    <Figure value={display.toFixed(decimals)} {...(ariaLabel ? { "aria-label": ariaLabel } : {})} />
  );
}
