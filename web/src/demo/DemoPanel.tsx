// ABOUTME: The demo controls, apart from the product: load the day's leads and deliver the producers' fixture replies.
// ABOUTME: A small card pinned bottom right.
import type { components } from '@/api/types'

type Props = { run: components['schemas']['RunView']; onChange: () => void }

export function DemoPanel({ run }: Props) {
  return <aside aria-label="Demo controls">{run.mode}</aside>
}
