// dsh-dataset-profiler — gives the agent "data-science eyes" before it writes any model code.
//
//   dataset_profile  rows, column types, missing %, stats, and red flags
//                    (constant columns, ID-like columns, likely target leakage)
//   dataset_suggest  for a chosen target: task type, class balance, metric,
//                    split strategy and a baseline to beat
// Pure JavaScript, no dependencies, so it works in any DSH profile.
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { defineTool } from '@deepseek-ai/dsh-tools'

export const name = 'dsh-dataset-profiler'
export const inject = ['tools']

const text = { schema: { type: 'string' }, render: (_a, v) => [{ type: 'text', text: v }] }

function parseCsv(src, maxRows) {
  const rows = []; let row = [], cell = '', q = false
  for (let i = 0; i < src.length; i++) {
    const c = src[i]
    if (q) { if (c === '"' && src[i + 1] === '"') { cell += '"'; i++ } else if (c === '"') q = false; else cell += c }
    else if (c === '"') q = true
    else if (c === ',') { row.push(cell); cell = '' }
    else if (c === '\n') { row.push(cell.replace(/\r$/, '')); rows.push(row); row = []; cell = ''; if (rows.length > maxRows) break }
    else cell += c
  }
  if (cell || row.length) { row.push(cell); rows.push(row) }
  const [header, ...data] = rows.filter(r => r.length > 1 || r[0] !== '')
  return { header, data }
}

const isMissing = v => v === undefined || v === '' || /^(na|nan|null|none)$/i.test(v)
const isNum = v => v !== '' && !isNaN(Number(v))
const isDate = v => /^\d{4}-\d{2}-\d{2}/.test(v)

function describe(header, data) {
  return header.map((col, j) => {
    const vals = data.map(r => r[j])
    const present = vals.filter(v => !isMissing(v))
    const missingPct = 100 * (vals.length - present.length) / Math.max(vals.length, 1)
    const unique = new Set(present).size
    let type = 'categorical'
    if (present.length && present.every(isNum)) type = 'numeric'
    else if (present.length && present.every(isDate)) type = 'date'
    const out = { col, type, missingPct, unique, n: vals.length }
    if (type === 'numeric') {
      const x = present.map(Number); const m = x.reduce((a, b) => a + b, 0) / x.length
      out.mean = m; out.std = Math.sqrt(x.reduce((a, b) => a + (b - m) ** 2, 0) / x.length)
      out.min = Math.min(...x); out.max = Math.max(...x); out.values = vals.map(v => isMissing(v) ? NaN : Number(v))
    } else {
      const counts = {}; for (const v of present) counts[v] = (counts[v] ?? 0) + 1
      out.top = Object.entries(counts).sort((a, b) => b[1] - a[1]).slice(0, 3)
      out.values = vals
    }
    return out
  })
}

function corr(a, b) {
  const idx = a.map((_, i) => i).filter(i => !isNaN(a[i]) && !isNaN(b[i]))
  const x = idx.map(i => a[i]), y = idx.map(i => b[i]); const n = x.length
  if (n < 3) return 0
  const mx = x.reduce((s, v) => s + v, 0) / n, my = y.reduce((s, v) => s + v, 0) / n
  let sxy = 0, sxx = 0, syy = 0
  for (let i = 0; i < n; i++) { sxy += (x[i] - mx) * (y[i] - my); sxx += (x[i] - mx) ** 2; syy += (y[i] - my) ** 2 }
  return sxx && syy ? sxy / Math.sqrt(sxx * syy) : 0
}

function encodeTarget(t) {
  if (t.type === 'numeric') return t.values
  const classes = [...new Set(t.values.filter(v => !isMissing(v)))]
  return t.values.map(v => isMissing(v) ? NaN : classes.indexOf(v))
}

function flags(cols, cfg, target) {
  const out = []
  for (const c of cols) {
    if (c.unique <= 1) out.push(`constant column "${c.col}" carries no signal - drop it`)
    if (c.missingPct > cfg.missingWarnPct) out.push(`"${c.col}" is ${c.missingPct.toFixed(0)}% missing - impute or add a missing-indicator`)
    if (c.unique === c.n && c.type !== 'numeric') out.push(`"${c.col}" is unique per row (ID-like) - exclude from features`)
    if (/(^|_)id$/i.test(c.col) && c.type === 'numeric' && c.unique === c.n) out.push(`"${c.col}" looks like a row ID - exclude from features`)
  }
  if (target) {
    const y = encodeTarget(target)
    for (const c of cols) {
      if (c === target || c.type !== 'numeric') continue
      const r = corr(c.values, y)
      if (Math.abs(r) > 0.95) out.push(`LEAKAGE? "${c.col}" correlates ${r.toFixed(2)} with target "${target.col}" - check it is known at prediction time`)
      // "only non-zero when the target is positive" -> value is probably recorded AFTER the outcome
      const rows = y.map((v, i) => i).filter(i => !isNaN(y[i]) && !isNaN(c.values[i]))
      const classes = new Set(rows.map(i => y[i]))
      if (classes.size === 2 && rows.length) {
        const pos = Math.max(...classes)
        const agree = rows.filter(i => (c.values[i] !== 0) === (y[i] === pos)).length / rows.length
        if (agree > 0.97 && Math.abs(r) <= 0.95) out.push(`LEAKAGE? "${c.col}" is non-zero almost exactly when "${target.col}" is positive (${(100 * agree).toFixed(1)}% agreement) - likely recorded after the outcome`)
      }
    }
  }
  return out
}

function load(path, cfg, cwd) {
  const { header, data } = parseCsv(readFileSync(resolve(cwd, path), 'utf8'), cfg.maxRows)
  return { header, data, cols: describe(header, data) }
}

export function apply(ctx, config = {}) {
  const cfg = { maxRows: 200000, missingWarnPct: 20, ...config }
  const cwd = () => process.cwd()

  ctx.tools.register(defineTool({
    name: 'dataset_profile',
    description: 'Profile a CSV dataset: shape, column types, missing values, basic statistics and data-quality red flags. Call this before writing any modeling code.',
    parameters: { path: { type: 'string', required: true, description: 'Path to a .csv file' } },
    output: text,
    async execute({ path }) {
      const { data, cols } = load(path, cfg, cwd())
      const lines = [`${path}: ${data.length} rows x ${cols.length} columns`, '',
        'column              type         missing  unique  summary']
      for (const c of cols) {
        const summary = c.type === 'numeric'
          ? `mean ${c.mean.toFixed(2)} std ${c.std.toFixed(2)} [${c.min}, ${c.max}]`
          : `top ${c.top?.map(([v, n]) => `${v}(${n})`).join(' ') ?? '-'}`
        lines.push(`${c.col.padEnd(20)}${c.type.padEnd(13)}${(c.missingPct.toFixed(1) + '%').padStart(7)}  ${String(c.unique).padStart(6)}  ${summary}`)
      }
      const f = flags(cols, cfg)
      lines.push('', f.length ? 'RED FLAGS:\n' + f.map(x => '  - ' + x).join('\n') : 'no red flags')
      return lines.join('\n')
    },
  }))

  ctx.tools.register(defineTool({
    name: 'dataset_suggest',
    description: 'Given a CSV and the target column, recommend task type, metric, validation split and a baseline model, and run a leakage check.',
    parameters: {
      path: { type: 'string', required: true, description: 'Path to a .csv file' },
      target: { type: 'string', required: true, description: 'Name of the column to predict' },
    },
    output: text,
    async execute({ path, target }) {
      const { cols } = load(path, cfg, cwd())
      const t = cols.find(c => c.col === target)
      if (!t) return `ERROR: no column "${target}". Columns: ${cols.map(c => c.col).join(', ')}`
      const classification = t.type !== 'numeric' || t.unique <= 10
      const out = [`target "${target}": ${classification ? 'CLASSIFICATION' : 'REGRESSION'} (${t.unique} distinct values)`]
      let metric = 'RMSE (and MAE)'
      if (classification) {
        const counts = {}; for (const v of t.values) if (!isMissing(v)) counts[v] = (counts[v] ?? 0) + 1
        const total = Object.values(counts).reduce((a, b) => a + b, 0)
        const dist = Object.entries(counts).map(([k, n]) => `${k}: ${(100 * n / total).toFixed(1)}%`).join(', ')
        const minority = Math.min(...Object.values(counts)) / total
        out.push(`class balance: ${dist}`)
        metric = minority < 0.3 ? 'ROC-AUC + PR-AUC (imbalanced; accuracy would mislead)' : 'accuracy + ROC-AUC'
        out.push(`majority-class baseline accuracy: ${(100 * Math.max(...Object.values(counts)) / total).toFixed(1)}%  <- any model must beat this`)
      }
      const dateCol = cols.find(c => c.type === 'date')
      out.push(`metric: ${metric}`)
      out.push(`split: ${dateCol ? `time-based on "${dateCol.col}" (train on past, test on future)` : classification ? 'stratified 5-fold CV' : '5-fold CV'}`)
      out.push(`baseline: ${classification ? 'LogisticRegression, then LightGBM/XGBoost' : 'Ridge, then LightGBM/XGBoost'}`)
      const f = flags(cols, cfg, t)
      if (f.length) out.push('', 'RED FLAGS:', ...f.map(x => '  - ' + x))
      return out.join('\n')
    },
  }))
}
