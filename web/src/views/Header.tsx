// SPDX-License-Identifier: AGPL-3.0-or-later
import { useState } from "react";
import type { Collection } from "../api/types";
import { isTag } from "../domain/datamatrix";
import { isFormer, type Row } from "../domain/query";
import { useFormat } from "../format";
import { useI18n } from "../i18n";
import { navigate, routePath } from "../router";
import { Icon } from "./common";
import { HeaderTag } from "./HeaderTag";

interface Props {
  collections: Collection[];
  current: Collection;
  rows: Row[];
  onForget: () => void;
}

export function Header({ collections, current, rows, onForget }: Props) {
  const { t, lang, plural, setLang } = useI18n();
  const format = useFormat();
  const synced = current.synced_at ? format.time(current.synced_at) : null;
  // The header label shows one random numbered plant of the collection; the
  // pick is made once per page load, and again when the collection changes
  // (the component is keyed by the collection). The picked plant is re-found
  // in fresh rows, and the label goes when the plant is gone from the sheet.
  const [pickedId] = useState<string | null>(() => {
    const pool = rows.filter((row) => isTag(row.plant.tag) && row.nameText);
    return pool[Math.floor(Math.random() * pool.length)]?.plant.id ?? null;
  });
  const tagRow = rows.find((row) => row.plant.id === pickedId) ?? null;
  const plantCount = rows.filter((row) => !isFormer(row)).length;

  return (
    <>
      <header className="ah">
        <span className="brandline">
          {tagRow && tagRow.plant.tag && <HeaderTag tag={tagRow.plant.tag} name={tagRow.name} />}
          <div className="coll">
            <b>SquarePot</b>
            <span className="cline">
              {collections.length > 1 && (
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
              )}
              <span>
                {plantCount} {plural(plantCount, "растение", "растения", "растений", "plants")}
              </span>
            </span>
          </div>
        </span>
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
