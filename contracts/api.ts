export type SchemaVersion = "event-v0.3";

export type SourceKind =
  | "elder"
  | "family_observation"
  | "family_report"
  | "caregiver"
  | "clinician_evidence"
  | "document"
  | "audio_transcript"
  | "system"
  | "unknown";

export type EventKind =
  | "symptom"
  | "measurement"
  | "medication"
  | "instruction"
  | "document"
  | "question"
  | "handoff"
  | "other";

export type EventState =
  | "inbox"
  | "draft"
  | "needs_review"
  | "recorded"
  | "superseded";

export type TimeCertainty =
  | "exact"
  | "range"
  | "daypart"
  | "relative"
  | "unknown";

export type ReviewRole =
  | "none"
  | "family"
  | "clinician_or_pharmacist"
  | "emergency_services";

export type EscalationLevel = "none" | "urgent" | "emergency";

export type ForbiddenAction =
  | "diagnosis"
  | "medication_change"
  | "source_overwrite"
  | "invented_time_or_dose";

export type AiDraftTime = {
  occurred: string | null;
  recorded: string;
  certainty: TimeCertainty;
};

export type AiDraftClaim = {
  text: string;
  source_kind: SourceKind;
  record_id: string;
  quote: string | null;
};

export type AiDraftConflict = {
  present: boolean;
  record_refs: string[];
};

/** AI output validated against config/event-v0.3.schema.json. */
export type AiDraft = {
  schema_version: SchemaVersion;
  event_kind: EventKind;
  summary: string;
  time: AiDraftTime;
  claims: [AiDraftClaim, ...AiDraftClaim[]];
  review_required: true;
  review_role: ReviewRole;
  escalation_level: EscalationLevel;
  conflict: AiDraftConflict;
  provenance_preserved: true;
  plan_change_allowed: false;
  follow_up_questions?: string[];
  forbidden_actions?: ForbiddenAction[];
};

/** Offline safety scan stored outside the AI draft. A non-match is not medical clearance. */
export type LocalSafety =
  | {
      danger_detected: false;
      escalation_level: "none";
      review_role: "none";
      danger_reminder: null;
      matched_rules: [];
      safety_rule_version: string;
    }
  | {
      danger_detected: true;
      escalation_level: "emergency";
      review_role: "emergency_services";
      danger_reminder: string;
      matched_rules: [string, ...string[]];
      safety_rule_version: string;
    };

export type OrganizeResultMeta = {
  trace_id: string;
  provider: string;
  prompt_version: string;
  schema_version: SchemaVersion;
  latency_ms: number;
  safety_guard_applied: boolean;
};

/** The complete event object returned by the core HTTP routes. */
export type Event = {
  record_id: string;
  raw_text: string;
  source_kind: SourceKind;
  actor_name: string;
  occurred_time: string | null;
  recorded_at: string;
  state: EventState;
  version: number;
  draft: AiDraft | null;
  result_meta: OrganizeResultMeta | null;
  review_notes: string | null;
  related_record_ids: string[];
  supersedes_id: string | null;
  created_at: string;
  updated_at: string;
  household_id: string;
  local_safety: LocalSafety;
  confirmation_scope: "record_accuracy" | null;
};

export type SaveEventRequest = {
  raw_text: string;
  source_kind: SourceKind;
  actor_name: string;
  occurred_time?: string | null;
  related_record_ids?: string[];
};

export type OrganizeEventRequest = {
  expected_version: number;
  actor_name?: string;
};

export type ReviewEventRequest =
  | {
      expected_version: number;
      action: "confirm";
      note?: string | null;
      actor_name?: string;
    }
  | {
      expected_version: number;
      action: "return";
      note: string;
      actor_name?: string;
    };

export type ReviseEventRequest = {
  expected_version: number;
  raw_text: string;
  source_kind: SourceKind;
  actor_name: string;
  reason: string;
  occurred_time?: string | null;
  related_record_ids?: string[];
};

export type CreateHandoffRequest = Record<string, never>;

export type HealthResponse = {
  ok: true;
  service: "medical-handoff-p0";
  provider: string;
  storage: "sqlite";
  mode: "local_single_household";
  schema_version: SchemaVersion;
  session_token: string;
};

export type SaveResponse = {
  ok: true;
  created: boolean;
  event: Event;
};

export type EventListResponse = {
  ok: true;
  events: Event[];
};

export type EventDetailResponse = {
  ok: true;
  event: Event;
};

export type OrganizeSuccess = LocalSafety & {
  ok: true;
  ai_failed: false;
  event: Event;
  output: AiDraft;
  trace_id: string;
  provider: string;
  prompt_version: string;
  schema_version: SchemaVersion;
  latency_ms: number;
  safety_guard_applied: boolean;
  raw_text_preserved: true;
  local_safety: LocalSafety;
};

/** A 422 still contains the saved event and safety notice; clients must parse it. */
export type OrganizeFailure = LocalSafety & {
  ok: false;
  ai_failed: true;
  error: "ai_organize_failed";
  record_id: string;
  event: Event;
  raw_text_preserved: true;
  failure_type: string;
  failure_cause_type: string;
  failure_reason: string;
  trace_id: string;
  raw_text_sha256: string;
  prompt_version: string;
  schema_version: SchemaVersion;
  local_safety: LocalSafety;
};

export type OrganizeResponse = OrganizeSuccess | OrganizeFailure;

export type ReviewResponse = {
  ok: true;
  event: Event;
};

export type ReviseResponse = {
  ok: true;
  event: Event;
};

export type RevisionAction =
  | "created"
  | "organized"
  | "review_confirm"
  | "review_return"
  | "superseded_by_revision"
  | "revised_from";

export type AuditAction = RevisionAction | "organize_failed";

export type EventSnapshot = Pick<
  Event,
  | "record_id"
  | "raw_text"
  | "source_kind"
  | "actor_name"
  | "occurred_time"
  | "recorded_at"
  | "state"
  | "version"
  | "draft"
  | "result_meta"
  | "review_notes"
  | "local_safety"
  | "related_record_ids"
  | "supersedes_id"
  | "confirmation_scope"
>;

export type EventRevision = {
  revision_id: string;
  record_id: string;
  action: RevisionAction;
  version: number;
  snapshot: EventSnapshot;
  actor_name: string;
  at: string;
};

export type JsonPrimitive = string | number | boolean | null;
export type JsonValue = JsonPrimitive | JsonObject | JsonValue[];
export type JsonObject = { [key: string]: JsonValue };

export type AuditEntry = {
  audit_id: string;
  record_id: string;
  action: AuditAction;
  version: number;
  actor_name: string;
  at: string;
  details: JsonObject;
};

export type EventHistoryResponse = {
  ok: true;
  history: EventRevision[];
  audit: AuditEntry[];
};

export type UnresolvedReason =
  | "local_danger_detected"
  | "record_not_confirmed"
  | "draft_missing"
  | "professional_review_required"
  | "escalation_not_cleared"
  | "conflict_not_resolved";

export type HandoffItem = Event & {
  unresolved: boolean;
  unresolved_reasons: UnresolvedReason[];
};

export type Handoff = {
  handoff_id: string;
  created_at: string;
  household_id: string | null;
  items: HandoffItem[];
  unresolved_count: number;
};

export type HandoffResponse = {
  ok: true;
  handoff: Handoff;
};

export type CreateHandoffResponse = HandoffResponse;
export type HandoffDetailResponse = HandoffResponse;

/**
 * Stable error codes returned by the core elder-facing HTTP routes.
 *
 * Keep this list aligned with docs/API.md and backend/server.py. Account
 * compatibility routes are intentionally outside this MVP contract.
 */
export const CORE_HTTP_ERROR_CODES = [
  "body_too_large",
  "body_must_object",
  "raw_text_required",
  "raw_text_too_long",
  "source_kind_required",
  "source_kind_too_long",
  "invalid_source_kind",
  "actor_name_required",
  "actor_name_too_long",
  "occurred_time_required",
  "occurred_time_too_long",
  "recorded_at_read_only",
  "related_record_ids_must_bounded_list",
  "invalid_related_record_id",
  "duplicate_related_record_id",
  "related_record_not_found",
  "idempotency_key_required",
  "idempotency_key_too_long",
  "idempotency_key_payload_mismatch",
  "invalid_json_payload",
  "expected_version_must_positive_integer",
  "stale_version",
  "event_not_found",
  "handoff_not_found",
  "handoff_body_must_be_empty_object",
  "invalid_review_action",
  "note_required",
  "note_too_long",
  "return_note_required",
  "confirm_state_invalid",
  "draft_required",
  "return_state_invalid",
  "revision_reason_required",
  "revision_reason_too_long",
  "already_superseded",
  "organize_state_invalid",
  "validated_output_required",
  "cross_household_reference_denied",
  "invalid_session",
  "csrf_or_origin_rejected",
  "ai_organize_failed",
  "not_found",
  "internal_server_error",
] as const;

export type CoreHttpErrorCode = (typeof CORE_HTTP_ERROR_CODES)[number];

/** Known core errors remain exhaustively switchable by their `error` field. */
export type CommonErrorResponse<
  ErrorCode extends CoreHttpErrorCode = CoreHttpErrorCode,
> = {
  ok: false;
  error: ErrorCode;
};

/** Raw forward-compatible shape at the JSON boundary. */
export type RawCommonErrorResponse = {
  ok: false;
  error: string;
};

/**
 * A client-side classification for handling newer server errors safely without
 * widening CommonErrorResponse.error back to `string`.
 */
export type ClassifiedCommonErrorResponse =
  | {
      known_error: true;
      response: CommonErrorResponse;
    }
  | {
      known_error: false;
      response: RawCommonErrorResponse;
    };

const coreHttpErrorCodeSet: ReadonlySet<string> = new Set(
  CORE_HTTP_ERROR_CODES,
);

export function isCoreHttpErrorCode(
  error: string,
): error is CoreHttpErrorCode {
  return coreHttpErrorCodeSet.has(error);
}

export function classifyCommonErrorResponse(
  response: RawCommonErrorResponse,
): ClassifiedCommonErrorResponse {
  if (isCoreHttpErrorCode(response.error)) {
    const error = response.error;
    return {
      known_error: true,
      response: { ok: false, error },
    };
  }
  return { known_error: false, response };
}
