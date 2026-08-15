/** Catalog labels: English (Latin) + Persian only — drop CJK and other scripts. */

const LATIN_LETTER = /\p{Script=Latin}/u
const PERSIAN_LETTER = /\p{Script=Arabic}/u
const ANY_LETTER = /\p{L}/u

export function isMostlyLatin(value: string): boolean {
  const letters = [...value].filter(ch => ANY_LETTER.test(ch))
  if (!letters.length) return false
  const latin = letters.filter(ch => LATIN_LETTER.test(ch)).length
  return latin / letters.length >= 0.6
}

export function isMostlyPersian(value: string): boolean {
  const letters = [...value].filter(ch => ANY_LETTER.test(ch))
  if (!letters.length) return false
  const persian = letters.filter(ch => PERSIAN_LETTER.test(ch)).length
  return persian / letters.length >= 0.6
}

/** True when every letter is Latin or Persian/Arabic (catalog allowlist). */
export function isAllowedCatalogName(value: string): boolean {
  const letters = [...value].filter(ch => ANY_LETTER.test(ch))
  if (!letters.length) return true
  return letters.every(ch => LATIN_LETTER.test(ch) || PERSIAN_LETTER.test(ch))
}

export function preferEnglishName(
  ...candidates: Array<string | null | undefined>
): { primary: string; secondary: string } {
  const unique = [...new Set(
    candidates
      .map(value => (value || '').trim())
      .filter(Boolean)
      .filter(isAllowedCatalogName),
  )]
  if (!unique.length) return { primary: '', secondary: '' }

  const english = unique.find(isMostlyLatin)
  const localized = unique.find(name => isMostlyPersian(name) || !isMostlyLatin(name))

  if (english) {
    return {
      primary: english,
      secondary: localized && localized !== english ? localized : '',
    }
  }

  return {
    primary: unique[0] || '',
    secondary: unique[1] && unique[1] !== unique[0] ? unique[1] : '',
  }
}

/** English-only label for catalog cards (poster rails, grids). */
export function englishCatalogTitle(
  item: { title?: string; secondary_title?: string; original_title?: string },
): string {
  const english = (item.secondary_title || item.original_title || '').trim()
  if (english && isMostlyLatin(english)) return english
  const { primary } = preferEnglishName(item.original_title, item.secondary_title, item.title)
  return primary || (item.title || '').trim()
}
