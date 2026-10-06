// ABOUTME: One planned effect as a line of text: its type and rule id, then what it asks for.
// ABOUTME: Shared by the plan in the full lead view and the playbook page view of the drill-down panel.
import type { components } from '@/api/types'
import { EFFECT_LABELS } from '@/labels'

type Effect = components['schemas']['PlannedEffect']['effect']

export function effectLine(effect: Effect): string {
  const label = `${EFFECT_LABELS[effect.type]} (${effect.rule})`
  switch (effect.type) {
    case 'surcharge':
      return `${label}: ${effect.percent}%`
    case 'coverage_adjustment':
      return `${label}: ${effect.field} to ${effect.proposed_value}`
    case 'decline':
    case 'no_action':
      return label
    default:
      return `${label}: ${effect.text}`
  }
}
