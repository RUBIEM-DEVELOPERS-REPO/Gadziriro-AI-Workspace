// Tiny in-house i18n layer (FR-44): React context + useT() hook. No deps.
import {
  createContext,
  createElement,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import { catalogs, type Lang } from './catalogs.ts'

export { LANGS, type Lang } from './catalogs.ts'

const STORAGE_KEY = 'gadziriro.lang'

function isLang(v: unknown): v is Lang {
  return v === 'en' || v === 'sn' || v === 'nd'
}

function loadLang(): Lang {
  try {
    const v = localStorage.getItem(STORAGE_KEY)
    if (isLang(v)) return v
  } catch {
    // storage unavailable; use default
  }
  return 'en'
}

export type TFn = (key: string, fallback?: string) => string

interface I18nValue {
  lang: Lang
  setLang: (l: Lang) => void
  t: TFn
}

const I18nContext = createContext<I18nValue>({
  lang: 'en',
  setLang: () => undefined,
  t: (key, fallback) => catalogs.en[key] ?? fallback ?? key,
})

export function I18nProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<Lang>(loadLang)

  const setLang = useCallback((l: Lang) => {
    setLangState(l)
    try {
      localStorage.setItem(STORAGE_KEY, l)
    } catch {
      // ignore persistence failure
    }
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const value = useMemo<I18nValue>(
    () => ({
      lang,
      setLang,
      t: (key, fallback) =>
        catalogs[lang][key] ?? catalogs.en[key] ?? fallback ?? key,
    }),
    [lang, setLang],
  )

  return createElement(I18nContext.Provider, { value }, children)
}

export function useT(): I18nValue {
  return useContext(I18nContext)
}
