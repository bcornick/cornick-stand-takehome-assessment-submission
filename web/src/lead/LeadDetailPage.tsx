// ABOUTME: Loads one lead's detail and shows the detail pane, or a loading or error message.
// ABOUTME: A request that fails shows a plain message and leaves the rest of the page as it is.
import { getLead } from '@/api/client'
import { useRemote } from '@/api/useRemote'
import { DetailPane } from './DetailPane'

export function LeadDetailPage({ leadId }: { leadId: string }) {
  const lead = useRemote(leadId, () => getLead(leadId))
  if (lead.state === 'loading') return <p role="status">{`Loading ${leadId}`}</p>
  if (lead.state === 'error') {
    return <p role="alert">{`Could not load ${leadId}: ${lead.message}.`}</p>
  }
  return <DetailPane lead={lead.data} />
}
