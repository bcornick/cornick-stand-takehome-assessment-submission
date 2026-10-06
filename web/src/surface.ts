// ABOUTME: The shared vocabulary of the underwriter surface: which conversation is open, what the drill-down panel shows, and one chat turn of a conversation's tail.
// ABOUTME: The shell holds these in state; the conversation, the chat tail and the panel exchange them through their props.
import type { components } from '@/api/types'

type Schemas = components['schemas']

// The key of the queue-level conversation; every other conversation is keyed by its lead id.
export const QUEUE = 'queue'

// What the drill-down panel shows: the thing a citation stands for, or a lead's full detail.
export type PanelTarget =
  | Pick<Schemas['Citation'], 'kind' | 'lead_id' | 'id'>
  | { kind: 'lead'; lead_id: string }

// How a chat turn closed. A card's rationale is kept with it, since it is the turn's reply text.
export type Closing =
  | Schemas['AnswerEvent']
  | Schemas['ErrorEvent']
  | (Schemas['ProposalEvent'] & { rationale: string })

// One typed message of a conversation and what came back; `closing` is null while the turn runs.
export type Turn = { message: string; steps: string[]; closing: Closing | null }

// The chat tails of the run in the browser's memory, by conversation, and the one way to add to them.
export type Chat = {
  turnsOf: (conversation: string) => Turn[]
  running: boolean
  send: (conversation: string, message: string) => void
}
