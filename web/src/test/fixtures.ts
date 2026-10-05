// ABOUTME: The UI fixtures under tests/fixtures/ui, typed against the generated API types.
// ABOUTME: A fixture that does not fit a response shape fails the type check; nothing is copied into web/.
import type { components } from '@/api/types'
import leadsJson from '../../../tests/fixtures/ui/leads.json'
import runJson from '../../../tests/fixtures/ui/run.json'
import lead000Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-000.json'
import lead001Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-001.json'
import lead002Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-002.json'
import lead003Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-003.json'
import lead004Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-004.json'
import lead005Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-005.json'
import lead006Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-006.json'
import lead007Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-007.json'
import lead008Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-008.json'
import lead009Json from '../../../tests/fixtures/ui/lead/LEAD-00000042-009.json'

type Schemas = components['schemas']
export type RunView = Schemas['RunView']
export type QueueRow = Schemas['QueueRow']
export type LeadDetail = Schemas['LeadDetail']

// JSON imports widen string-literal unions to `string`; the type a fixture must fit is its
// response type with those unions widened, so a missing or mistyped field still fails.
type Widen<T> = T extends string
  ? string
  : T extends (infer Item)[]
    ? Widen<Item>[]
    : T extends object
      ? { [Key in keyof T]: Widen<T[Key]> }
      : T

function fit<T>(json: Widen<T>): T {
  return json as T
}

export const run = fit<RunView>(runJson)
export const rows = fit<QueueRow[]>(leadsJson)

// The lead details, keyed by lead id, read from the same files the stand-in API serves.
export const details: Record<string, LeadDetail> = Object.fromEntries(
  [
    fit<LeadDetail>(lead000Json),
    fit<LeadDetail>(lead001Json),
    fit<LeadDetail>(lead002Json),
    fit<LeadDetail>(lead003Json),
    fit<LeadDetail>(lead004Json),
    fit<LeadDetail>(lead005Json),
    fit<LeadDetail>(lead006Json),
    fit<LeadDetail>(lead007Json),
    fit<LeadDetail>(lead008Json),
    fit<LeadDetail>(lead009Json),
  ].map((lead) => [lead.lead_id, lead]),
)

export function detail(leadId: string): LeadDetail {
  const found = details[leadId]
  if (!found) throw new Error(`no fixture for ${leadId}`)
  return found
}
