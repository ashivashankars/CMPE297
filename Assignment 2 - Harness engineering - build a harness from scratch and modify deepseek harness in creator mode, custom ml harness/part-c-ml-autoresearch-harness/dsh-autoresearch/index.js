// dsh-autoresearch — turns any DeepSeek Harness agent into an ML researcher that CANNOT cheat.
//
// The agent is the "researcher": it reads the program, proposes one experiment at a time.
// The plugin forwards every proposal to harness.py, which owns the truth:
//   apply edit -> frozen-file hash check -> leakage check -> frozen eval under a time budget
//   -> keep (if better by >= MIN_DELTA) or revert -> append to runs/results.tsv
// The agent never computes its own score and never sees the test split.
//
// Tools: ar_program, ar_experiment, ar_status, ar_finalize
import { execFile } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { promisify } from 'node:util'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'dsh-autoresearch'
export const inject = ['tools']

const run = promisify(execFile)
const text = { schema: { type: 'string' }, render: (_a, v) => [{ type: 'text', text: v }] }

export function apply(ctx, config = {}) {
  const { dir, python = 'python3', budgetSeconds = 60 } = config
  const harness = async (...args) => {
    try {
      const { stdout, stderr } = await run(python, ['harness.py', ...args], { cwd: dir, timeout: (budgetSeconds + 30) * 1000, maxBuffer: 4 << 20 })
      return (stdout + (stderr ? `\n${stderr}` : '')).trim()
    } catch (e) {
      return `harness error: ${(e.stderr || e.message).trim().split('\n').slice(-3).join('\n')}`
    }
  }

  ctx.tools.register(defineTool({
    name: 'ar_program',
    description: 'Start here. Returns the research program (goal and rules), the current train.py, and the leaderboard.',
    parameters: {},
    output: text,
    async execute() {
      const program = readFileSync(join(dir, 'program.md'), 'utf8')
      const train = readFileSync(join(dir, 'train.py'), 'utf8')
      return `${program}\n\n# current train.py\n${train}\n\n# leaderboard\n${await harness('status')}`
    },
  }))

  ctx.tools.register(defineTool({
    name: 'ar_experiment',
    description: 'Run ONE experiment. Give a hypothesis and edits to train.py as a JSON list of {"old": exact unique snippet, "new": replacement}. ' +
      'The harness applies them, checks integrity and leakage, scores with the frozen evaluator, then keeps or reverts. Returns the verdict.',
    parameters: {
      hypothesis: { type: 'string', required: true, description: 'One idea and why it should help' },
      edits: { type: 'string', required: true, description: 'JSON list: [{"old": "...", "new": "..."}]' },
    },
    output: text,
    async execute({ hypothesis, edits }) {
      return harness('step', '--hypothesis', hypothesis, '--edits', edits, '--budget', String(budgetSeconds))
    },
  }))

  ctx.tools.register(defineTool({
    name: 'ar_status',
    description: 'Show the experiment leaderboard: every experiment with status keep/discard/crash/rejected and its validation AUC.',
    parameters: {},
    output: text,
    async execute() { return harness('status') },
  }))

  ctx.tools.register(defineTool({
    name: 'ar_finalize',
    description: 'End the search: score the best kept model once on the hidden test split and write runs/report.md.',
    parameters: {},
    output: text,
    async execute() {
      const out = await harness('finalize')
      return `${out}\n\n${readFileSync(join(dir, 'runs', 'report.md'), 'utf8')}`
    },
  }))
}
