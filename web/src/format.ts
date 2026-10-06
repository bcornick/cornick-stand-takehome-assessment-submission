// ABOUTME: Formats what the API returns for display: a value of any shape, a timestamp in the reader's local time, a lead's short name and the run summary sentence.
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
