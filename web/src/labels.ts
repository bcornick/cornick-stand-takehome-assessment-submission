// ABOUTME: Human-readable labels for the API's value sets: statuses, blocker kinds, missing-field resolutions, owners, sources, groups, message kinds, effects, event types and actors.
// ABOUTME: One mapping module, so no screen carries its own string literals for these.
import type { components } from '@/api/types'

type Schemas = components['schemas']
type Status = Schemas['QueueRow']['status']
type BlockerKind = Schemas['BlockerView']['kind']
type Owner = Schemas['BlockerView']['owner']
type Source = Schemas['FactView']['source']
type Group = Schemas['QueueRow']['group']
type MessageKind = Schemas['DraftView']['kind']
type DraftState = Schemas['DraftView']['state']
type EffectType = Schemas['PlannedEffect']['effect']['type']
type EventType = Schemas['EventRow']['type']
type Actor = Schemas['EventRow']['actor']
type Resolution = Schemas['MissingField']['resolution']

export const STATUS_LABELS: Record<Status, string> = {
  received: 'Received',
  triaged: 'Triaged',
  in_progress: 'In progress',
  quote_sent: 'Quote sent',
  declined: 'Declined',
}

export const BLOCKER_KIND_LABELS: Record<BlockerKind, string> = {
  delivery_unknown: 'Delivery unknown',
  underwriter_question: 'Underwriter question',
  underwriter_review: 'Underwriter review',
  data: 'Data',
  producer_reply: 'Producer reply',
}

// The heading a missing field is listed under in the full lead view, by how the triage resolves it.
export const MISSING_LABELS: Record<Resolution, string> = {
  ask: 'Asked of the producer',
  ask_follow_on: 'Asked of the producer',
  fetch: 'Looked up by the system',
  derive: 'Looked up by the system',
  blocked: 'Waiting on other fields',
  assume: 'Assumed',
  verify: 'To verify',
  none: 'Not yet resolved',
  not_required: 'Not required',
  defer: 'Deferred',
}

export const OWNER_LABELS: Record<Owner, string> = {
  underwriter: 'Underwriter',
  producer: 'Producer',
  data_team: 'Data team',
}

export const SOURCE_LABELS: Record<Source, string> = {
  submitted: 'Submitted',
  fetched: 'Fetched',
  derived: 'Derived',
  assumed: 'Assumed',
  reply: 'Reply',
  underwriter: 'Underwriter',
}

// The queue groups in the order section 11 lists them.
export const GROUP_ORDER: Group[] = [
  'blocked_on_underwriter',
  'waiting_on_data_or_producer',
  'finished',
]

export const GROUP_LABELS: Record<Group, string> = {
  blocked_on_underwriter: 'Waiting on the underwriter',
  waiting_on_data_or_producer: 'Waiting on the producer or data',
  finished: 'Finished',
}

export const MESSAGE_KIND_LABELS: Record<MessageKind, string> = {
  routine_request: 'Routine request',
  sensitive_request: 'Sensitive request',
  quote_packet: 'Quote packet',
  decline_notice: 'Decline notice',
}

export const DRAFT_STATE_LABELS: Record<DraftState, string> = {
  draft: 'Draft',
  dispatching: 'Dispatching',
  sent: 'Sent',
  unknown: 'Delivery unknown',
  closed_unsent: 'Closed unsent',
}

export const EFFECT_LABELS: Record<EffectType, string> = {
  decline: 'Decline',
  requirement: 'Requirement',
  surcharge: 'Surcharge',
  exclusion_or_endorsement: 'Exclusion or endorsement',
  coverage_adjustment: 'Coverage adjustment',
  advisory: 'Advisory',
  obligation: 'Obligation',
  no_action: 'No action',
}

export const EVENT_LABELS: Record<EventType, string> = {
  run_started: 'Run started',
  replay_miss: 'Recording missing',
  draft_edited: 'Draft edited',
  proposal_created: 'Proposal made',
  lead_received: 'Lead received',
  fact_observed: 'Fact observed',
  fact_selected: 'Fact chosen',
  conflict_opened: 'Conflict opened',
  conflict_closed: 'Conflict closed',
  triage_completed: 'Triage done',
  provider_called: 'Data looked up',
  plan_built: 'Plan built',
  blocker_opened: 'Wait opened',
  blocker_closed: 'Wait closed',
  intent_created: 'Message drafted',
  message_sent: 'Message sent',
  delivery_unknown: 'Delivery unknown',
  reply_received: 'Reply received',
  reply_read: 'Reply read',
  approval_recorded: 'Decision recorded',
  ruling_recorded: 'Ruling recorded',
  command_refused: 'Command refused',
  skill_fallback_used: 'Fallback used',
  model_called: 'Model called',
  fault_injected: 'Fault injected',
}

export const ACTOR_LABELS: Record<Actor, string> = {
  workflow: 'The system',
  underwriter: 'The underwriter',
  assistant: 'The assistant',
  inbound: 'The producer',
}
