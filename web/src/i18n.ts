// SPDX-License-Identifier: AGPL-3.0-or-later
// Russian and English. Each text is written in both where it is used: `t("…", "…")`.
import { createContext, useContext } from "react";
import type { LocalizedLabel } from "./api/types";

export type Lang = "ru" | "en";

const KEY = "squarepot.lang";

export function initialLang(): Lang {
  try {
    const saved = localStorage.getItem(KEY);
    if (saved === "ru" || saved === "en") return saved;
  } catch {
    // No storage: follow the browser.
  }
  return navigator.language.toLowerCase().startsWith("ru") ? "ru" : "en";
}

export function saveLang(lang: Lang): void {
  try {
    localStorage.setItem(KEY, lang);
  } catch {
    // Kept for this visit only.
  }
  document.documentElement.lang = lang;
}

export interface I18n {
  lang: Lang;
  t: (ru: string, en: string) => string;
  label: (label: LocalizedLabel) => string;
  plural: (n: number, one: string, few: string, many: string, en: string) => string;
  setLang: (lang: Lang) => void;
}

export function makeI18n(lang: Lang, setLang: (lang: Lang) => void): I18n {
  return {
    lang,
    t: (ru, en) => (lang === "ru" ? ru : en),
    label: (label) => label[lang],
    plural: (n, one, few, many, en) => {
      if (lang === "en") return en;
      const [ten, hundred] = [n % 10, n % 100];
      if (ten === 1 && hundred !== 11) return one;
      if (ten >= 2 && ten <= 4 && (hundred < 10 || hundred >= 20)) return few;
      return many;
    },
    setLang,
  };
}

export const I18nContext = createContext<I18n>(makeI18n("ru", () => undefined));
export const useI18n = (): I18n => useContext(I18nContext);
