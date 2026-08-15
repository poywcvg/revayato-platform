/**
 * Extract a muted accent from a poster/backdrop for cinematic detail pages.
 * Falls back to brand emerald when extraction fails or is unsupported.
 */
const FALLBACK = { hex: '#b0e4cc', rgb: '176 228 204' }

function rgbToHex(r: number, g: number, b: number) {
  return `#${[r, g, b].map(v => Math.round(v).toString(16).padStart(2, '0')).join('')}`
}

function luminance(r: number, g: number, b: number) {
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) / 255
}

/** Soften extreme colors so overlays and text stay readable. */
function tameAccent(r: number, g: number, b: number) {
  const lum = luminance(r, g, b)
  let nr = r
  let ng = g
  let nb = b
  if (lum < 0.22) {
    const lift = (0.35 - lum) * 180
    nr = Math.min(255, r + lift)
    ng = Math.min(255, g + lift)
    nb = Math.min(255, b + lift)
  } else if (lum > 0.78) {
    const drop = (lum - 0.65) * 140
    nr = Math.max(0, r - drop)
    ng = Math.max(0, g - drop)
    nb = Math.max(0, b - drop)
  }
  // Bias slightly toward brand mint so dynamic accents still feel on-brand.
  return {
    r: Math.round(nr * 0.72 + 176 * 0.28),
    g: Math.round(ng * 0.72 + 228 * 0.28),
    b: Math.round(nb * 0.72 + 204 * 0.28),
  }
}

export function useDominantColor(source: MaybeRefOrGetter<string | undefined | null>) {
  const accentHex = ref(FALLBACK.hex)
  const accentRgb = ref(FALLBACK.rgb)
  const ready = ref(false)

  async function extract(url: string) {
    if (!import.meta.client || !url) {
      accentHex.value = FALLBACK.hex
      accentRgb.value = FALLBACK.rgb
      ready.value = true
      return
    }

    try {
      const img = new Image()
      img.crossOrigin = 'anonymous'
      const loaded = new Promise<HTMLImageElement>((resolve, reject) => {
        img.onload = () => resolve(img)
        img.onerror = () => reject(new Error('image load failed'))
      })
      img.src = url
      await loaded

      const size = 48
      const canvas = document.createElement('canvas')
      canvas.width = size
      canvas.height = size
      const ctx = canvas.getContext('2d', { willReadFrequently: true })
      if (!ctx) throw new Error('no canvas')

      ctx.drawImage(img, 0, 0, size, size)
      const { data } = ctx.getImageData(0, 0, size, size)

      let r = 0
      let g = 0
      let b = 0
      let count = 0
      for (let i = 0; i < data.length; i += 16) {
        const a = data[i + 3] ?? 0
        if (a < 180) continue
        const pr = data[i] ?? 0
        const pg = data[i + 1] ?? 0
        const pb = data[i + 2] ?? 0
        // Skip near-black / near-white pixels that wash out accents.
        const lum = luminance(pr, pg, pb)
        if (lum < 0.08 || lum > 0.92) continue
        r += pr
        g += pg
        b += pb
        count += 1
      }

      if (!count) throw new Error('no samples')
      const tamed = tameAccent(r / count, g / count, b / count)
      accentHex.value = rgbToHex(tamed.r, tamed.g, tamed.b)
      accentRgb.value = `${tamed.r} ${tamed.g} ${tamed.b}`
    } catch {
      accentHex.value = FALLBACK.hex
      accentRgb.value = FALLBACK.rgb
    } finally {
      ready.value = true
    }
  }

  watch(
    () => toValue(source),
    (url) => { void extract(url || '') },
    { immediate: true },
  )

  const styleVars = computed(() => ({
    '--media-accent': accentHex.value,
    '--media-accent-rgb': accentRgb.value,
  }))

  return { accentHex, accentRgb, ready, styleVars }
}
