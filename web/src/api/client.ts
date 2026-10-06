// ABOUTME: Typed fetch calls: the run, the queue, one lead's detail and events, the open items and the proposal cards, and the actions of the page: start the run, deliver the fixture replies, the underwriter's commands, a pasted reply, a chat message, apply or dismiss a card.
// ABOUTME: A response that is not 2xx throws an ApiError that carries the server's `detail` when it has one, and otherwise names the route and the status; a command resolves to the reason it was refused, or null when it was accepted.
import type { components, paths } from '@/api/types'

type Schemas = components['schemas']
type Command = paths['/api/commands']['post']['requestBody']['content']['application/json']

class ApiError extends Error {
  readonly path: string
  readonly status: number

  constructor(path: string, status: number, detail: string | null) {
    super(detail ?? `${path} answered ${status}`)
    this.name = 'ApiError'
    this.path = path
    this.status = status
  }
}

// The reason the server gives for a failure, when it gives one as text.
async function detailOf(response: Response): Promise<string | null> {
  try {
    const body: unknown = await response.json()
    const detail = (body as { detail?: unknown }).detail
    return typeof detail === 'string' ? detail : null
  } catch {
    return null
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw new ApiError(path, response.status, await detailOf(response))
  return (await response.json()) as T
}

const post = <T>(path: string, body?: unknown) =>
  request<T>(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  })

export const getRun = () => request<Schemas['RunView']>('/api/run')
export const getLeads = () => request<Schemas['QueueRow'][]>('/api/leads')
export const getLead = (leadId: string) =>
  request<Schemas['LeadDetail']>(`/api/leads/${encodeURIComponent(leadId)}`)
export const getLeadEvents = (leadId: string) =>
  request<Schemas['LeadEvents']>(`/api/leads/${encodeURIComponent(leadId)}/events`)
export const getItems = () => request<Schemas['Item'][]>('/api/items')

export const startRun = () => post<Schemas['RunView']>('/api/run/start?wait=true')
export const deliverFixtureReplies = () =>
  post<Schemas['FixtureRepliesResponse']>('/api/replies/fixtures')

const refusal = (answer: Schemas['CommandResponse']) =>
  answer.accepted ? null : (answer.reason ?? 'The command was refused.')

const command = async (body: Command) =>
  refusal(await post<Schemas['CommandResponse']>('/api/commands', body))

// A draft is approved against the hash shown with it; any other item has none.
export const approve = (itemId: number, reason: string, payloadHash: string | null = null) =>
  command({
    type: 'approve',
    payload: { item_id: itemId, artifact_hash: payloadHash, reason },
  })
export const reject = (itemId: number, reason: string) =>
  command({ type: 'reject', payload: { item_id: itemId, reason } })
export const editDraft = (intentId: string, subject: string, body: string, reason: string) =>
  command({
    type: 'edit_draft',
    payload: { intent_id: intentId, subject, body, reason },
  })
export const recordRuling = (leadId: string, choiceId: string, option: string, reason: string) =>
  command({
    type: 'record_ruling',
    payload: { lead_id: leadId, choice_id: choiceId, option, reason },
  })
export const resolveFact = (
  leadId: string,
  key: string,
  value: string | number | boolean,
  reason: string,
) => command({ type: 'resolve_fact', payload: { lead_id: leadId, key, value, reason } })
export const declineLead = (leadId: string, reason: string) =>
  command({ type: 'decline_lead', payload: { lead_id: leadId, reason } })

export const deliverReply = async (leadId: string, intentId: string, body: string) =>
  refusal(
    await post<Schemas['ReplyResponse']>('/api/replies', {
      lead_id: leadId,
      intent_id: intentId,
      body,
    }),
  )

export type ChatEvent =
  | Schemas['StepEvent']
  | Schemas['AnswerEvent']
  | Schemas['ProposalEvent']
  | Schemas['ErrorEvent']

// The `data:` payload of one server-sent event, or null for a block of comment lines only.
function eventOf(block: string): ChatEvent | null {
  const data = block
    .split('\n')
    .filter((line) => line.startsWith('data:'))
    .map((line) => line.slice('data:'.length).trimStart())
    .join('\n')
  return data === '' ? null : (JSON.parse(data) as ChatEvent)
}

// Posts one chat turn and hands each event of the answering stream to `onEvent` as it arrives.
export async function streamChat(
  chatRequest: Schemas['ChatRequest'],
  onEvent: (event: ChatEvent) => void,
): Promise<void> {
  const path = '/api/chat'
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(chatRequest),
  })
  if (!response.ok) throw new ApiError(path, response.status, await detailOf(response))
  if (response.body === null) throw new ApiError(path, response.status, 'The answer had no body.')
  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''
  for (;;) {
    const { done, value } = await reader.read()
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, '\n')
    const blocks = buffer.split('\n\n')
    buffer = done ? '' : (blocks.pop() ?? '')
    for (const block of blocks) {
      const event = eventOf(block)
      if (event !== null) onEvent(event)
    }
    if (done) return
  }
}
export const getProposals = () => request<Schemas['ProposalView'][]>('/api/proposals')
export const applyProposal = (proposalId: number) =>
  post<Schemas['CommandResponse']>(`/api/proposals/${proposalId}/apply`)
export const dismissProposal = (proposalId: number) =>
  post<null>(`/api/proposals/${proposalId}/dismiss`)
