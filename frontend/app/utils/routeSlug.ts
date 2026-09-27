/** Normalize SSR-encoded dynamic params before using them as API identifiers. */
export function decodeRouteSlug(value: unknown): string {
  const slug = Array.isArray(value) ? String(value[0] ?? '') : String(value ?? '')
  try {
    return decodeURIComponent(slug)
  } catch {
    // Let the detail endpoint decide whether a malformed-but-valid path exists.
    return slug
  }
}
