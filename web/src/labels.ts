// ABOUTME: Human-readable labels for the API's vocabularies: statuses, blocker kinds, owners, sources, groups, pages and more.
// ABOUTME: One mapping module, so no screen carries its own string literals for these.
import type { components } from '@/api/types'

type Schemas = components['schemas']
type Status = Schemas['QueueRow']['status']
type BlockerKind = Schemas['BlockerView']['kind']
type Owner = Schemas['BlockerView']['owner']
type Source = Schemas['FactView']['source']
type Group = Schemas['QueueRow']['group']
type Result = NonNullable<Schemas['PlaybookPage']['result']>
type Applies = Schemas['PlaybookPage']['applies']
type MessageKind = Schemas['DraftView']['kind']
type DraftState = Schemas['DraftView']['state']
type EffectType = Schemas['PlannedEffect']['effect']['type']
type Mode = Schemas['RunView']['mode']

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

export const RESULT_LABELS: Record<Result, string> = {
  decided: 'Decided',
  undecided: 'Undecided',
  declines_on_every_branch: 'Declines on every branch',
  not_evaluated: 'Not evaluated',
}

export const APPLIES_LABELS: Record<Applies, string> = {
  yes: 'Applies',
  no: 'Does not apply',
  unknown: 'Applicability unknown',
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

export const MODE_LABELS: Record<Mode, string> = {
  live: 'live',
  record: 'record',
  replay: 'replay',
}

const PAGE_LABELS: Record<string, string> = {
  electrical: 'Electrical',
  fire_simulation: 'Fire simulation',
  occupancy: 'Occupancy',
  pc_9_and_10: 'PC 9 & 10',
  plumbing: 'Plumbing',
  pools: 'Pools',
  post_and_pier: 'Post & Pier',
  profile: 'Profile',
  replacement_cost: 'Replacement cost',
  roof: 'Roof',
  siding: 'Siding',
  trusts: 'Trusts',
}

// A playbook page's graph id as a label; an id with no entry reads as its words.
export function pageLabel(graph: string): string {
  return PAGE_LABELS[graph] ?? graph.replace(/_/g, ' ')
}
