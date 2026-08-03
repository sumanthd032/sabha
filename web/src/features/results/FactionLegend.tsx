import { Figure } from "../../components/Figure";
import type { OpinionMapPoint } from "../../lib/api";
import { factionColour } from "./OpinionMap";

interface ClusterCount {
  cluster: number;
  count: number;
  isSelfCluster: boolean;
}

function summarise(points: OpinionMapPoint[], kClusters: number): ClusterCount[] {
  const counts = new Map<number, number>();
  for (let cluster = 0; cluster < kClusters; cluster += 1) counts.set(cluster, 0);
  let selfCluster: number | null = null;
  for (const point of points) {
    counts.set(point.cluster, (counts.get(point.cluster) ?? 0) + 1);
    if (point.is_self) selfCluster = point.cluster;
  }
  return Array.from(counts.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([cluster, count]) => ({ cluster, count, isSelfCluster: cluster === selfCluster }));
}

interface FactionLegendProps {
  points: OpinionMapPoint[];
  kClusters: number;
}

/**
 * The legend, the arbitrariness note, and the map's text alternative in
 * one component: below 640px this is not a supplement to the map, it is
 * the whole faction breakdown, per section 5.4's collapse rule.
 */
export function FactionLegend({ points, kClusters }: FactionLegendProps) {
  const clusters = summarise(points, kClusters);
  const selfCluster = clusters.find((c) => c.isSelfCluster);

  return (
    <div className="faction-legend">
      <ul className="faction-legend__list">
        {clusters.map((cluster) => (
          <li key={cluster.cluster} className="faction-legend__item">
            <span
              className="faction-legend__swatch"
              style={{ background: factionColour(cluster.cluster) }}
              aria-hidden="true"
            />
            <span className="faction-legend__label">
              Faction {cluster.cluster + 1}
              {cluster.isSelfCluster ? ", you" : ""}
            </span>
            <Figure
              value={cluster.count}
              aria-label={`${cluster.count} participants in faction ${cluster.cluster + 1}`}
            />
          </li>
        ))}
      </ul>
      <p className="faction-legend__note">
        Colours are assigned by cluster number and carry no political meaning.
      </p>
      <p className="faction-legend__summary">
        {points.length} participants placed into {kClusters} factions by this model run.
        {selfCluster ? ` You are in faction ${selfCluster.cluster + 1}.` : ""}
      </p>
    </div>
  );
}
