// ABOUTME: Renders an assistant's answer for reading: blank lines separate paragraphs, and a run of lines starting with "- " or "1. " is a list.
// ABOUTME: Plain text otherwise; the answer carries no other markup.
type Block = { kind: 'paragraph'; lines: string[] } | { kind: 'bullets' | 'numbers'; items: string[] }

const BULLET = /^[-*•]\s+/
const NUMBER = /^\d+[.)]\s+/

// The answer's blocks: a list is a run of list lines; everything else between blank lines is a paragraph.
export function blocksOf(answer: string): Block[] {
  const blocks: Block[] = []
  for (const chunk of answer.trim().split(/\n\s*\n/)) {
    const lines = chunk.split('\n').map((line) => line.trim()).filter((line) => line !== '')
    let paragraph: string[] = []
    const flush = () => {
      if (paragraph.length > 0) blocks.push({ kind: 'paragraph', lines: paragraph })
      paragraph = []
    }
    for (const line of lines) {
      const kind = BULLET.test(line) ? 'bullets' : NUMBER.test(line) ? 'numbers' : null
      if (kind === null) {
        paragraph.push(line)
        continue
      }
      flush()
      const item = line.replace(kind === 'bullets' ? BULLET : NUMBER, '')
      const last = blocks.at(-1)
      if (last !== undefined && last.kind === kind) last.items.push(item)
      else blocks.push({ kind, items: [item] })
    }
    flush()
  }
  return blocks
}

export function AnswerText({ answer }: { answer: string }) {
  return (
    <div className="flex flex-col gap-2 text-sm">
      {blocksOf(answer).map((block, index) =>
        block.kind === 'paragraph' ? (
          <p key={index}>{block.lines.join(' ')}</p>
        ) : block.kind === 'bullets' ? (
          <ul key={index} className="list-disc space-y-0.5 pl-5">
            {block.items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ul>
        ) : (
          <ol key={index} className="list-decimal space-y-0.5 pl-5">
            {block.items.map((item, i) => (
              <li key={i}>{item}</li>
            ))}
          </ol>
        ),
      )}
    </div>
  )
}
