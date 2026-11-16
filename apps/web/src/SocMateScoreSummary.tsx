import type { DeepTeamAuditReport } from "./modelConnectivityService";

const object = (value: unknown): Record<string, unknown> => value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const list = (value: unknown) => Array.isArray(value) ? value.map(object) : [];

export function SocMateScoreSummary({ audit }: { audit: DeepTeamAuditReport | null }) {
  if (!audit) return null;
  const paths = list(audit.evidence.paths), reviews = list(audit.evidence.review_results);
  if (!paths.length) return null;
  return <dl className="socmate-score-summary" aria-label="Recorded Judge scores">{paths.map((path, index) => {
    const review = reviews.find(review => review.path_id === path.path_id);
    const evaluation = object(review?.target_evaluation);
    const score = evaluation.deviation_score, confidence = evaluation.confidence;
    const validScore = typeof score === "number" && Number.isInteger(score) && score >= 0 && score <= 100;
    const validConfidence = typeof confidence === "number" && Number.isFinite(confidence) && confidence >= 0 && confidence <= 1;
    return <div key={String(path.path_id ?? index)} className="socmate-path-score"><div><dt>{paths.length > 1 ? `Path ${index + 1} · ` : ""}Deviation score</dt>
      <dd><strong>{validScore ? `${score}/100` : "Not evaluated"}</strong></dd></div>
      <div><dt>Judge-reported confidence</dt><dd>{validConfidence ? `${Math.round(confidence * 100)}%` : "Not recorded"}</dd></div>
    </div>;
  })}</dl>;
}
