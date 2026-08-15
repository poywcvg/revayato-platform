import assert from 'node:assert/strict'
import test from 'node:test'

import { isDeadPlaybackHost, isPlayablePlaybackUrl, linkMatchesEpisode, pickStreamFriendlyLink } from '../app/utils/downloadMeta.ts'

test('browser-safe MP4 wins over an incompatible MKV quality label', () => {
  const selected = pickStreamFriendlyLink([
    { quality: '480p', url: 'https://cdn.example/movie.mkv' },
    { quality: '720p', url: 'https://cdn.example/movie.mp4' },
  ], 'lean')

  assert.equal(selected?.url, 'https://cdn.example/movie.mp4')
})

test('network profile selects a sensible MP4 startup rung', () => {
  const links = [
    { quality: '480p', url: 'https://cdn.example/movie-480.mp4' },
    { quality: '720p', url: 'https://cdn.example/movie-720.mp4' },
    { quality: '1080p', url: 'https://cdn.example/movie-1080.mp4' },
  ]

  assert.equal(pickStreamFriendlyLink(links, 'lean')?.quality, '480p')
  assert.equal(pickStreamFriendlyLink(links, 'balanced')?.quality, '480p')
  assert.equal(pickStreamFriendlyLink(links, 'fast')?.quality, '720p')
})

test('subtitle sidecars are never selected as video sources', () => {
  const selected = pickStreamFriendlyLink([
    { quality: 'auto', url: 'https://cdn.example/movie.vtt' },
    { quality: '480p', url: 'https://cdn.example/movie.mp4' },
  ], 'balanced')

  assert.equal(selected?.url, 'https://cdn.example/movie.mp4')
})

test('dead Soft CDN hosts are skipped when a live mirror exists', () => {
  assert.equal(isDeadPlaybackHost('https://dl2.cdnhost.lol/Movies/x/Soft/a.mkv'), true)
  assert.equal(isDeadPlaybackHost('https://s13.dlyar.top/Movies/x/Hard/a.mp4'), true)
  assert.equal(isDeadPlaybackHost('https://not-dlyar.top/Movies/x/Hard/a.mp4'), false)
  assert.equal(isPlayablePlaybackUrl('https://dl2.cdnhost.lol/Movies/x/Soft/a.mkv'), false)
  assert.equal(isPlayablePlaybackUrl('https://cdn.live.example/Movies/x/Hard/a.mkv'), true)

  const selected = pickStreamFriendlyLink([
    { quality: '1080p', url: 'https://dl2.cdnhost.lol/Movies/x/Soft/a.mkv' },
    { quality: '720p', url: 'https://cdn.live.example/Movies/x/Hard/a.mkv' },
  ], 'balanced')

  assert.equal(selected?.url, 'https://cdn.live.example/Movies/x/Hard/a.mkv')
})

test('subtitle and malformed provider URLs are never treated as video', () => {
  assert.equal(isPlayablePlaybackUrl('https://cdn.example/movie.fa.srt'), false)
  assert.equal(isPlayablePlaybackUrl('https://cdn.example/Show.E01.mp41'), false)
  assert.equal(isPlayablePlaybackUrl('https://cdn.example/Show.E02.mkvر'), false)
  assert.equal(isPlayablePlaybackUrl('https://cdn.example/Show.E03.mp4?token=ok'), true)
  assert.equal(isPlayablePlaybackUrl('https://cdn.example/cover.jpg'), false)
  assert.equal(isPlayablePlaybackUrl('javascript:alert(1)'), false)
})

test('series links remain strictly scoped to the selected season and episode', () => {
  const selected = { url: 'https://cdn.example/show.S02E03.720p.mkv', quality: '720p' }
  const otherEpisode = { url: 'https://cdn.example/show.S02E04.720p.mkv', quality: '720p' }
  const otherSeason = { url: 'https://cdn.example/show.S01E03.720p.mkv', quality: '720p' }

  assert.equal(linkMatchesEpisode(selected, 2, 3), true)
  assert.equal(linkMatchesEpisode(otherEpisode, 2, 3), false)
  assert.equal(linkMatchesEpisode(otherSeason, 2, 3), false)
})
