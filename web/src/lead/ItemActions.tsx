// ABOUTME: The actions of one open item (A.11): one card, one decision. The choices are buttons side by side; choosing one opens a single reason field with a confirm button that repeats the choice.
// ABOUTME: A draft folds its text into a preview with an edit form; a review the underwriter cannot decide shows how it closes; rejecting a decline notice says it sends the asks; a refusal reason shows under the choice.
import { approve, editDraft, recordRuling, reject } from '@/api/client'
import type { components } from '@/api/types'
import { ActionForm } from '@/components/ActionForm'
import { Badge } from '@/components/ui/badge'
import { useAction } from '@/components/useAction'
import { fieldLabel, formatValue } from '@/format'
import { BLOCKER_KIND_LABELS, OWNER_LABELS } from '@/labels'
import { useState } from 'react'

type Schemas = components['schemas']
type LeadDetail = Schemas['LeadDetail']
type Blocker = LeadDetail['blockers'][number]
type Draft = LeadDetail['drafts'][number]

type Props = { lead: LeadDetail; onChange: () => void }

// One way to close an item. `act` resolves to the reason it was refused, or null when accepted;
// `confirm` is the confirm button's words when they differ from the choice's own.
type Choice = {
  label: string
  outline: boolean
  act: (reason: string) => Promise<string | null>
  confirm?: string
  note?: string
}

// One open item as the underwriter meets it: what it is, why it waits, and its one decision.
export function OpenItem({ lead, blocker, onChange }: Props & { blocker: Blocker }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="flex flex-wrap items-baseline gap-2">
        <Badge variant="outline">{BLOCKER_KIND_LABELS[blocker.kind]}</Badge>
        <span className="text-sm text-muted-foreground">
          {`Waits on ${OWNER_LABELS[blocker.owner].toLowerCase()}`}
        </span>
        {blocker.kind !== 'underwriter_question' && <span>{blocker.detail.text}</span>}
      </p>
      <ItemActions lead={lead} blocker={blocker} onChange={onChange} />
    </div>
  )
}

function ItemActions({ lead, blocker, onChange }: Props & { blocker: Blocker }) {
  const { item_id: itemId } = blocker
  const { item_kind: itemKind, cause_persists: persists } = blocker.detail
  const approveChoice = (label: string, hash?: string): Choice => ({
    label,
    outline: false,
    act: (reason) => approve(itemId, reason, hash),
  })
  const rejectChoice = (label = 'Reject', note?: string): Choice => ({
    label,
    outline: true,
    act: (reason) => reject(itemId, reason),
    note,
  })

  if (blocker.kind === 'underwriter_question') {
    return <QuestionCard lead={lead} blocker={blocker} onChange={onChange} />
  }
  if (itemKind === 'draft') {
    const draft = lead.drafts.find((d) => d.intent_id === blocker.detail.intent_id)
    if (draft === undefined) return null
    const rejectDraft =
      draft.kind === 'decline_notice'
        ? rejectChoice(
            'Withdraw decline and send the asks',
            'Withdrawing the decline suppresses it for this lead and sends the requests for the facts still missing.',
          )
        : rejectChoice()
    return (
      <>
        <DraftPreview draft={draft} onChange={onChange} />
        <Decision
          // A new hash is a new draft, which the reason given for the old one does not cover.
          key={draft.payload_hash}
          choices={[approveChoice('Approve', draft.payload_hash), rejectDraft]}
          onChange={onChange}
        />
      </>
    )
  }
  if (itemKind === 'observation') {
    const pending = blocker.observation
    const current = lead.facts.find((fact) => fact.key === pending?.key)
    return (
      <>
        {pending !== null && (
          <p className="text-sm">
            {`${fieldLabel(lead.fields, pending.key)}: proposed ${formatValue(pending.value)}, current ${formatValue(current?.value)}`}
          </p>
        )}
        <Decision choices={[approveChoice('Approve'), rejectChoice()]} onChange={onChange} />
      </>
    )
  }
  if (itemKind === 'delivery_unknown') {
    return <Decision choices={[approveChoice('Approve'), rejectChoice()]} onChange={onChange} />
  }
  if (itemKind === 'review' && !persists) {
    return <Decision choices={[approveChoice('Acknowledge')]} onChange={onChange} />
  }
  return (
    <p className="text-sm text-muted-foreground">{`This closes when ${blocker.detail.resume_trigger}.`}</p>
  )
}

// The choices as buttons, none chosen. Choosing one opens the single reason field; the confirm
// stays disabled until the reason has text, so nothing is submitted without one.
function Decision({ choices, onChange }: { choices: Choice[]; onChange: () => void }) {
  const [chosen, setChosen] = useState<Choice | null>(null)
  const [reason, setReason] = useState('')
  const { busy, message, run } = useAction(onChange)

  function close() {
    setChosen(null)
    setReason('')
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (chosen !== null && (await run(() => chosen.act(reason)))) close()
  }

  return (
    <div className="flex flex-col gap-2">
      <span className="flex flex-wrap gap-2">
        {choices.map((choice) => (
          <button
            key={choice.label}
            type="button"
            aria-pressed={chosen === choice}
            onClick={() => setChosen(choice)}
            className={choice.outline ? 'button-outline' : 'button-primary'}
          >
            {choice.label}
          </button>
        ))}
      </span>
      {chosen !== null && (
        <form aria-label="Confirm the choice" onSubmit={submit} className="flex flex-col gap-2">
          {chosen.note !== undefined && <p className="text-sm text-muted-foreground">{chosen.note}</p>}
          <label className="flex flex-col gap-1 text-sm">
            Reason
            <input
              type="text"
              className="rounded-md border px-2 py-1 text-sm"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
            />
          </label>
          <span className="flex flex-wrap items-center gap-2">
            <button type="submit" disabled={busy || reason.trim() === ''} className="button-primary">
              {chosen.confirm ?? chosen.label}
            </button>
            <button type="button" onClick={close} className="button-outline">
              Cancel
            </button>
          </span>
        </form>
      )}
      {message !== null && (
        <span role="alert" className="text-sm text-destructive">
          {message}
        </span>
      )}
    </div>
  )
}

// The draft's text, folded and read-only; Edit opens the form to change it in place.
function DraftPreview({ draft, onChange }: { draft: Draft; onChange: () => void }) {
  const [editing, setEditing] = useState(false)
  return (
    <details className="rounded-md border p-3 text-sm">
      <summary className="cursor-pointer">
        {draft.kind === 'decline_notice' ? 'Preview the notice' : 'Preview the packet'}
      </summary>
      <div className="mt-2 flex flex-col gap-2">
        {editing ? (
          <ActionForm
            // A new hash is a new draft; the fields start again from its text.
            key={draft.payload_hash}
            label="Edit"
            fields={[
              { name: 'subject', label: 'Subject', initial: draft.subject },
              { name: 'body', label: 'Body', initial: draft.body, multiline: true },
              { name: 'reason', label: 'Reason' },
            ]}
            act={({ subject, body, reason }) => editDraft(draft.intent_id, subject!, body!, reason!)}
            onDone={() => {
              setEditing(false)
              onChange()
            }}
          />
        ) : (
          <>
            <p className="font-medium">{draft.subject}</p>
            <p className="whitespace-pre-wrap">{draft.body}</p>
            <span>
              <button type="button" onClick={() => setEditing(true)} className="button-outline">
                Edit
              </button>
            </span>
          </>
        )}
      </div>
    </details>
  )
}

// One section for every open choice of the lead: the prompt, the values it needs, then one equal
// button per option, none chosen by default.
function QuestionCard({ lead, blocker, onChange }: Props & { blocker: Blocker }) {
  const choices = (lead.plan?.open_choices ?? []).filter((choice) =>
    blocker.detail.choice_ids.includes(choice.choice_id),
  )
  const facts = new Map(lead.facts.map((fact) => [fact.key, fact.value]))

  return (
    <div className="flex flex-col gap-3 rounded-md border p-3">
      {choices.map((choice) => (
        <section key={choice.choice_id} aria-label={choice.choice_id} className="flex flex-col gap-2">
          <p className="text-sm">{choice.prompt}</p>
          <ul className="text-sm text-muted-foreground">
            {choice.show.map((key) => (
              <li key={key}>{`${fieldLabel(lead.fields, key)}: ${formatValue(facts.get(key))}`}</li>
            ))}
          </ul>
          <Decision
            choices={choice.options.map((option) => {
              const words = option.replace(/_/g, ' ')
              return {
                label: words,
                confirm: `Choose ${words}`,
                outline: true,
                act: (reason) => recordRuling(lead.lead_id, choice.choice_id, option, reason),
              }
            })}
            onChange={onChange}
          />
        </section>
      ))}
    </div>
  )
}
