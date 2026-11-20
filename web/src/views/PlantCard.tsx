// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from "react";
import { api, apiError } from "../api/client";
import type { Collection, FieldDefinition, FieldSchema, LabelTemplate, Plant } from "../api/types";
import { refresh } from "../data";
import { age, styled } from "../domain/names";
import { own, type Row } from "../domain/query";
import { sheetRowUrl } from "../domain/sheet";
import { useFormat } from "../format";
import { useI18n } from "../i18n";
import { navigate, onLinkClick } from "../router";
import { Icon, Name } from "./common";
import { LabelPreview } from "./LabelPreview";
import { Photos } from "./Photos";

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

      <Photos key={plant.tag ?? plant.id} schema={schema} plant={plant} />

      <div className="cgrid">
        <div className="side-main">
          {groups.map((group) => {
            // Empty fields stay off the card; broken values stay visible. A
            // group with nothing to show goes entirely.
            const visible = group.fields.filter((field) => value(field) || plant.invalid[field.key]);
            const hasSeeding = group.fields.some((field) => field.key === "seeding_date");
            if (!visible.length && !(hasSeeding && ageField && plantAge)) return null;
            return (
              <section key={group.title} className="blk">
                <h3>{group.title}</h3>
                <dl className="kv">
                  {visible.map((field) => {
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
                        ) : (
                          <dd>{shownValue}</dd>
                        )}
                      </div>
                    );
                  })}
                  {hasSeeding && ageField && plantAge && (
                    <div>
                      <dt>
                        {label(ageField.label)}
                        <span className="key">{t("вычисляется", "computed")}</span>
                      </dt>
                      <dd>{plantAge}</dd>
                    </div>
                  )}
                </dl>
              </section>
            );
          })}
          {collection.custom_columns.some((column) => own(plant.custom, column)) && (
            <section className="blk">
              <h3>
                {t("Свои колонки", "Your columns")}
                <small>{t("из таблицы, как есть", "from the sheet, as they are")}</small>
              </h3>
              <dl className="kv">
                {collection.custom_columns.filter((column) => own(plant.custom, column)).map((column) => (
                  <div key={column}>
                    <dt>{column}</dt>
                    <dd>{own(plant.custom, column)}</dd>
                  </div>
                ))}
              </dl>
            </section>
          )}
        </div>
        <div className="side">
          <LabelPreview plant={plant} templates={templates} />
          {collection.editable && <StatusBlock schema={schema} collection={collection} plant={plant} />}
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
              <Icon name="lock" size={13} /> {t("Остальное правится в этой строке таблицы.", "Everything else is edited in this row of the sheet.")}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}

/** The status of a plant and its change: gone or back, with an optional date
 * and one comment, written through the collection's bulk status endpoint
 * (ADR 0009). The living state is never displayed. */
function StatusBlock({ schema, collection, plant }: { schema: FieldSchema; collection: Collection; plant: Plant }) {
  const { t, label } = useI18n();
  const format = useFormat();
  const [editing, setEditing] = useState<null | "gone" | "back">(null);
  const [date, setDate] = useState("");
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ bad: boolean; text: string } | null>(null);

  const gone = plant.status === "gone";
  const statusField = schema.fields.find((field) => field.key === "status");
  const dateField = schema.fields.find((field) => field.key === "status_date");
  const commentField = schema.fields.find((field) => field.key === "status_comment");
  const goneValue = statusField?.values?.find((value) => value.key === "0");
  const statusText = goneValue ? label(goneValue.label) : t("Выбыло", "Gone");

  const start = (which: "gone" | "back") => {
    setEditing(which);
    setDate("");
    setComment("");
    setNote(null);
  };

  const apply = async () => {
    if (!editing) return;
    setBusy(true);
    setNote(null);
    const which = editing;
    try {
      const response = await api.POST("/api/v1/collections/{collection_id}/status", {
        params: { path: { collection_id: collection.id } },
        body: {
          status: which === "gone" ? "gone" : null,
          status_date: date || null,
          comment: comment.trim() || null,
          plants: [{ id: plant.id, seen: plant.status }],
        },
      });
      if (!response.data) throw apiError(response.response, response.error);
      const result = response.data.find((item) => item.id === plant.id)?.result;
      if (result === "written") {
        setEditing(null);
        setNote({
          bad: false,
          text: which === "gone" ? t("Статус записан в таблицу.", "The status is written to the sheet.") : t("Растение вернулось в коллекцию.", "The plant is back in the collection."),
        });
        await refresh();
      } else if (result === "changed_in_sheet") {
        setEditing(null);
        setNote({
          bad: true,
          text: t("Ячейка статуса в таблице уже другая: ничего не записано, показываем свежую копию.", "The status cell in the sheet already changed: nothing was written; showing the fresh copy."),
        });
        await refresh();
      } else {
        setEditing(null);
        setNote({ bad: true, text: t("Этого растения больше нет в таблице.", "This plant is no longer in the sheet.") });
        await refresh();
      }
    } catch (error) {
      setNote({ bad: true, text: error instanceof Error ? error.message : String(error) });
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="blk syncb" aria-label={t("Статус", "Status")}>
      <h3>{t("Статус", "Status")}</h3>
      {gone ? (
        <>
          <div className="row">
            <span>{statusField ? label(statusField.label) : t("Статус", "Status")}</span>
            <span>{statusText}</span>
          </div>
          {plant.status_since && (
            <div className="row">
              <span>{dateField ? label(dateField.label) : t("Дата", "Date")}</span>
              <span>{format.date(plant.status_since)}</span>
            </div>
          )}
          {plant.status_comment && (
            <div className="row">
              <span>{commentField ? label(commentField.label) : t("Комментарий", "Comment")}</span>
              <span>{plant.status_comment}</span>
            </div>
          )}
          {editing === null && (
            <button className="btn sec" type="button" onClick={() => { start("back"); }}>
              {t("Вернуть в коллекцию", "Return to the collection")}
            </button>
          )}
        </>
      ) : editing === null ? (
        <button className="btn sec" type="button" onClick={() => { start("gone"); }}>
          {t("Отметить как выбывшее", "Mark as gone")}
        </button>
      ) : null}
      {editing && (
        <div className="sform">
          <label>
            <span>{dateField ? label(dateField.label) : t("Дата изменения", "Date of the change")}</span>
            <input type="date" value={date} onChange={(event) => { setDate(event.target.value); }} />
          </label>
          <p className="ro2">{t("Пусто — запишется сегодняшний день.", "Empty writes the server's day.")}</p>
          <label>
            <span>{commentField ? label(commentField.label) : t("Комментарий", "Comment")}</span>
            <input
              type="text"
              value={comment}
              maxLength={200}
              placeholder={editing === "gone" ? t("зачем ушло: продано, погибло…", "why it left: sold, died…") : t("откуда вернулось…", "where it came back from…")}
              onChange={(event) => { setComment(event.target.value); }}
            />
          </label>
          <div className="acts">
            <button className="btn pri" type="button" disabled={busy} onClick={() => { void apply(); }}>
              {editing === "gone" ? t("Отметить выбывшим", "Mark as gone") : t("Вернуть", "Return")}
            </button>
            <button className="btn ghost" type="button" disabled={busy} onClick={() => { setEditing(null); }}>
              {t("Отмена", "Cancel")}
            </button>
          </div>
        </div>
      )}
      {note && <p className={note.bad ? "bad" : "ro2"}>{note.text}</p>}
    </section>
  );
}
