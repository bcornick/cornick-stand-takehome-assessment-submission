// ABOUTME: What a lead waits on, and the actions of each open item (A.11): a draft is approved, edited or rejected, a pending value or an unknown delivery is approved or rejected with a reason, and an underwriter question is one card of equal option buttons.
// ABOUTME: A review the underwriter cannot decide shows how it closes; rejecting a decline notice says it sends the asks instead; every control shows the reason the command was refused.
import { approve, editDraft, recordRuling, reject } from '@/api/client'
import type { components } from '@/api/types'
import { ActionForm } from '@/components/ActionForm'
import { Badge } from '@/components/ui/badge'
import { useAction } from '@/components/useAction'
import { formatValue } from '@/format'
import { BLOCKER_KIND_LABELS, OWNER_LABELS } from '@/labels'
import { useState } from 'react'

type Schemas = components['schemas']
type LeadDetail = Schemas['LeadDetail']
type Blocker = LeadDetail['blockers'][number]
type Draft = LeadDetail['drafts'][number]

type Props = { lead: LeadDetail; onChange: () => void }

const REASON = { name: 'reason', label: 'Reason' }

export function Blockers({ lead, onChange }: Props) {
  if (lead.blockers.length === 0) return <p className="text-sm text-muted-foreground">Nothing is waiting.</p>
  return (
    <ul className="flex flex-col gap-4">
      {lead.blockers.map((blocker) => (
        <li key={blocker.item_id} className="flex flex-col gap-2">
          <p className="flex flex-wrap items-baseline gap-2">
            <Badge variant="outline">{BLOCKER_KIND_LABELS[blocker.kind]}</Badge>
            <span className="text-sm text-muted-foreground">
              {`Waits on ${OWNER_LABELS[blocker.owner].toLowerCase()}`}
            </span>
            {blocker.kind !== 'underwriter_question' && <span>{blocker.detail.text}</span>}
          </p>
          <ItemActions lead={lead} blocker={blocker} onChange={onChange} />
        </li>
      ))}
    </ul>
  )
}

function ItemActions({ lead, blocker, onChange }: Props & { blocker: Blocker }) {
  const { item_id: itemId } = blocker
  const { item_kind: itemKind, cause_persists: persists } = blocker.detail
  if (blocker.kind === 'underwriter_question') {
    return <QuestionCard lead={lead} blocker={blocker} onChange={onChange} />
  }
  if (itemKind === 'draft') {
    const draft = lead.drafts.find((d) => d.intent_id === blocker.detail.intent_id)
    return draft === undefined ? null : <DraftActions itemId={itemId} draft={draft} onChange={onChange} />
  }
  if (itemKind === 'observation') {
    const pending = blocker.observation
    const current = lead.facts.find((fact) => fact.key === pending?.key)
    return (
      <>
        {pending !== null && (
          <p className="text-sm">
            {`${pending.key}: proposed ${formatValue(pending.value)}, current ${formatValue(current?.value)}`}
          </p>
        )}
        <ApproveOrReject itemId={itemId} approveLabel="Approve" canReject onChange={onChange} />
      </>
    )
  }
  if (itemKind === 'delivery_unknown') {
    return <ApproveOrReject itemId={itemId} approveLabel="Approve" canReject onChange={onChange} />
  }
  if (itemKind === 'review' && !persists) {
    return <ApproveOrReject itemId={itemId} approveLabel="Acknowledge" canReject={false} onChange={onChange} />
  }
  return (
    <p className="text-sm text-muted-foreground">{`This closes when ${blocker.detail.resume_trigger}.`}</p>
  )
}

type ApproveOrRejectProps = {
  itemId: number
  approveLabel: string
  canReject: boolean
  onChange: () => void
}

function ApproveOrReject({ itemId, approveLabel, canReject, onChange }: ApproveOrRejectProps) {
  return (
    <div className="flex flex-col gap-3">
      <ActionForm
        label={approveLabel}
        fields={[REASON]}
        act={({ reason }) => approve(itemId, reason!)}
        onDone={onChange}
      />
      {canReject && (
        <ActionForm
          label="Reject"
          fields={[REASON]}
          act={({ reason }) => reject(itemId, reason!)}
          onDone={onChange}
        />
      )}
    </div>
  )
}

type DraftActionsProps = { itemId: number; draft: Draft; onChange: () => void }

function DraftActions({ itemId, draft, onChange }: DraftActionsProps) {
  const isDecline = draft.kind === 'decline_notice'
  return (
    <div className="flex flex-col gap-3">
      <ActionForm
        // A new hash is a new draft, which the reason given for the old one does not cover.
        key={`approve-${draft.payload_hash}`}
        label="Approve"
        fields={[REASON]}
        act={({ reason }) => approve(itemId, reason!, draft.payload_hash)}
        onDone={onChange}
      />
      <ActionForm
        // A new hash is a new draft; the fields start again from its text.
        key={draft.payload_hash}
        label="Edit"
        fields={[
          { name: 'subject', label: 'Subject', initial: draft.subject },
          { name: 'body', label: 'Body', initial: draft.body, multiline: true },
          REASON,
        ]}
        act={({ subject, body, reason }) => editDraft(draft.intent_id, subject!, body!, reason!)}
        onDone={onChange}
      />
      {isDecline && (
        <p className="text-sm text-muted-foreground">
          Withdrawing the decline suppresses it for this lead and sends the requests for the facts still missing.
        </p>
      )}
      <ActionForm
        label={isDecline ? 'Withdraw decline and send the asks' : 'Reject'}
        fields={[REASON]}
        act={({ reason }) => reject(itemId, reason!)}
        onDone={onChange}
      />
    </div>
  )
}

// One card for every open choice of the lead: each choice shows the values it needs, then one
// equal button per option, none chosen by default. One reason covers the choice that is answered.
function QuestionCard({ lead, blocker, onChange }: Props & { blocker: Blocker }) {
  const [reason, setReason] = useState('')
  const { busy, message, run } = useAction(onChange)
  const choices = (lead.plan?.open_choices ?? []).filter((choice) =>
    blocker.detail.choice_ids.includes(choice.choice_id),
  )
  const facts = new Map(lead.facts.map((fact) => [fact.key, fact.value]))

  async function answer(choiceId: string, option: string) {
    if (await run(() => recordRuling(lead.lead_id, choiceId, option, reason))) setReason('')
  }

  return (
    <div className="flex flex-col gap-3 rounded-md border p-3">
      {choices.map((choice) => (
        <section key={choice.choice_id} aria-label={choice.choice_id} className="flex flex-col gap-2">
          <p className="text-sm">{choice.prompt}</p>
          <ul className="text-sm text-muted-foreground">
            {choice.show.map((key) => (
              <li key={key}>{`${key}: ${formatValue(facts.get(key))}`}</li>
            ))}
          </ul>
          <span className="flex flex-wrap gap-2">
            {choice.options.map((option) => (
              <button
                key={option}
                type="button"
                disabled={busy || reason.trim() === ''}
                onClick={() => answer(choice.choice_id, option)}
                className="rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
              >
                {option.replace(/_/g, ' ')}
              </button>
            ))}
          </span>
        </section>
      ))}
      <label className="flex flex-col gap-1 text-sm">
        Reason for the choice
        <input
          type="text"
          className="rounded-md border px-2 py-1 text-sm"
          value={reason}
          onChange={(e) => setReason(e.target.value)}
        />
      </label>
      {message !== null && (
        <span role="alert" className="text-sm text-destructive">
          {message}
        </span>
      )}
    </div>
  )
}
