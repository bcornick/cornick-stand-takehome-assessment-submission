// ABOUTME: The one-line message box at the bottom of a conversation.
// ABOUTME: A disabled composer shows the note that says why.
import { useState, type FormEvent } from 'react'

type Props = {
  placeholder: string
  disabled: boolean
  note: string | null
  onSend: (message: string) => void
}

export function Composer({ placeholder, disabled, note, onSend }: Props) {
  const [message, setMessage] = useState('')

  function submit(event: FormEvent) {
    event.preventDefault()
    const text = message.trim()
    if (text === '') return
    onSend(text)
    setMessage('')
  }

  return (
    <form onSubmit={submit} className="flex items-center gap-2 border-t p-3">
      <input
        aria-label="Message"
        value={message}
        onChange={(event) => setMessage(event.target.value)}
        placeholder={placeholder}
        disabled={disabled}
        className="min-w-0 flex-1 rounded-md border px-3 py-1.5 text-sm disabled:opacity-50"
      />
      <button
        type="submit"
        disabled={disabled}
        className="button-primary"
      >
        Send
      </button>
      {note !== null && <p className="text-xs text-muted-foreground">{note}</p>}
    </form>
  )
}
