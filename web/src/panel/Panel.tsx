// ABOUTME: The drill-down panel on the right: the fact, event, message, reply, playbook page or full lead that a citation chip or a link opened.
// ABOUTME: It loads the lead and its events once for every view and closes with one click; it overlays the conversation and sizes to its content, so nothing in it scrolls sideways.
import { getLead, getLeadEvents } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { DetailPane } from '@/lead/DetailPane'
import type { PanelTarget } from '@/surface'
import { EventView, FactView, MessageView, PageView, ReplyView, type ViewProps } from './views'

type Props = {
  target: PanelTarget
  refresh: number
  onOpen: (target: PanelTarget) => void
  onClose: () => void
  onChange: () => void
}

const TITLES: Record<PanelTarget['kind'], string> = {
  event: 'Event timeline',
  fact: 'Fact',
  message: 'Message',
  reply: 'Reply',
  page: 'Playbook page',
  lead: 'Lead',
}

export function Panel({ target, refresh, onOpen, onClose, onChange }: Props) {
  const loaded = useRemote(
    `panel:${target.lead_id}`,
    () => Promise.all([getLead(target.lead_id), getLeadEvents(target.lead_id)]),
    refresh,
  )
  return (
    <aside
      aria-label="Detail"
      // A layer over the conversation: as wide as its content, up to 700px, and never scrolling sideways.
      // Its own scrollbar is the right-hand gutter, so the content sits as close to both edges.
      className="fixed top-0 right-0 z-10 flex h-screen w-fit max-w-[700px] min-w-[360px] flex-col gap-4 overflow-x-hidden overflow-y-auto border-l bg-background py-4 pr-1 pl-4 shadow-[-12px_0_32px_rgba(0,0,0,0.12)]"
    >
      {/* The header stays at the top while the panel scrolls, so Close is always in reach. It reaches over the
          panel's padding on the top and both sides, so the content scrolls under it from edge to edge. */}
      <header className="sticky -top-4 z-10 -mt-4 -mr-1 -ml-4 flex items-center justify-between border-b bg-background pt-4 pr-1 pb-3 pl-4">
        <h2 className="text-base font-semibold">{TITLES[target.kind]}</h2>
        <button type="button" onClick={onClose} className="button-outline">
          Close
        </button>
      </header>
      {loaded.state === 'loading' && <p role="status">Loading</p>}
      {loaded.state === 'error' && <p role="alert">{`Could not load: ${loaded.message}.`}</p>}
      {loaded.state === 'ready' && (
        <View
          target={target}
          lead={loaded.data[0]}
          events={loaded.data[1].events}
          onOpen={onOpen}
          onChange={onChange}
        />
      )}
    </aside>
  )
}

function View({ target, lead, events, onOpen, onChange }: Omit<ViewProps, 'target'> & { target: PanelTarget; onChange: () => void }) {
  if (target.kind === 'lead') return <DetailPane lead={lead} onChange={onChange} />
  const view = { target, lead, events, onOpen }
  switch (target.kind) {
    case 'event':
      return <EventView {...view} />
    case 'fact':
      return <FactView {...view} />
    case 'message':
      return <MessageView {...view} />
    case 'reply':
      return <ReplyView {...view} />
    case 'page':
      return <PageView {...view} />
  }
}
