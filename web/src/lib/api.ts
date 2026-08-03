/**
 * Typed fetch wrappers for the voting API. Every shape here mirrors
 * api/sabha/schemas.py; a change to one is not complete without the other.
 * Paths are relative so the same code works against the Vite dev proxy
 * and the same-origin deployed build without an API base URL to configure.
 */

export interface Consultation {
  id: number;
  title: string;
  question: string;
  department: string | null;
  is_synthetic: boolean;
  opens_at: string;
  closes_at: string;
}

export interface Statement {
  id: number;
  code: string;
  text: string;
  language: string;
  author_type: "participant" | "generated";
  parent_statement_id: number | null;
  is_synthetic: boolean;
}

export interface JoinResponse {
  participant_id: number;
  session_token: string;
}

export type VoteValue = 1 | -1;

export interface VoteResponse {
  id: number;
  statement_id: number;
  value: VoteValue;
  created_at: string;
}

export interface RankingEntry {
  statement_id: number;
  code: string;
  text: string;
  score: number;
  rank: number;
}

export interface Rankings {
  model_run_id: number | null;
  model_run_created_at: string | null;
  bridging: RankingEntry[];
  majority: RankingEntry[];
}

export interface OpinionMapPoint {
  participant_id: number;
  factor: [number, number];
  cluster: number;
  is_self: boolean;
}

export interface OpinionMap {
  model_run_id: number;
  k_clusters: number;
  points: OpinionMapPoint[];
}

export interface ClusterSupport {
  cluster: number;
  participant_count: number;
  agree_count: number;
  agree_fraction: number;
}

export interface Certificate {
  model_run_id: number;
  statement: Statement;
  participant_count: number;
  clusters: ClusterSupport[];
}

export interface RankingsPushMessage {
  type: "rankings";
  model_run_id: number;
  bridging: RankingEntry[];
  majority: RankingEntry[];
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    ...init,
    headers: { "content-type": "application/json", ...init?.headers },
  });
  if (!response.ok) {
    const body: unknown = await response.json().catch(() => null);
    const detail =
      body && typeof body === "object" && "detail" in body ? String(body.detail) : response.statusText;
    throw new ApiError(response.status, detail);
  }
  return response.json() as Promise<T>;
}

export function listConsultations(): Promise<Consultation[]> {
  return request("/api/consultations");
}

export function listStatements(consultationId: number): Promise<Statement[]> {
  return request(`/api/consultations/${consultationId}/statements`);
}

export function joinConsultation(consultationId: number): Promise<JoinResponse> {
  return request(`/api/consultations/${consultationId}/join`, { method: "POST" });
}

export function fetchNextStatement(
  consultationId: number,
  sessionToken: string,
): Promise<Statement | null> {
  const query = new URLSearchParams({ session_token: sessionToken });
  return request(`/api/consultations/${consultationId}/statements/next?${query.toString()}`);
}

export function castVote(
  consultationId: number,
  sessionToken: string,
  statementId: number,
  value: VoteValue,
): Promise<VoteResponse> {
  return request(`/api/consultations/${consultationId}/votes`, {
    method: "POST",
    body: JSON.stringify({ session_token: sessionToken, statement_id: statementId, value }),
  });
}

export function fetchRankings(consultationId: number): Promise<Rankings> {
  return request(`/api/consultations/${consultationId}/rankings`);
}

export function fetchOpinionMap(
  consultationId: number,
  sessionToken?: string,
): Promise<OpinionMap> {
  const query = sessionToken ? `?${new URLSearchParams({ session_token: sessionToken })}` : "";
  return request(`/api/consultations/${consultationId}/opinion-map${query}`);
}

export function fetchCertificate(consultationId: number): Promise<Certificate> {
  return request(`/api/consultations/${consultationId}/certificate`);
}

export function liveSessionUrl(consultationId: number): string {
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/api/consultations/${consultationId}/live`;
}
