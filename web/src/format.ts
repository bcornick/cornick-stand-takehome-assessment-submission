// ABOUTME: Formats an API value for display: a missing value, booleans, numbers and text.
// ABOUTME: Values arrive as JSON of any shape, so the formatter takes unknown.
export const MISSING = '—'

export function formatValue(value: unknown): string {
  if (value === null || value === undefined) return MISSING
  if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
    return String(value)
  }
  return JSON.stringify(value)
}
