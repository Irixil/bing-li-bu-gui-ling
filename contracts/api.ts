export type LocalSafety = {
  danger_detected: boolean;
  escalation_level: 'none' | 'emergency';
  review_role: 'none' | 'emergency_services';
  danger_reminder: string | null;
  matched_rules: string[];
  safety_rule_version: string;
};

export type EventState = 'inbox' | 'draft' | 'needs_review' | 'recorded' | 'superseded';

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
  local_safety: LocalSafety;
  danger_detected: boolean;
  escalation_level: 'none' | 'emergency';
  review_role: 'none' | 'emergency_services';
  danger_reminder: string | null;
};
