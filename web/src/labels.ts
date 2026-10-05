// ABOUTME: Human-readable labels for the API's value sets: statuses, blocker kinds, owners, sources, groups, message kinds and effects.
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
  blocked_on_underwriter: 'Blocked on the underwriter',
  waiting_on_data_or_producer: 'Waiting on data or producer',
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
