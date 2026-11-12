// String catalogs keyed by stable ids. English is the source of truth; any key
// missing from sn/nd falls back to English at lookup time (see index.ts).

export type Lang = 'en' | 'sn' | 'nd'
export type Catalog = Record<string, string>

export const LANGS: { code: Lang; label: string }[] = [
  { code: 'en', label: 'English' },
  { code: 'sn', label: 'chiShona' },
  { code: 'nd', label: 'isiNdebele' },
]

export const en: Catalog = {
  'nav.aria': 'Main navigation',
  'nav.workspace': 'Workspace',
  'nav.registry': 'Registry',
  'nav.jobs': 'Jobs',
  'nav.exports': 'Exports',
  'nav.governance': 'Governance',
  'nav.ops': 'Ops',
  'nav.modelstudio': 'Model Studio',
  'nav.evaluate': 'Evaluate',
  'nav.weighttools': 'Weight Tools',
  'nav.modelcard': 'Model Card',
  'nav.compliance': 'Compliance',
  'nav.safety': 'Safety',
  'nav.enterprise': 'Enterprise',
  'nav.updates': 'Updates',
  'nav.plugins': 'Plugins',
  'nav.evidence': 'Evidence',
  'nav.admin': 'Admin',
  'nav.skip': 'Skip to main content',
  'common.login': 'Sign in',
  'common.signingIn': 'Signing in…',
  'common.logout': 'Logout',
  'common.run': 'Run',
  'common.save': 'Save',
  'common.loading': 'Loading…',
  'common.language': 'Language',
  'common.refresh': 'Refresh',
  'common.install': 'Install',
  'common.enable': 'Enable',
  'common.disable': 'Disable',
  'login.subtitle': 'Sign in to your private, sealed workspace.',
  'login.username': 'Username',
  'login.password': 'Password',
  'login.invalid': 'Invalid username or password.',
  'login.unreachable': 'Could not reach the gateway.',
  'plugins.title': 'Plug-ins',
  'evidence.title': 'Evidence packs',
  'evidence.export': 'Export evidence pack',
}

// TODO native review: all sn entries should be checked by native speakers.
export const sn: Catalog = {
  'nav.jobs': 'Mabasa',
  'nav.updates': 'Zvigadziriso',
  'common.login': 'Pinda',
  'common.logout': 'Buda',
  'common.save': 'Chengetedza',
  'common.language': 'Mutauro',
  'login.password': 'Pasiwedhi',
  // TODO native review: remaining strings intentionally fall back to English.
}

// TODO native review: all nd entries should be checked by native speakers.
export const nd: Catalog = {
  'nav.jobs': 'Imisebenzi',
  'nav.updates': 'Izibuyekezo',
  'common.login': 'Ngena',
  'common.logout': 'Phuma',
  'common.save': 'Londoloza',
  'common.language': 'Ulimi',
  'login.password': 'Iphasiwedi',
  // TODO native review: remaining strings intentionally fall back to English.
}

export const catalogs: Record<Lang, Catalog> = { en, sn, nd }
