// SPDX-License-Identifier: AGPL-3.0-or-later
// Dates, ages and times in the reader's language.
import { useI18n } from "./i18n";

export function useFormat() {
  const { lang, t, plural } = useI18n();
  return {
    date: (iso: string | undefined): string => {
      if (!iso) return "";
      const [year, month, day] = iso.split("-");
      return lang === "ru" ? `${day ?? ""}.${month ?? ""}.${year ?? ""}` : iso;
    },
    age: (value: { months: number } | { years: number } | null): string => {
      if (!value) return "";
      if ("months" in value) return t(`${String(value.months)} мес.`, `${String(value.months)} mo`);
      const n = value.years;
      return `${String(n)} ${plural(n, "год", "года", "лет", "yr")}`;
    },
    time: (iso: string): string =>
      new Date(iso).toLocaleString(lang, { hour: "2-digit", minute: "2-digit", day: "numeric", month: "short" }),
  };
}
