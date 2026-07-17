export function useLibrary() {
  const watchlistIds = useState<number[]>('mock-watchlist', () => [1, 3, 101])
  const likedIds = useState<number[]>('mock-likes', () => [1, 6])

  const isInWatchlist = (id: number) => watchlistIds.value.includes(id)
  const isLiked = (id: number) => likedIds.value.includes(id)

  function toggleIn(list: Ref<number[]>, id: number) {
    list.value = list.value.includes(id)
      ? list.value.filter(itemId => itemId !== id)
      : [...list.value, id]
  }

  return {
    watchlistIds,
    likedIds,
    isInWatchlist,
    isLiked,
    toggleWatchlist: (id: number) => toggleIn(watchlistIds, id),
    toggleLike: (id: number) => toggleIn(likedIds, id),
  }
}
