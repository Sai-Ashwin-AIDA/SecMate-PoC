import captured from "./fixtures/chatmateOfflineContract.json";
import type { ChatMateCriticReview, ChatMateRunRecord } from "./chatmateService";
import type { DeepTeamAuditReport } from "./modelConnectivityService";

// Captured from the offline worker + API on 2026-10-12, with mocked HTTP.
// Only unrelated audit metadata and repeated objects are omitted in the JSON.
// These shared objects reconstruct the exact captured assessment/evidence values.
export function offlineChatMateContractFixture() {
  const data = structuredClone(captured);
  const record = data.record as ChatMateRunRecord;
  const audit: DeepTeamAuditReport = {
    ...data.audit,
    manifest: { ...data.audit.manifest, assessment_spec: record.candidate_batch!.assessment_spec },
    evidence: { ...data.audit.evidence, paths: data.audit.evidence.paths.map((path) => ({ ...path,
      turns: path.turns.map((turn) => ({ ...turn, manual_collection: [record.manual_evidence] })),
    })) },
  };
  const follow_up_draft = { ...data.follow_up_draft, assessment_spec_snapshot: record.candidate_batch!.assessment_spec } as ChatMateRunRecord;
  return { ...data, record, audit, follow_up_draft, review: data.review as ChatMateCriticReview };
}
