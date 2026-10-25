// SPDX-License-Identifier: AGPL-3.0-or-later
import type { Collection } from "../api/types";
import { useFormat } from "../format";
import { useI18n } from "../i18n";
import { navigate, routePath } from "../router";
import { Icon } from "./common";

interface Props {
  collections: Collection[];
  current: Collection;
  plantCount: number;
  onForget: () => void;
}

export function Header({ collections, current, plantCount, onForget }: Props) {
  const { t, lang, plural, setLang } = useI18n();
  const format = useFormat();
  const synced = current.synced_at ? format.time(current.synced_at) : null;

  return (
    <>
      <header className="ah">
        <span className="brand">Square-Pot</span>
        <div className="coll">
          {collections.length > 1 ? (
            <select
              aria-label={t("Коллекция", "Collection")}
              value={current.id}
              onChange={(event) => {
                navigate(routePath({ page: "list", collection: event.target.value }));
              }}
            >
              {collections.map((collection) => (
                <option key={collection.id} value={collection.id}>
                  {collection.name}
                </option>
              ))}
            </select>
          ) : (
            <b>{current.name}</b>
          )}
          <span>
            {plantCount} {plural(plantCount, "растение", "растения", "растений", "plants")}
          </span>
        </div>
        <span
          className={current.error ? "sync warn" : "sync"}
          title={t("Сервер регулярно перечитывает таблицу", "The server rereads the sheet regularly")}
        >
          <span className="dot" />
          {current.error
            ? t(`Копия от ${synced ?? "—"}`, `Copy of ${synced ?? "—"}`)
            : synced
              ? t(`Таблица прочитана ${synced}`, `Sheet read ${synced}`)
              : t("Таблица ещё не прочитана", "Sheet not read yet")}
        </span>
        {current.sheet_url && (
          <a className="btn sec" href={current.sheet_url} target="_blank" rel="noopener noreferrer">
            <Icon name="ext" />
            <span className="tx">{t("Открыть таблицу", "Open the sheet")}</span>
          </a>
        )}
        <span className="hctl">
          <button
            className="btn ghost"
            type="button"
            onClick={() => {
              setLang(lang === "ru" ? "en" : "ru");
            }}
          >
            {lang === "ru" ? "EN" : "RU"}
          </button>
          <button className="btn ghost" type="button" onClick={onForget} title={t("Забыть токен в этом браузере", "Forget the token in this browser")}>
            <Icon name="key" />
            <span className="tx">{t("Выйти", "Sign out")}</span>
          </button>
        </span>
      </header>
      {current.error && (
        <div className="banner" role="status">
          <span className="bi">
            <Icon name="warn" size={18} />
          </span>
          <div>
            <b>{t("Сервер не может прочитать таблицу", "The server cannot read the sheet")}</b>
            {current.error}{" "}
            {t(
              "Ниже — последняя прочитанная копия; более поздние правки сюда не попали.",
              "Below is the last copy read; later edits are missing.",
            )}
          </div>
        </div>
      )}
    </>
  );
}
