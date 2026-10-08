// ABOUTME: Formats what the API returns for display: a value of any shape, a timestamp or date in the reader's local time, a lead's short name and id, a field's registry label in place of its key, and the queue greeting.
// ABOUTME: Values arrive as JSON of any shape, so the formatter takes unknown.
import type { components } from '@/api/types'

// A value in plain words: a flag as Yes or No, a missing value as "Not provided".
export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return 'Not provided'
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  return JSON.stringify(value)
}

// An ISO timestamp as the reader's local date and time, for example "Jun 29, 2026, 8:00 AM".
export function formatTime(iso: string): string {
  return new Date(iso).toLocaleString('en-US', { dateStyle: 'medium', timeStyle: 'short' })
}

// A lead as an underwriter says it: "Lead 008" for LEAD-00000042-008.
export function leadName(leadId: string): string {
  return `Lead ${leadId.slice(leadId.lastIndexOf('-') + 1)}`
}

// A lead id as shown to the underwriter: LEAD-003 for LEAD-00000042-003, without the run's seed.
export function shortLeadId(leadId: string): string {
  return leadId.replace(/^LEAD-\d+-/, 'LEAD-')
}

// Whether the lead has an address: a lead with none is labelled by its short id.
export function hasAddress(leadId: string, label: string): boolean {
  return label !== shortLeadId(leadId)
}

// A lead as a title: "Lead 003 · 9273 Hillside Ct", or "Lead 000" for a lead with no address.
export function leadTitle(leadId: string, label: string): string {
  return hasAddress(leadId, label) ? `${leadName(leadId)} · ${label}` : leadName(leadId)
}

// An ISO date or timestamp as a short date, for example "Jul 21".
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: 'UTC' })
}

type Field = components['schemas']['FactField']

// The registry's label for a field key, or the key itself for one the registry does not list.
export function fieldLabel(fields: Field[], key: string): string {
  return fields.find((field) => field.key === key)?.label ?? key
}

// A field's value as its registry kind reads best: a date field's ISO date as "Jul 15, 2008", any other value as formatValue.
export function formatFieldValue(fields: Field[], key: string, value: unknown): string {
  const kind = fields.find((field) => field.key === key)?.kind
  if (kind === 'date' && typeof value === 'string' && /^\d{4}-\d{2}-\d{2}/.test(value)) {
    return new Date(value).toLocaleDateString('en-US', { dateStyle: 'medium', timeZone: 'UTC' })
  }
  return formatValue(value)
}

// A sentence with every field key it names replaced by the field's registry label; longer keys go first so a key does not match inside another.
export function labelKeys(text: string, fields: Field[]): string {
  return [...fields]
    .sort((a, b) => b.key.length - a.key.length)
    .reduce((result, field) => result.replace(new RegExp(`\\b${field.key}\\b`, 'g'), field.label), text)
}

// The queue conversation's greeting: who needs the underwriter, who waits on producers, and what is finished.
export function greeting(summary: components['schemas']['RunSummary']): string {
  const needing = summary.waiting_on_underwriter
  const sentences = [
    `${needing} ${needing === 1 ? 'lead needs' : 'leads need'} you.`,
    `${summary.waiting_on_producer} ${summary.waiting_on_producer === 1 ? 'is' : 'are'} waiting on producers.`,
  ]
  if (summary.quotes_sent > 0) sentences.push(`${summary.quotes_sent} ${summary.quotes_sent === 1 ? 'quote' : 'quotes'} sent.`)
  if (summary.declines_approved > 0) sentences.push(`${summary.declines_approved} declined.`)
  return sentences.join(' ')
}
