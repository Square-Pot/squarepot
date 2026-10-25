// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect } from "react";
import type { Collection, FieldDefinition, FieldSchema, LabelTemplate } from "../api/types";
import { age, styled } from "../domain/names";
import { own, type Row } from "../domain/query";
import { sheetRowUrl } from "../domain/sheet";
import { useFormat } from "../format";
import { useI18n } from "../i18n";
import { navigate, onLinkClick } from "../router";
import { Icon, Name } from "./common";
import { LabelPreview } from "./LabelPreview";

interface Props {
  schema: FieldSchema;
  collection: Collection;
  templates: LabelTemplate[];
  row: Row;
  now: Date;
  /** The filtered, sorted list the card was opened from, for ← and →. */
  list: Row[];
  listHref: string;
  plantHref: (row: Row) => string;
}

export function PlantCard({ schema, collection, templates, row, now, list, listHref, plantHref }: Props) {
  const { t, label } = useI18n();
  const format = useFormat();
  const { plant } = row;
  const at = list.indexOf(row);
  const prev = at > 0 ? list[at - 1] : undefined;
  const next = at >= 0 ? list[at + 1] : undefined;
  const prevHref = prev ? plantHref(prev) : null;
  const nextHref = next ? plantHref(next) : null;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.target instanceof HTMLInputElement || event.metaKey || event.ctrlKey || event.altKey) return;
      if (event.key === "ArrowLeft" && prevHref) navigate(prevHref, { replace: true });
      else if (event.key === "ArrowRight" && nextHref) navigate(nextHref, { replace: true });
      else if (event.key === "Escape") navigate(listHref);
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, [prevHref, nextHref, listHref]);

  const value = (field: FieldDefinition) => {
    const raw = plant.fields[field.key];
    if (!raw) return null;
    if (field.type === "date") return format.date(raw);
    if (field.key === "price") return `${raw} ${plant.fields.currency ?? ""}`;
    const runs = styled(raw, field.display);
    return runs.map((run, i) => (run.italic ? <i key={i} className="nmv">{run.text}</i> : <span key={i}>{run.text}</span>));
  };

  const shown = schema.fields.filter((field) => field.key !== "tag" && field.key !== "currency");
  const groups: { title: string; fields: FieldDefinition[] }[] = [
    { title: t("Основное", "Basic"), fields: shown.filter((field) => field.group === "basic") },
    { title: t("Подробности", "Details"), fields: shown.filter((field) => field.group !== "basic") },
  ];
  const ageField = schema.computed.find((field) => field.key === "age");
  const plantAge = format.age(age(plant.fields, now));

  return (
    <div className="cardv">
      <div className="crumbs">
        <a className="btn ghost" href={listHref} onClick={(event) => { onLinkClick(event, listHref); }}>
          <Icon name="back" />
          {t("К списку", "Back to the list")}
        </a>
        <span className="nav">
          {at >= 0 && t(`${String(at + 1)} из ${String(list.length)}`, `${String(at + 1)} of ${String(list.length)}`)}
          <button className="btn sec" type="button" disabled={!prevHref} aria-label={t("Предыдущее", "Previous")} onClick={() => { if (prevHref) navigate(prevHref, { replace: true }); }}>
            <Icon name="left" />
          </button>
          <button className="btn sec" type="button" disabled={!nextHref} aria-label={t("Следующее", "Next")} onClick={() => { if (nextHref) navigate(nextHref, { replace: true }); }}>
            <Icon name="right" />
          </button>
        </span>
      </div>

      <div className="chead">
        <div className="tags">
          {plant.tag ? (
            <span>
              № <b>{plant.tag}</b>
            </span>
          ) : plant.invalid.tag ? (
            <span className="bad" title={plant.invalid.tag.reason}>
              {t(`Номер не прочитан: ${plant.invalid.tag.value}`, `Unreadable number: ${plant.invalid.tag.value}`)}
            </span>
          ) : (
            <span>{t("Номер не выдан", "No number yet")}</span>
          )}
          {plant.fields.field_number && <b>{plant.fields.field_number}</b>}
          <span>{t(`строка ${String(plant.row)}`, `row ${String(plant.row)}`)}</span>
        </div>
        <h2>
          <Name runs={row.name} />
        </h2>
        {plant.fields.ex && (
          <div className="ex">
            ex {plant.fields.ex}
            {plant.fields.locality ? ` · ${plant.fields.locality}` : ""}
          </div>
        )}
      </div>

      {!plant.tag && (
        <div className="banner quiet" role="note">
          <span className="bi">
            <Icon name="warn" size={18} />
          </span>
          <div>
            <b>{t("У растения нет номера", "This plant has no number")}</b>
            {t(
              "Камера его не узнает, и бирку напечатать нельзя. Номер выдаётся в таблице.",
              "The camera cannot recognise it and no label can be printed. Numbers are given in the sheet.",
            )}
          </div>
        </div>
      )}

      <div className="cgrid">
        <div className="side-main">
          {groups.map((group) => (
            <section key={group.title} className="blk">
              <h3>{group.title}</h3>
              <dl className="kv">
                {group.fields.map((field) => {
                  const shownValue = value(field);
                  const bad = plant.invalid[field.key];
                  return (
                    <div key={field.key}>
                      <dt>
                        {label(field.label)}
                        <span className="key">{field.key}</span>
                      </dt>
                      {bad ? (
                        <dd>
                          <span className="bad">{bad.value}</span>
                          <span className="cell">{bad.cell}</span>
                          <span className="why">
                            {bad.reason}. {t("Поле пока пустое.", "The field is left empty for now.")}
                          </span>
                        </dd>
                      ) : shownValue ? (
                        <dd>{shownValue}</dd>
                      ) : (
                        <dd className="e">{t("пусто", "empty")}</dd>
                      )}
                    </div>
                  );
                })}
                {group.fields.some((field) => field.key === "seeding_date") && ageField && (
                  <div>
                    <dt>
                      {label(ageField.label)}
                      <span className="key">{t("вычисляется", "computed")}</span>
                    </dt>
                    {plantAge ? <dd>{plantAge}</dd> : <dd className="e">{t("пусто", "empty")}</dd>}
                  </div>
                )}
              </dl>
            </section>
          ))}
          {collection.custom_columns.length > 0 && (
            <section className="blk">
              <h3>
                {t("Свои колонки", "Your columns")}
                <small>{t("из таблицы, как есть", "from the sheet, as they are")}</small>
              </h3>
              <dl className="kv">
                {collection.custom_columns.map((column) => (
                  <div key={column}>
                    <dt>{column}</dt>
                    {own(plant.custom, column) ? <dd>{own(plant.custom, column)}</dd> : <dd className="e">{t("пусто", "empty")}</dd>}
                  </div>
                ))}
              </dl>
            </section>
          )}
        </div>
        <div className="side">
          <LabelPreview plant={plant} templates={templates} />
          <div className="blk syncb">
            <h3>{t("Где в таблице", "Where in the sheet")}</h3>
            <div className="row">
              <span>{t("Коллекция", "Collection")}</span>
              <span>{collection.name}</span>
            </div>
            <div className="row">
              <span>{t("Строка", "Row")}</span>
              <span>{plant.row}</span>
            </div>
            <div className="row">
              <span>{t("Прочитана", "Read")}</span>
              <span>{collection.synced_at ? format.time(collection.synced_at) : "—"}</span>
            </div>
            {collection.sheet_url && (
              <a className="btn pri" href={sheetRowUrl(collection.sheet_url, plant.row)} target="_blank" rel="noopener noreferrer">
                <Icon name="ext" />
                {t("Открыть в таблице", "Open in the sheet")}
              </a>
            )}
            <p className="ro2">
              <Icon name="lock" size={13} /> {t("Только просмотр. Править — в этой строке таблицы.", "View only. Edit this row in the sheet.")}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
