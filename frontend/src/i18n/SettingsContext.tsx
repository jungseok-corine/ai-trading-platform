import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import { translations, type Language, type Translations } from "./translations";

export type Timezone = "Asia/Seoul" | "Asia/Bangkok" | "UTC";

const LANGUAGE_STORAGE_KEY = "settings.language";
const TIMEZONE_STORAGE_KEY = "settings.timezone";
const ACCOUNT_ID_STORAGE_KEY = "settings.accountId";

const DEFAULT_LANGUAGE: Language = "ko";
const DEFAULT_TIMEZONE: Timezone = "Asia/Seoul";
const DEFAULT_ACCOUNT_ID = 1;

function loadStoredLanguage(): Language {
  try {
    const stored = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
    if (stored === "ko" || stored === "en") return stored;
  } catch {
    // localStorage 접근 불가 시 기본값 사용
  }
  return DEFAULT_LANGUAGE;
}

function loadStoredTimezone(): Timezone {
  try {
    const stored = window.localStorage.getItem(TIMEZONE_STORAGE_KEY);
    if (stored === "Asia/Seoul" || stored === "Asia/Bangkok" || stored === "UTC") return stored;
  } catch {
    // localStorage 접근 불가 시 기본값 사용
  }
  return DEFAULT_TIMEZONE;
}

function loadStoredAccountId(): number {
  try {
    const stored = window.localStorage.getItem(ACCOUNT_ID_STORAGE_KEY);
    if (stored && /^\d+$/.test(stored) && Number(stored) > 0) return Number(stored);
  } catch {
    // localStorage 접근 불가 시 기본값 사용
  }
  return DEFAULT_ACCOUNT_ID;
}

interface SettingsContextValue {
  language: Language;
  setLanguage: (language: Language) => void;
  timezone: Timezone;
  setTimezone: (timezone: Timezone) => void;
  accountId: number;
  setAccountId: (accountId: number) => void;
  t: Translations;
  formatDateTime: (value: string | null | undefined) => string;
}

const SettingsContext = createContext<SettingsContextValue | null>(null);

const DATE_TIME_FORMATTER_CACHE = new Map<Timezone, Intl.DateTimeFormat>();

function getFormatter(timezone: Timezone): Intl.DateTimeFormat {
  let formatter = DATE_TIME_FORMATTER_CACHE.get(timezone);
  if (!formatter) {
    formatter = new Intl.DateTimeFormat("ko-KR", {
      timeZone: timezone,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    });
    DATE_TIME_FORMATTER_CACHE.set(timezone, formatter);
  }
  return formatter;
}

export function SettingsProvider({ children }: { children: ReactNode }) {
  const [language, setLanguageState] = useState<Language>(loadStoredLanguage);
  const [timezone, setTimezoneState] = useState<Timezone>(loadStoredTimezone);
  const [accountId, setAccountIdState] = useState<number>(loadStoredAccountId);

  useEffect(() => {
    try {
      window.localStorage.setItem(LANGUAGE_STORAGE_KEY, language);
    } catch {
      // localStorage 접근 불가 시 무시
    }
  }, [language]);

  useEffect(() => {
    try {
      window.localStorage.setItem(TIMEZONE_STORAGE_KEY, timezone);
    } catch {
      // localStorage 접근 불가 시 무시
    }
  }, [timezone]);

  useEffect(() => {
    try {
      window.localStorage.setItem(ACCOUNT_ID_STORAGE_KEY, String(accountId));
    } catch {
      // localStorage 접근 불가 시 무시
    }
  }, [accountId]);

  const value = useMemo<SettingsContextValue>(() => {
    const formatDateTime = (value: string | null | undefined): string => {
      if (!value) return "-";
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) return value;
      const formatted = getFormatter(timezone).format(date);
      return timezone === "UTC" ? `${formatted} UTC` : formatted;
    };

    return {
      language,
      setLanguage: setLanguageState,
      timezone,
      setTimezone: setTimezoneState,
      accountId,
      setAccountId: setAccountIdState,
      t: translations[language],
      formatDateTime,
    };
  }, [language, timezone, accountId]);

  return <SettingsContext.Provider value={value}>{children}</SettingsContext.Provider>;
}

export function useSettings(): SettingsContextValue {
  const context = useContext(SettingsContext);
  if (!context) {
    throw new Error("useSettings must be used within a SettingsProvider");
  }
  return context;
}
