import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const css = readFileSync(new URL('../app/assets/css/main.css', import.meta.url), 'utf8')
const toaster = readFileSync(new URL('../app/components/ui/AppNotifications.vue', import.meta.url), 'utf8')
const episodes = readFileSync(new URL('../app/components/content/EpisodeList.vue', import.meta.url), 'utf8')
const catalogDetail = readFileSync(new URL('../app/components/content/CatalogDetail.vue', import.meta.url), 'utf8')

function themeBlock(selector) {
  const escaped = selector.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = css.match(new RegExp(`${escaped}\\s*\\{([\\s\\S]*?)\\n\\}`))
  assert.ok(match, `Missing ${selector} theme block`)
  return match[1]
}

function hexToken(block, token) {
  const match = block.match(new RegExp(`--${token}:\\s*(#[0-9a-fA-F]{6})`))
  assert.ok(match, `Missing hexadecimal --${token}`)
  return match[1]
}

function luminance(hex) {
  const channels = hex.slice(1).match(/../g).map(value => Number.parseInt(value, 16) / 255)
  const [red, green, blue] = channels.map(value => (
    value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
  ))
  return (0.2126 * red) + (0.7152 * green) + (0.0722 * blue)
}

function contrast(first, second) {
  const firstLuminance = luminance(first)
  const secondLuminance = luminance(second)
  return (Math.max(firstLuminance, secondLuminance) + 0.05)
    / (Math.min(firstLuminance, secondLuminance) + 0.05)
}

test('light theme text and action colors meet WCAG AA', () => {
  const light = themeBlock('html[data-theme="light"]')
  const surface = hexToken(light, 'theme-bg-surface')
  const accent = hexToken(light, 'theme-accent-primary')

  assert.ok(contrast(hexToken(light, 'theme-text-primary'), surface) >= 7)
  assert.ok(contrast(hexToken(light, 'theme-text-secondary'), surface) >= 4.5)
  assert.ok(contrast(hexToken(light, 'theme-text-muted'), surface) >= 4.5)
  assert.ok(contrast(accent, surface) >= 4.5)
  assert.ok(contrast(hexToken(light, 'theme-primary-200'), surface) >= 4.5)
  assert.ok(contrast(hexToken(light, 'theme-primary-300'), surface) >= 4.5)
  assert.ok(contrast(hexToken(light, 'theme-primary-400'), surface) >= 4.5)
  assert.ok(contrast(hexToken(light, 'theme-on-accent'), accent) >= 4.5)
  assert.ok(contrast(hexToken(light, 'theme-error'), surface) >= 4.5)
})

test('cinematic surfaces reset light theme palette before rendering media text', () => {
  const media = themeBlock('.theme-media-dark')

  assert.match(media, /--palette-ink-rgb:\s*236 238 239/)
  assert.match(media, /--theme-bg-main:\s*#070809/)
  assert.match(media, /--theme-text-primary:\s*#eceeef/)
  assert.match(media, /--theme-primary-500:\s*#b0e4cc/)
  assert.match(media, /--theme-error:\s*#f87171/)
  assert.match(media, /--color-ink:\s*#eceeef/)
  assert.match(media, /--color-primary-300:\s*#7a9e90/)
})

test('toaster stays dark-only; media overlays keep cinematic dark isolation', () => {
  assert.match(toaster, /theme="dark"/)
  assert.match(episodes, /theme-media-dark relative aspect-video/)
  assert.match(episodes, /bg-elevated text-secondary ring-1 ring-line/)
  assert.doesNotMatch(episodes, /<EmptyState[^>]+dark\s*\/>/)
  assert.match(catalogDetail, /<article class="media-detail overflow-clip"/)
  assert.doesNotMatch(catalogDetail, /<article class="[^\"]*theme-media-dark/)
})
