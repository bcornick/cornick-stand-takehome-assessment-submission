// ABOUTME: Formats an API value for display: a missing value, booleans, numbers and text, and a timestamp in the reader's local time.
// ABOUTME: Values arrive as JSON of any shape, so the formatter takes unknown.
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
