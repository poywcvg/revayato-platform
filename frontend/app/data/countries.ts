export interface CatalogCountry {
  code: string
  name: string
  movie_count?: number
  series_count?: number
}

/** Keep in sync with backend/apps/catalog/countries.py */
const countryNames: Record<string, string> = {
  AE: 'امارات متحده عربی',
  AL: 'آلبانی',
  AR: 'آرژانتین',
  AT: 'اتریش',
  AU: 'استرالیا',
  AZ: 'آذربایجان',
  BE: 'بلژیک',
  BG: 'بلغارستان',
  BH: 'بحرین',
  BR: 'برزیل',
  CA: 'کانادا',
  CH: 'سوئیس',
  CL: 'شیلی',
  CN: 'چین',
  CO: 'کلمبیا',
  CU: 'کوبا',
  CY: 'قبرس',
  CZ: 'جمهوری چک',
  DE: 'آلمان',
  DK: 'دانمارک',
  EG: 'مصر',
  ES: 'اسپانیا',
  FI: 'فنلاند',
  FR: 'فرانسه',
  GB: 'بریتانیا',
  GE: 'گرجستان',
  GR: 'یونان',
  HK: 'هنگ‌کنگ',
  HR: 'کرواسی',
  HU: 'مجارستان',
  ID: 'اندونزی',
  IE: 'ایرلند',
  IL: 'اسرائیل',
  IN: 'هند',
  IQ: 'عراق',
  IR: 'ایران',
  IS: 'ایسلند',
  IT: 'ایتالیا',
  JO: 'اردن',
  JP: 'ژاپن',
  KR: 'کره جنوبی',
  KW: 'کویت',
  LB: 'لبنان',
  LK: 'سری‌لانکا',
  LT: 'لیتوانی',
  LU: 'لوکزامبورگ',
  LV: 'لتونی',
  MA: 'مراکش',
  MK: 'مقدونیه شمالی',
  MX: 'مکزیک',
  MY: 'مالزی',
  NG: 'نیجریه',
  NL: 'هلند',
  NO: 'نروژ',
  NZ: 'نیوزیلند',
  PE: 'پرو',
  PH: 'فیلیپین',
  PK: 'پاکستان',
  PL: 'لهستان',
  PS: 'فلسطین',
  PT: 'پرتغال',
  QA: 'قطر',
  RO: 'رومانی',
  RS: 'صربستان',
  RU: 'روسیه',
  SA: 'عربستان سعودی',
  SE: 'سوئد',
  SG: 'سنگاپور',
  SK: 'اسلواکی',
  SU: 'اتحاد جماهیر شوروی',
  TH: 'تایلند',
  TN: 'تونس',
  TR: 'ترکیه',
  TW: 'تایوان',
  UA: 'اوکراین',
  US: 'آمریکا',
  VN: 'ویتنام',
  XK: 'کوزوو',
  ZA: 'آفریقای جنوبی',
}

const englishNameToCode: Record<string, string> = {
  albania: 'AL', argentina: 'AR', australia: 'AU', austria: 'AT', azerbaijan: 'AZ',
  bahrain: 'BH', belgium: 'BE', brazil: 'BR', bulgaria: 'BG', canada: 'CA', chile: 'CL',
  china: 'CN', colombia: 'CO', croatia: 'HR', cuba: 'CU', cyprus: 'CY',
  'czech republic': 'CZ', czechia: 'CZ', denmark: 'DK', egypt: 'EG', finland: 'FI',
  france: 'FR', georgia: 'GE', germany: 'DE', greece: 'GR', 'hong kong': 'HK',
  hungary: 'HU', iceland: 'IS', india: 'IN', indonesia: 'ID', iran: 'IR', iraq: 'IQ',
  ireland: 'IE', israel: 'IL', italy: 'IT', japan: 'JP', jordan: 'JO', kosovo: 'XK',
  kuwait: 'KW', latvia: 'LV', lebanon: 'LB', lithuania: 'LT', luxembourg: 'LU',
  macedonia: 'MK', malaysia: 'MY', mexico: 'MX', morocco: 'MA', netherlands: 'NL',
  'new zealand': 'NZ', nigeria: 'NG', 'north macedonia': 'MK', norway: 'NO',
  pakistan: 'PK', palestine: 'PS', peru: 'PE', philippines: 'PH', poland: 'PL',
  portugal: 'PT', qatar: 'QA', romania: 'RO', russia: 'RU', 'saudi arabia': 'SA',
  serbia: 'RS', singapore: 'SG', slovakia: 'SK', 'south africa': 'ZA',
  'south korea': 'KR', 'soviet union': 'SU', spain: 'ES', 'sri lanka': 'LK',
  sweden: 'SE', switzerland: 'CH', taiwan: 'TW', thailand: 'TH', tunisia: 'TN',
  turkey: 'TR', ukraine: 'UA', 'united arab emirates': 'AE', 'united kingdom': 'GB',
  'great britain': 'GB', 'united states': 'US', 'united states of america': 'US',
  usa: 'US', vietnam: 'VN',
}

export const catalogCountries: CatalogCountry[] = Object.entries(countryNames)
  .map(([code, name]) => ({ code, name }))
  .sort((a, b) => a.name.localeCompare(b.name, 'fa'))

export function localizeCountry(name = '', code = '') {
  const normalizedCode = code.trim().toUpperCase()
  if (countryNames[normalizedCode]) return countryNames[normalizedCode]
  if (/^[A-Za-z]{2}$/.test(name.trim()) && countryNames[name.trim().toUpperCase()]) {
    return countryNames[name.trim().toUpperCase()]
  }
  const inferredCode = englishNameToCode[name.trim().toLowerCase()]
  return countryNames[inferredCode] || name.trim() || normalizedCode
}

export function countryCodeForName(name: string) {
  const normalizedName = name.trim()
  if (/^[A-Za-z]{2}$/.test(normalizedName)) return normalizedName.toUpperCase()
  return catalogCountries.find(country => country.name === normalizedName)?.code
    || englishNameToCode[normalizedName.toLowerCase()]
    || ''
}

/** Prefer ISO code in catalog query strings; fall back to Persian/English label. */
export function countryFilterValue(name = '', code = '') {
  const normalizedCode = (code || countryCodeForName(name)).trim().toUpperCase()
  if (/^[A-Z]{2}$/.test(normalizedCode)) return normalizedCode
  return name.trim()
}

export type CountryRegionId = 'west-asia' | 'east-asia' | 'europe' | 'americas' | 'other'

export interface CountryRegion {
  id: CountryRegionId
  label: string
  codes: string[]
}

export const countryRegions: CountryRegion[] = [
  { id: 'west-asia', label: 'خاورمیانه و غرب آسیا', codes: ['IR', 'TR', 'LB', 'AE', 'QA', 'SA', 'IQ', 'JO', 'KW', 'BH', 'PS', 'EG', 'IL'] },
  { id: 'east-asia', label: 'شرق و جنوب آسیا', codes: ['JP', 'KR', 'CN', 'HK', 'TW', 'TH', 'IN', 'MY', 'PH', 'SG', 'ID', 'PK', 'VN', 'LK'] },
  { id: 'europe', label: 'اروپا', codes: ['FR', 'DE', 'GB', 'IT', 'ES', 'SE', 'NO', 'DK', 'FI', 'NL', 'BE', 'CH', 'AT', 'PL', 'CZ', 'GR', 'IE', 'IS', 'HR', 'LU', 'LV', 'UA', 'RU', 'SU', 'PT', 'RO', 'BG', 'HU', 'RS', 'SK', 'LT', 'AL', 'CY', 'XK', 'MK', 'GE'] },
  { id: 'americas', label: 'قاره آمریکا', codes: ['US', 'CA', 'BR', 'MX', 'AR', 'CL', 'CO', 'PE', 'CU'] },
  { id: 'other', label: 'اقیانوسیه، آفریقا و سایر', codes: ['AU', 'NZ', 'ZA', 'MA', 'TN', 'NG', 'AZ'] },
]

export function regionForCountryCode(code: string): CountryRegionId {
  const normalized = code.trim().toUpperCase()
  for (const region of countryRegions) {
    if (region.codes.includes(normalized)) return region.id
  }
  return 'other'
}

/** SVG flag URL for ISO 3166-1 alpha-2 codes. Empty for unsupported codes. */
export function countryFlagSrc(code: string) {
  const normalized = code.trim().toUpperCase()
  if (!/^[A-Z]{2}$/.test(normalized) || normalized === 'SU') return ''
  return `https://flagcdn.com/${normalized.toLowerCase()}.svg`
}
