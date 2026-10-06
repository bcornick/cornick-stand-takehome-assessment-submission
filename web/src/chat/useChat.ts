// ABOUTME: The chat tails of the run, held in the browser's memory by conversation and lost on reload by design; a new run clears them.
// ABOUTME: Sending a message streams its turn into the tail of the conversation it was typed in.
import type { Chat } from '@/surface'

export function useChat(_runId: string | null, _onProposal: () => void): Chat {
  return { turnsOf: () => [], running: false, send: () => {} }
}
