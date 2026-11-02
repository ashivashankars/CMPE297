// dsh-second-brain — a "second brain" plugin for DeepSeek Harness, written from scratch.
//
// The agent gets three tools:
//   brain_capture  save an idea as a Markdown note (tags + [[wiki links]] to other notes)
//   brain_search   rank notes for a question (title > tags > body, boosted by backlinks)
//   brain_graph    show which notes link to which (the "map" of your knowledge)
// Notes are plain .md files, so they also open in Obsidian / VS Code.
import { mkdirSync, readdirSync, readFileSync, writeFileSync, existsSync } from 'node:fs'
import { join } from 'node:path'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'dsh-second-brain'
export const inject = ['tools']

const slug = s => s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 60) || 'note'
const words = s => (s.toLowerCase().match(/[a-z0-9]+/g) ?? []).filter(w => w.length > 2)
const text = { schema: { type: 'string' }, render: (_a, v) => [{ type: 'text', text: v }] }

function loadNotes(dir) {
  if (!existsSync(dir)) return []
  return readdirSync(dir).filter(f => f.endsWith('.md')).map(file => {
    const raw = readFileSync(join(dir, file), 'utf8')
    const title = raw.match(/^title: (.*)$/m)?.[1] ?? file
    const tags = (raw.match(/^tags: \[(.*)\]$/m)?.[1] ?? '').split(',').map(t => t.trim()).filter(Boolean)
    const body = raw.split(/^---$/m).slice(2).join('---').trim()
    const links = [...body.matchAll(/\[\[([^\]]+)\]\]/g)].map(m => slug(m[1]))
    return { id: file.replace(/\.md$/, ''), title, tags, body, links }
  })
}

function backlinks(notes) {
  const count = {}
  for (const n of notes) for (const l of n.links) count[l] = (count[l] ?? 0) + 1
  return count
}

export function apply(ctx, config = {}) {
  const dir = config.dir
  mkdirSync(dir, { recursive: true })

  ctx.tools.register(defineTool({
    name: 'brain_capture',
    description: 'Save a note to the user\'s second brain. Link related notes with [[Note Title]] inside the body.',
    parameters: {
      title: { type: 'string', required: true, description: 'Short title of the note' },
      body: { type: 'string', required: true, description: 'Markdown body; use [[Other Note]] to link' },
      tags: { type: 'string', description: 'Comma-separated tags, e.g. "ml, harness"' },
    },
    output: text,
    async execute({ title, body, tags = '' }) {
      const id = slug(title)
      const tagList = tags.split(',').map(t => t.trim()).filter(Boolean)
      const date = new Date().toISOString().slice(0, 10)
      writeFileSync(join(dir, `${id}.md`), `---\ntitle: ${title}\ntags: [${tagList.join(', ')}]\ncreated: ${date}\n---\n${body}\n`)
      const notes = loadNotes(dir)
      const links = notes.find(n => n.id === id)?.links ?? []
      const missing = links.filter(l => !notes.some(n => n.id === l))
      return `saved ${id}.md (${notes.length} notes total); links -> ${links.join(', ') || 'none'}` +
        (missing.length ? `; not yet written: ${missing.join(', ')}` : '')
    },
  }))

  ctx.tools.register(defineTool({
    name: 'brain_search',
    description: 'Search the second brain. Returns the best-matching notes with a snippet.',
    parameters: {
      query: { type: 'string', required: true, description: 'What to look for' },
      limit: { type: 'integer', description: 'Max results (default 3)' },
    },
    output: text,
    async execute({ query, limit = 3 }) {
      const notes = loadNotes(dir)
      const back = backlinks(notes)
      const q = words(query)
      const scored = notes.map(n => {
        const t = words(n.title), g = n.tags.flatMap(words), b = words(n.body)
        let s = 0
        for (const w of q) s += 3 * t.filter(x => x === w).length + 2 * g.filter(x => x === w).length + b.filter(x => x === w).length
        return { n, s: s ? s + (back[n.id] ?? 0) : 0 }
      }).filter(x => x.s > 0).sort((a, b) => b.s - a.s).slice(0, limit)
      if (!scored.length) return `no notes match "${query}" (${notes.length} notes searched)`
      return scored.map(({ n, s }) =>
        `* ${n.title}  [score ${s}, ${back[n.id] ?? 0} backlinks, tags: ${n.tags.join(', ') || '-'}]\n  ${n.body.replace(/\s+/g, ' ').slice(0, 140)}`).join('\n')
    },
  }))

  ctx.tools.register(defineTool({
    name: 'brain_graph',
    description: 'Show the link graph of the second brain: each note, what it links to, and its backlinks.',
    parameters: {},
    output: text,
    async execute() {
      const notes = loadNotes(dir)
      const back = backlinks(notes)
      if (!notes.length) return 'the second brain is empty'
      return notes.map(n => `${n.id}  ->  ${n.links.join(', ') || '(none)'}   [backlinks: ${back[n.id] ?? 0}]`).join('\n')
    },
  }))
}
