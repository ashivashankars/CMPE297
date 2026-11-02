#!/usr/bin/env node
// scripted-model.mjs — a tiny stand-in "LLM" for recording DeepSeek Harness demos offline.
//
// DSH's DeepSeek adapter speaks the Anthropic-Messages SSE protocol at $DEEPSEEK_BASE_URL/messages.
// This server answers that protocol, replaying a JSON script of steps:
//     {"tool": "brain_capture", "args": {...}}   -> the model "calls" a tool
//     {"text": "..."}                            -> the model answers; {{last}} = latest tool result
// The HARNESS and PLUGINS are 100% real: DSH loads the plugins, validates args, runs the tools,
// and feeds the results back. Only the model's choices are pre-written.
// With a real key (DeepSeek or OpenRouter, see ../README.md) you don't need this file at all.
//
//   node scripted-model.mjs --port 8765 --script ../demo/second-brain.json
import { createServer } from 'node:http'
import { readFileSync } from 'node:fs'

const arg = (k, d) => { const i = process.argv.indexOf(k); return i > 0 ? process.argv[i + 1] : d }
const port = Number(arg('--port', 8765))
const steps = JSON.parse(readFileSync(arg('--script'), 'utf8'))
let cursor = 0

function lastToolResult(messages) {
  for (const m of [...messages].reverse()) {
    if (!Array.isArray(m.content)) continue
    for (const block of [...m.content].reverse()) {
      if (block.type !== 'tool_result') continue
      const c = block.content
      const text = Array.isArray(c) ? c.map(x => x.text ?? '').join('') : String(c ?? '')
      return text.trim()
    }
  }
  return ''
}

createServer((req, res) => {
  if (req.method !== 'POST' || !req.url.endsWith('/messages')) { res.writeHead(404).end(); return }
  let body = ''
  req.on('data', d => (body += d))
  req.on('end', () => {
    const request = JSON.parse(body)
    // Side requests (e.g. auto session titles) also hit this endpoint; give them a short title.
    const isMainAgent = (request.tools ?? []).length > 0
    const step = isMainAgent ? (steps[cursor++] ?? { text: '(script finished)' }) : { text: 'Demo session' }
    if (isMainAgent) {
      const names = request.tools.map(t => t.name)
      const custom = names.filter(n => /^(brain_|dataset_|ar_)/.test(n))
      process.stderr.write(`[scripted-model] request #${cursor}: ${names.length} tools offered; plugin tools: ${custom.join(', ') || '-'}\n`)
    }
    const send = ev => res.write(`event: ${ev.type}\ndata: ${JSON.stringify(ev)}\n\n`)
    res.writeHead(200, { 'content-type': 'text/event-stream', 'cache-control': 'no-cache' })
    send({ type: 'message_start', message: { id: `msg_${cursor}`, type: 'message', role: 'assistant',
      model: 'scripted-model', content: [], usage: { input_tokens: Math.round(body.length / 4), output_tokens: 0 } } })
    if (step.tool) {
      const json = JSON.stringify(step.args ?? {})
      send({ type: 'content_block_start', index: 0, content_block: { type: 'tool_use', id: `toolu_${cursor}`, name: step.tool, input: {} } })
      send({ type: 'content_block_delta', index: 0, delta: { type: 'input_json_delta', partial_json: json } })
      send({ type: 'content_block_stop', index: 0 })
      send({ type: 'message_delta', delta: { stop_reason: 'tool_use', stop_sequence: null }, usage: { output_tokens: 20 } })
    } else {
      const text = step.text.replace('{{last}}', lastToolResult(request.messages ?? []))
      send({ type: 'content_block_start', index: 0, content_block: { type: 'text', text: '' } })
      send({ type: 'content_block_delta', index: 0, delta: { type: 'text_delta', text } })
      send({ type: 'content_block_stop', index: 0 })
      send({ type: 'message_delta', delta: { stop_reason: 'end_turn', stop_sequence: null }, usage: { output_tokens: text.length / 4 | 0 } })
    }
    send({ type: 'message_stop' })
    res.end()
  })
}).listen(port, '127.0.0.1', () => process.stderr.write(`[scripted-model] listening on http://127.0.0.1:${port}/v1 (${steps.length} steps)\n`))
