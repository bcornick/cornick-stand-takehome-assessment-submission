// ABOUTME: The drill-down panel on the right: the fact, event, message, reply, playbook page or full lead that a citation chip or a link opened.
// ABOUTME: It loads the lead and its events once for every view and closes with one click.
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
  event: 'Event',
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
      className={`${target.kind === 'lead' ? 'w-[480px]' : 'w-[360px]'} flex shrink-0 flex-col gap-4 overflow-y-auto border-l p-4`}
    >
      <header className="flex items-center justify-between">
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
