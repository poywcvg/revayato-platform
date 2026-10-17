import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

import { anyRepairActive, repairBadge, STAGED_REJECT_LABEL } from '../app/utils/stagedRebuild.ts'

const backend = readFileSync(
  new URL('../../backend/apps/catalog/title_staging.py', import.meta.url),
  'utf8',
)

test('every backend reject code has Persian words', () => {
  const codes = [...backend.matchAll(/^REJECT_\w+ = '([a-z_]+)'/gm)].map(match => match[1])
  assert.ok(codes.length >= 5)
  for (const code of codes) assert.ok(STAGED_REJECT_LABEL[code], `missing label for ${code}`)
})

test('applied run reads as replaced, rejected run says why it was left alone', () => {
  assert.equal(repairBadge({ mode: 'staged', state: 'done', verdict: 'applied' }).tone, 'success')
  const rejected = repairBadge({ mode: 'staged', state: 'done', verdict: 'rejected', verdict_reason: 'fresh_dead' })
  assert.equal(rejected.label, 'دست نخورد')
  assert.equal(rejected.hint, STAGED_REJECT_LABEL.fresh_dead)
})

test('no run, active runs and stale runs', () => {
  assert.equal(repairBadge(undefined), null)
  assert.equal(repairBadge({ state: 'queued' }).label, 'در صف')
  assert.match(repairBadge({ state: 'running', step: 'test' }).label, /تست لینک‌ها/)
  assert.equal(repairBadge({ state: 'failed' }).tone, 'danger')
  assert.equal(anyRepairActive([undefined, { state: 'done' }]), false)
  assert.equal(anyRepairActive([{ state: 'running' }]), true)
})

test('an untested rebuild says it replaced without a test', () => {
  const badge = repairBadge({ mode: 'rebuild', state: 'done' })
  assert.equal(badge.label, 'جایگزین شد · بدون تست')
  assert.equal(badge.tone, 'success')
  assert.equal(repairBadge({ mode: 'complete', state: 'done' }).label, 'تکمیل شد')
})

test('a rebuild that left a problem open is a warning that names it', () => {
  const badge = repairBadge({ state: 'done', mode: 'rebuild', problems_fixed: ['approx_rating'], problems_left: ['source_gap'] })
  assert.equal(badge.tone, 'warning')
  assert.equal(badge.hint, 'رفع شد: نمرهٔ تقریبی · باقی مانده: پخش در مرورگر')
})

test('a rebuild that fixed everything stays a success and says what it fixed', () => {
  const badge = repairBadge({ state: 'done', mode: 'rebuild', problems_fixed: ['subtitle_gap'], problems_queued: [], problems_left: [] })
  assert.equal(badge.tone, 'success')
  assert.equal(badge.hint, 'رفع شد: زیرنویس')
})
