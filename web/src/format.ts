// SPDX-License-Identifier: AGPL-3.0-or-later
// Dates, ages and times in the reader's language.
import { localDay } from "./domain/photos";
import { useI18n } from "./i18n";

export function useFormat() {
  const { lang, t, plural } = useI18n();
  const date = (iso: string | undefined): string => {
    if (!iso) return "";
    const [year, month, day] = iso.split("-");
    return lang === "ru" ? `${day ?? ""}.${month ?? ""}.${year ?? ""}` : iso;
  };
  return {
    date,
    /** The local day of a time, as `date` shows it. */
    day: (iso: string | null | undefined): string => (iso ? date(localDay(iso)) : ""),
    /** A span in months, to the month: «2 года 3 мес.». */
    span: (months: number): string => {
      if (months < 1) return t("меньше месяца", "under a month");
      if (months < 12) return t(`${String(months)} мес.`, `${String(months)} mo`);
      const [years, rest] = [Math.floor(months / 12), months % 12];
      const ru = `${String(years)} ${plural(years, "год", "года", "лет", "")}${rest ? ` ${String(rest)} мес.` : ""}`;
      return t(ru, `${String(years)} yr${rest ? ` ${String(rest)} mo` : ""}`);
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
