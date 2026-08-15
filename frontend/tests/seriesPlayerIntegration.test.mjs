import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'

const watchPage = readFileSync(
  new URL('../app/pages/watch/[slug].vue', import.meta.url),
  'utf8',
)
const player = readFileSync(
  new URL('../app/components/content/VideoPlayer.vue', import.meta.url),
  'utf8',
)
const watchProgress = readFileSync(
  new URL('../app/composables/useWatchProgress.ts', import.meta.url),
  'utf8',
)

test('watch page rejects a route source from another selected episode', () => {
  assert.match(watchPage, /activeRouteSource[\s\S]*episodeScopedLinks\.value\.some\(link => link\.url === queried\)/)
  assert.match(watchPage, /linkMatchesEpisode\(sourceLink\.value, season, episodeNo\)/)
})

test('online player exposes seasons, episodes, previous/next and episode requests', () => {
  assert.match(player, /episodeRequest: \[episode: PlaybackEpisodeOption\]/)
  assert.match(player, /settingsTab === 'episodes'/)
  assert.match(player, /previousEpisode/)
  assert.match(player, /nextEpisode/)
  assert.match(watchPage, /@episode-request="selectEpisode"/)
})

test('series resume progress is scoped to the saved episode', () => {
  assert.match(watchProgress, /contentType === 'series' && episodeId && entry\.episode_id !== episodeId/)
  assert.match(watchPage, /progressFor\(item\.value\.id, item\.value\.type, currentEpisode\.value\?\.id\)/)
})

test('finishing an episode advances to the next ordered episode', () => {
  assert.match(watchPage, /orderedEpisodes\.value\[currentIndex \+ 1\]/)
  assert.match(watchPage, /پخش خودکار/)
})
