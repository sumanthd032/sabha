import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { EmptyState } from "../../components/EmptyState";
import { ErrorNote } from "../../components/ErrorNote";
import { Link } from "../../lib/router";
import {
  fetchCertificate,
  fetchOpinionMap,
  fetchRankings,
  liveSessionUrl,
  listConsultations,
  type RankingsPushMessage,
} from "../../lib/api";
import { useSessionStore } from "../../store/sessionStore";
import { ConsensusCertificate } from "./ConsensusCertificate";
import { FactionLegend } from "./FactionLegend";
import { OpinionMap } from "./OpinionMap";
import { RankingsComparison } from "./RankingsComparison";
import "./results.css";

/**
 * The opinion map, the faction legend, both rankings, and the consensus
 * certificate. Subscribes to the live channel so a refit triggered by
 * anyone's vote, not only this participant's own, updates the screen:
 * the rankings push is applied directly, and the opinion map and
 * certificate, which the push does not carry, are refetched.
 */
export function ResultsScreen() {
  const queryClient = useQueryClient();

  const consultationsQuery = useQuery({ queryKey: ["consultations"], queryFn: listConsultations });
  const consultation = consultationsQuery.data?.[0] ?? null;
  const consultationId = consultation?.id ?? null;

  const sessionToken = useSessionStore((state) =>
    consultationId !== null ? state.sessions[consultationId]?.sessionToken : undefined,
  );

  const opinionMapQuery = useQuery({
    queryKey: ["opinion-map", consultationId, sessionToken],
    queryFn: () => fetchOpinionMap(consultationId as number, sessionToken),
    enabled: consultationId !== null,
  });

  const rankingsQuery = useQuery({
    queryKey: ["rankings", consultationId],
    queryFn: () => fetchRankings(consultationId as number),
    enabled: consultationId !== null,
  });

  const certificateQuery = useQuery({
    queryKey: ["certificate", consultationId],
    queryFn: () => fetchCertificate(consultationId as number),
    enabled: consultationId !== null,
    retry: false,
  });

  useEffect(() => {
    if (consultationId === null) return;
    const socket = new WebSocket(liveSessionUrl(consultationId));
    socket.onmessage = (event: MessageEvent<string>) => {
      const message: RankingsPushMessage = JSON.parse(event.data);
      if (message.type !== "rankings") return;
      queryClient.setQueryData(["rankings", consultationId], {
        model_run_id: message.model_run_id,
        model_run_created_at: new Date().toISOString(),
        bridging: message.bridging,
        majority: message.majority,
      });
      void queryClient.invalidateQueries({ queryKey: ["opinion-map", consultationId] });
      void queryClient.invalidateQueries({ queryKey: ["certificate", consultationId] });
    };
    return () => socket.close();
  }, [consultationId, queryClient]);

  if (consultationsQuery.isError) {
    return (
      <main className="results-screen">
        <ErrorNote
          heading="This consultation did not load"
          body="Check your connection and reload the page to try again."
        />
      </main>
    );
  }

  if (consultationsQuery.isLoading || !consultation) {
    return <main className="results-screen" aria-busy="true" />;
  }

  const opinionMap = opinionMapQuery.data;
  const rankings = rankingsQuery.data;
  const certificate = certificateQuery.data;
  const hasResults = rankings?.model_run_id != null && opinionMap;

  return (
    <main className="results-screen">
      <header className="results-screen__header">
        <h1 className="results-screen__title">{consultation.title}</h1>
        {consultation.is_synthetic ? (
          <p className="voting-screen__synthetic-note">
            This consultation runs on synthetic data, generated for this build rather than
            collected from real submissions.
          </p>
        ) : null}
        <Link to="/">Back to voting</Link>
      </header>

      {!hasResults || !opinionMap || !rankings ? (
        <EmptyState
          heading="No results yet"
          body="Results appear once enough votes have been cast for a model run to fit. Check back after voting for a while."
        />
      ) : (
        <>
          <section aria-labelledby="opinion-map-heading">
            <h2 id="opinion-map-heading" className="results-screen__section-heading">
              Opinion map
            </h2>
            <div className="opinion-map-section">
              <OpinionMap points={opinionMap.points} />
              <FactionLegend points={opinionMap.points} kClusters={opinionMap.k_clusters} />
            </div>
          </section>

          <section aria-labelledby="rankings-heading">
            <h2 id="rankings-heading" className="results-screen__section-heading">
              Bridging ranking against the majority ranking
            </h2>
            <RankingsComparison bridging={rankings.bridging} majority={rankings.majority} />
          </section>

          {certificate ? <ConsensusCertificate certificate={certificate} /> : null}
        </>
      )}
    </main>
  );
}
