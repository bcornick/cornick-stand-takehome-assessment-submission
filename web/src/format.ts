// ABOUTME: Formats what the API returns for display: a value of any shape, a timestamp or date in the reader's local time, a lead's short name, a field's registry label in place of its key, and the queue greeting.
// ABOUTME: Values arrive as JSON of any shape, so the formatter takes unknown.
import type { components } from '@/api/types'

export const MISSING = '—'

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return MISSING
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
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

// The run's seven counts as one sentence.
export function summarySentence(summary: components['schemas']['RunSummary']): string {
  return (
    `${summary.quotes_sent} quotes sent, ${summary.follow_ups_sent} follow-ups sent, ` +
    `${summary.declines_approved} declines approved, ` +
    `${summary.waiting_on_underwriter} waiting on the underwriter, ` +
    `${summary.waiting_on_producer} waiting on the producer, ` +
    `${summary.waiting_on_data} waiting on data, ${summary.delivery_unknown} delivery unknown.`
  )
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
