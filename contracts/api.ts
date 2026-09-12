export type LocalSafety = {
  danger_detected: boolean;
  escalation_level: 'none' | 'emergency';
  review_role: 'none' | 'emergency_services';
  danger_reminder: string | null;
  matched_rules: string[];
  safety_rule_version: string;
  previous_rule_version?: string;
  previous_danger_detected?: boolean;
  previous_matched_rules?: string[];
  historical_notice_preserved?: boolean;
  clinical_review_flags?: string[];
  clinical_review_required?: boolean;
  clinical_review_role?: 'clinician_or_pharmacist' | null;
  clinical_review_notice?: string | null;
  clinical_review_version?: string;
  clinical_review_status?: 'candidate_unverified' | 'not_flagged';
  previous_clinical_review_version?: string | null;
  previous_clinical_review_flags?: string[];
  historical_clinical_review_preserved?: boolean;
};

export type EventState = 'inbox' | 'draft' | 'needs_review' | 'recorded' | 'superseded';

export type ModelTrace = {
  trace_id: string;
  provider: string | null;
  model_id?: string | null;
  prompt_version: string;
  prompt_sha256?: string;
  input_sha256?: string;
  schema_version: string;
  latency_ms?: number;
  safety_guard_applied?: boolean;
};

export type Event = {
  record_id: string;
  raw_text: string;
  source_kind: string;
  actor_name: string;
  recorded_at: string;
  occurred_time: string | null;
  state: EventState;
  version: number;
  draft: Record<string, unknown> | null;
  result_meta?: ModelTrace | null;
  local_safety: LocalSafety;
  related_record_ids: string[];
  supersedes_id: string | null;
};

export type SaveResponse = { ok: true; created: boolean; event: Event };
export type OrganizeFailure = {
  ok: false;
  ai_failed: true;
  record_id: string;
  event: Event;
  raw_text_preserved: true;
  failure_reason: string;
  failure_code?: string;
  provider_http_status?: number;
  local_safety: LocalSafety;
  danger_detected: boolean;
  escalation_level: 'none' | 'emergency';
  review_role: 'none' | 'emergency_services';
  danger_reminder: string | null;
};
