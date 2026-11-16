import type { ChatMatePromptCandidate } from "./chatmateService";

export function BaselineMethodReview({ candidate }: { candidate: ChatMatePromptCandidate | null | undefined }) {
  if (candidate?.generation_mode !== "BASELINE_METHOD_REVIEWED" || !candidate.method_review) return null;
  const label = { ALIGNED: "Aligned", NOT_ALIGNED: "Not aligned", UNCERTAIN: "Uncertain" }[candidate.method_review.verdict];
  return <div className="chatmate-helper baseline-method-review">
    <span><strong>Selected method:</strong> {candidate.attack_method}</span>
    <span><strong>Method match:</strong> {label}</span>
  </div>;
}
