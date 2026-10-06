// ABOUTME: A form of required text or choice fields with one submit button; it shows the reason when the action is refused or fails, and tells the page to refetch when the action is done.
// ABOUTME: The button stays disabled until every field has text, so a reason cannot be skipped; the fields return to their initial text after an accepted action. A destructive action's button is a neutral outline.
import { useState } from 'react'
import { useAction } from './useAction'

export type FormField = {
  name: string
  label: string
  multiline?: boolean
  initial?: string
  // A field with options is a choice of one of them, shown by its label.
  options?: { value: string; label: string }[]
}

type Props = {
  label: string
  fields: FormField[]
  act: (values: Record<string, string>) => Promise<string | null>
  onDone: () => void
  destructive?: boolean
}

const inputClass = 'rounded-md border px-2 py-1 text-sm'

export function ActionForm({ label, fields, act, onDone, destructive = false }: Props) {
  const initial = Object.fromEntries(fields.map((field) => [field.name, field.initial ?? '']))
  const [values, setValues] = useState<Record<string, string>>(initial)
  const { busy, message, run } = useAction(onDone)
  const complete = fields.every((field) => (values[field.name] ?? '').trim() !== '')

  async function submit(event: React.FormEvent) {
    event.preventDefault()
    if (await run(() => act(values))) setValues(initial)
  }

  return (
    <form aria-label={label} onSubmit={submit} className="flex flex-col gap-2">
      {fields.map((field) => (
        <label key={field.name} className="flex flex-col gap-1 text-sm">
          {field.label}
          {field.options !== undefined ? (
            <select
              className={inputClass}
              value={values[field.name]}
              onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
            >
              <option value="" />
              {field.options.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
          ) : field.multiline === true ? (
            <textarea
              rows={6}
              className={inputClass}
              value={values[field.name]}
              onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
            />
          ) : (
            <input
              type="text"
              className={inputClass}
              value={values[field.name]}
              onChange={(e) => setValues({ ...values, [field.name]: e.target.value })}
            />
          )}
        </label>
      ))}
      <span className="flex flex-wrap items-center gap-2">
        <button
          type="submit"
          disabled={busy || !complete}
          className={destructive ? 'button-outline' : 'button-primary'}
        >
          {label}
        </button>
        {message !== null && (
          <span role="alert" className="text-sm text-destructive">
            {message}
          </span>
        )}
      </span>
    </form>
  )
}
