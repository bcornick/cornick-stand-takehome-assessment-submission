// ABOUTME: Typed fetch calls for the read routes: the run, the queue and one lead's detail.
// ABOUTME: A response that is not 2xx throws an ApiError that names the route and the status.
import type { components } from '@/api/types'

type Schemas = components['schemas']

export class ApiError extends Error {
  readonly path: string
  readonly status: number

  constructor(path: string, status: number) {
    super(`${path} answered ${status}`)
    this.name = 'ApiError'
    this.path = path
    this.status = status
  }
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (!response.ok) throw new ApiError(path, response.status)
  return (await response.json()) as T
}

export const getRun = () => getJson<Schemas['RunView']>('/api/run')
export const getLeads = () => getJson<Schemas['QueueRow'][]>('/api/leads')
export const getLead = (leadId: string) =>
  getJson<Schemas['LeadDetail']>(`/api/leads/${encodeURIComponent(leadId)}`)
