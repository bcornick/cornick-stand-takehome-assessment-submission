// ABOUTME: The drill-down panel on the right: the fact, event, message, playbook page or full lead that a citation chip or a link opened.
// ABOUTME: One click closes it.
import type { PanelTarget } from '@/surface'

type Props = {
  target: PanelTarget
  refresh: number
  onOpen: (target: PanelTarget) => void
  onClose: () => void
  onChange: () => void
}

export function Panel({ target, onClose }: Props) {
  return (
    <aside aria-label="Detail">
      <button type="button" onClick={onClose}>
        Close
      </button>
      {target.kind}
    </aside>
  )
}
