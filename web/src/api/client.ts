// ABOUTME: Typed fetch calls: the run, the queue and one lead's detail, the three actions of the page (start the run, deliver the fixture replies, approve an item) and the chat panel's: a message, the open proposal cards, apply and dismiss.
// ABOUTME: A response that is not 2xx throws an ApiError that names the route and the status.
import type { components } from '@/api/types'

type Schemas = components['schemas']

class ApiError extends Error {
  readonly path: string
  readonly status: number

  constructor(path: string, status: number) {
    super(`${path} answered ${status}`)
    this.name = 'ApiError'
    this.path = path
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  if (!response.ok) throw new ApiError(path, response.status)
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

export const startRun = () => post<Schemas['RunView']>('/api/run/start?wait=true')
export const deliverFixtureReplies = () =>
  post<Schemas['FixtureRepliesResponse']>('/api/replies/fixtures')
export const approve = (itemId: number, payloadHash: string) =>
  post<Schemas['CommandResponse']>('/api/commands', {
    type: 'approve',
    payload: { item_id: itemId, artifact_hash: payloadHash, reason: 'Approved in the detail pane.' },
  })

export const sendChat = (message: string, leadId: string | null) =>
  post<Schemas['ChatResponse']>('/api/chat', { message, lead_id: leadId })
export const getProposals = () => request<Schemas['ProposalView'][]>('/api/proposals')
export const applyProposal = (proposalId: number) =>
  post<Schemas['CommandResponse']>(`/api/proposals/${proposalId}/apply`)
export const dismissProposal = (proposalId: number) =>
  post<Schemas['ProposalView']>(`/api/proposals/${proposalId}/dismiss`)
