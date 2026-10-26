// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState, type MouseEvent } from "react";
import { api, apiError } from "../api/client";
import type { Collection, FieldSchema, LabelTemplate } from "../api/types";
import {
  clampSkip,
  cleanFields,
  defaultFields,
  defaultKind,
  grid,
  MAX_PLANTS,
  pageCount,
  pageOf,
  pageSize,
  parseIdList,
  printableFields,
  printOrder,
  slotAt,
  toEntries,
  wantedKind,
  type Kind,
  type LabelFields,
  type Order,
} from "../domain/print";
import { own, type ListState, type Row } from "../domain/query";
import { useI18n, type Lang } from "../i18n";
import { onLinkClick } from "../router";
import { Icon, Name } from "./common";

const PAGE = 100;

interface Props {
  schema: FieldSchema;
  collection: Collection;
  templates: LabelTemplate[];
  rows: Row[];
  /** The plants the picker's search and filters find, in the list's order. */
  found: Row[];
  state: ListState;
  onState: (next: ListState) => void;
  listHref: string;
}

const storageKey = (collection: string, kind: Kind) => `squarepot.print.${collection}.${kind}`;

function loadFields(collection: string, kind: Kind, allowed: string[], fallback: LabelFields): LabelFields {
  try {
    return cleanFields(JSON.parse(localStorage.getItem(storageKey(collection, kind)) ?? "null"), allowed, fallback);
  } catch {
    return fallback;
  }
}

function saveFields(collection: string, kind: Kind, fields: LabelFields): void {
  try {
    localStorage.setItem(storageKey(collection, kind), JSON.stringify(fields));
  } catch {
    // Kept for this visit only.
  }
}

interface Preview {
  key: string;
  url: string | null;
  pages: number;
  /** Plants whose caption or burial text the server cut short, on any page. */
  cut: string[];
  error: string | null;
}

export function PrintView({ schema, collection, templates, rows, found, state, onState, listHref }: Props) {
  const { t, lang, label, plural } = useI18n();
  const [selected, setSelected] = useState<Set<string>>(() => new Set());
  const [later, setLater] = useState<{ ids: string[]; kind: Kind } | null>(null);
  const [chosenKind, setChosenKind] = useState<Kind | null>(null);
  const [order, setOrder] = useState<Order>("list");
  // Places the owner chose to leave empty; held to what a page of the current type has.
  const [wantedSkip, setSkip] = useState(0);
  const [page, setPage] = useState(1);
  const [fieldLang, setFieldLang] = useState<Lang>(lang);
  const [shown, setShown] = useState(PAGE);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [downloading, setDownloading] = useState(false);
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const allowed = ["name", ...printableFields(schema), ...collection.custom_columns.map((column) => `c:${column}`)];
  // Selected plants in the list's order, whatever the picker shows now.
  const listOrder = new Map(found.map((row, i) => [row.plant.id, i]));
  const chosenRows = rows
    .filter((row) => selected.has(row.plant.id) && row.plant.tag)
    .sort((a, b) => (listOrder.get(a.plant.id) ?? Infinity) - (listOrder.get(b.plant.id) ?? Infinity) || a.plant.row - b.plant.row);
  const kind = chosenKind ?? defaultKind(chosenRows);
  const template = templates.find((item) => item.key === kind);
  const [fieldsByKind, setFieldsByKind] = useState<Partial<Record<Kind, LabelFields>>>({});
  const fields = fieldsByKind[kind] ?? loadFields(collection.id, kind, allowed, defaultFields(schema, kind));
  const setFields = (next: LabelFields) => {
    setFieldsByKind({ ...fieldsByKind, [kind]: next });
    saveFields(collection.id, kind, next);
  };

  const printed = printOrder(chosenRows, order);
  const others = printed.filter((row) => wantedKind(row) !== kind);
  const layout = template?.layout;
  const perPage = layout ? grid(layout).perPage : 0;
  const skip = clampSkip(wantedSkip, perPage);
  const pages = pageCount(printed.length, skip, perPage);
  const shownPage = Math.min(page, pages);
  const tooMany = printed.length > MAX_PLANTS;
  const untaggedFound = found.filter((row) => !row.plant.tag);

  const body = template && printed.length && !tooMany
    ? {
        plants: printed.map((row) => row.plant.id),
        template: template.key,
        caption_fields: toEntries(fields.caption),
        extra_fields: toEntries(fields.extra),
        language: fieldLang,
        skip,
      }
    : null;
  const previewKey = body ? JSON.stringify({ ...body, page: shownPage }) : "";

  useEffect(() => {
    if (!body) return;
    const abort = new AbortController();
    let url: string | null = null;
    // Wait for a pause in clicking before asking the server.
    const timer = setTimeout(() => {
      void api
        .POST("/api/v1/labels", { body: { ...body, format: "svg", page: shownPage }, parseAs: "text", signal: abort.signal })
        .then(({ data, error, response }) => {
          if (data === undefined) throw apiError(response, error);
          url = URL.createObjectURL(new Blob([data], { type: "image/svg+xml" }));
          const count = Number(response.headers.get("X-Page-Count") ?? "1");
          const cut = parseIdList(response.headers.get("X-Cut-Captions"));
          setPreview({ key: previewKey, url, pages: count, cut, error: null });
        })
        .catch((error: unknown) => {
          if (abort.signal.aborted) return;
          setPreview({ key: previewKey, url: null, pages: 1, cut: [], error: error instanceof Error ? error.message : String(error) });
        });
    }, 250);
    return () => {
      clearTimeout(timer);
      abort.abort();
      if (url) URL.revokeObjectURL(url);
    };
    // The key holds everything the request is made of.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey]);
  const current = preview?.key === previewKey ? preview : null;
  const cutIds = new Set(current?.cut ?? []);
  const cutRows = printed.filter((row) => cutIds.has(row.plant.id));

  const download = () => {
    if (!body) return;
    setDownloading(true);
    setDownloadError(null);
    void api
      .POST("/api/v1/labels", { body: { ...body, format: "pdf" }, parseAs: "blob" })
      .then(({ data, error, response }) => {
        // The contract calls the PDF a string; with parseAs "blob" it is a Blob.
        const pdf: unknown = data;
        if (!(pdf instanceof Blob)) throw apiError(response, error);
        const url = URL.createObjectURL(pdf);
        const link = document.createElement("a");
        link.href = url;
        link.download = `labels-${collection.id}-${new Date().toISOString().slice(0, 10)}.pdf`;
        link.click();
        setTimeout(() => {
          URL.revokeObjectURL(url);
        }, 10_000);
      })
      .catch((error: unknown) => {
        setDownloadError(error instanceof Error ? error.message : String(error));
      })
      .finally(() => {
        setDownloading(false);
      });
  };

  const toggle = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };
  const selectAllFound = () => {
    setSelected(new Set([...selected, ...found.filter((row) => row.plant.tag).map((row) => row.plant.id)]));
  };
  const printOthersLater = () => {
    const ids = new Set(others.map((row) => row.plant.id));
    setLater({ ids: [...ids], kind: kind === "vertical" ? "horizontal" : "vertical" });
    setSelected(new Set([...selected].filter((id) => !ids.has(id))));
    setChosenKind(kind);
  };
  const printLaterNow = () => {
    if (!later) return;
    setSelected(new Set(later.ids));
    setChosenKind(later.kind);
    setLater(null);
    setSkip(0);
    setPage(1);
  };

  const onSheetClick = (event: MouseEvent<HTMLImageElement>) => {
    if (!layout || shownPage !== 1) return;
    const box = event.currentTarget.getBoundingClientRect();
    const [width, height] = pageSize(layout);
    const slot = slotAt(layout, ((event.clientX - box.left) / box.width) * width, ((event.clientY - box.top) / box.height) * height);
    if (slot !== null) setSkip(slot);
  };

  const fieldLabel = (key: string): string => {
    if (key.startsWith("c:")) return key.slice(2);
    const field = schema.fields.find((item) => item.key === key) ?? schema.computed.find((item) => item.key === key);
    return field ? label(field.label) : key;
  };
  const genera = [...new Set(rows.map((row) => row.genus).filter(Boolean))].sort((a, b) => a.localeCompare(b));
  const [customColumn, customValues] = Object.entries(state.custom)[0] ?? ["", []];
  const columnValues = customColumn
    ? [...new Set(rows.map((row) => own(row.plant.custom, customColumn)?.trim() ?? ""))].sort((a, b) =>
        a === "" ? 1 : b === "" ? -1 : a.localeCompare(b),
      )
    : [];
  const selectedFound = found.filter((row) => selected.has(row.plant.id)).length;

  return (
    <div className="print">
      <div className="panes">
        <section className="pane left" aria-label={t("Растения", "Plants")}>
          <div className="ph">
            <h2>{t("Растения", "Plants")}</h2>
            <a className="btn ghost" href={listHref} onClick={(event) => { onLinkClick(event, listHref); }}>
              <Icon name="back" />
              {t("К списку", "Back to the list")}
            </a>
          </div>
          <div className="tools">
            <label className="search">
              <Icon name="search" size={16} />
              <input
                type="search"
                value={state.q}
                onChange={(event) => { onState({ ...state, q: event.target.value }); }}
                placeholder={t("Номер, название, полевой номер", "Number, name, field number")}
                aria-label={t("Поиск", "Search")}
                autoComplete="off"
              />
            </label>
            <select
              aria-label={t("Род", "Genus")}
              value={state.genus.length === 1 ? (state.genus[0] ?? "") : ""}
              onChange={(event) => { onState({ ...state, genus: event.target.value ? [event.target.value] : [] }); }}
            >
              <option value="">{state.genus.length > 1 ? t(`Родов: ${String(state.genus.length)}`, `${String(state.genus.length)} genera`) : t("Все роды", "All genera")}</option>
              {genera.map((genus) => (
                <option key={genus} value={genus}>
                  {genus}
                </option>
              ))}
            </select>
          </div>
          {collection.custom_columns.length > 0 && (
            <div className="tools">
              <select
                aria-label={t("Своя колонка", "Your column")}
                value={customColumn}
                onChange={(event) => { onState({ ...state, custom: event.target.value ? { [event.target.value]: [] } : {} }); }}
              >
                <option value="">{t("Своя колонка: любая", "Your column: any")}</option>
                {collection.custom_columns.map((column) => (
                  <option key={column} value={column}>
                    {column}
                  </option>
                ))}
              </select>
              {customColumn && (
                <select
                  aria-label={t("Значение", "Value")}
                  value={customValues.length === 1 ? `=${customValues[0] ?? ""}` : ""}
                  onChange={(event) => {
                    const value = event.target.value;
                    onState({ ...state, custom: { [customColumn]: value ? [value.slice(1)] : [] } });
                  }}
                >
                  <option value="">{t("любое значение", "any value")}</option>
                  {columnValues.map((value) => (
                    <option key={value} value={`=${value}`}>
                      {value || t("пусто", "empty")}
                    </option>
                  ))}
                </select>
              )}
            </div>
          )}
          <div className="selall">
            <span>
              {t("Найдено ", "")}
              <b>{found.length}</b>
              {t(", выбрано из них ", " found, ")}
              <b>{selectedFound}</b>
              {t("", " of them selected")}
            </span>
            <span className="sp" />
            <button className="more" type="button" onClick={selectAllFound} disabled={!found.some((row) => row.plant.tag)}>
              {t(`Выбрать все найденные (${String(found.filter((row) => row.plant.tag).length)})`, `Select all found (${String(found.filter((row) => row.plant.tag).length)})`)}
            </button>
            {selected.size > 0 && (
              <button className="more" type="button" onClick={() => { setSelected(new Set()); }}>
                {t("Снять выбор", "Clear the selection")}
              </button>
            )}
          </div>
          {found.length ? (
            <div className="plist">
              {found.slice(0, shown).map((row) => {
                const disabled = !row.plant.tag;
                const on = !disabled && selected.has(row.plant.id);
                return (
                  <label key={row.plant.id} className={`prow${on ? " on" : ""}${disabled ? " dis" : ""}`}>
                    <input type="checkbox" checked={on} disabled={disabled} onChange={() => { toggle(row.plant.id); }} />
                    <span className="num">{row.plant.tag ?? "——"}</span>
                    <span className="nm">
                      <Name runs={row.name} />
                      <small>
                        {[row.plant.fields.field_number, row.plant.fields.ex ? `ex ${row.plant.fields.ex}` : ""].filter(Boolean).join(" · ")}
                        {disabled && <span className="why"> · {t("нет номера — не печатается", "no number, cannot print")}</span>}
                      </small>
                    </span>
                    {wantedKind(row) === "horizontal" ? <span className="ltag" title="label_type = h">h</span> : <span />}
                  </label>
                );
              })}
              {found.length > shown && (
                <button className="more" type="button" onClick={() => { setShown(shown + PAGE); }}>
                  {t(`Показать ещё (${String(found.length - shown)})`, `Show more (${String(found.length - shown)})`)}
                </button>
              )}
            </div>
          ) : (
            <div className="empty">
              <p>{t("Ничего не нашлось. Уточните поиск или фильтры.", "Nothing found. Change the search or the filters.")}</p>
            </div>
          )}
        </section>

        <section className="pane right" aria-label={t("Лист", "Sheet")}>
          <div className="ph">
            <h2>{t("Лист", "Sheet")}</h2>
            {perPage > 0 && <span className="n">{t(`${String(perPage)} бирок на листе`, `${String(perPage)} labels a sheet`)}</span>}
          </div>
          <p className="fttl">{t("Тип бирки — на весь лист", "Label type, for the whole sheet")}</p>
          <div className="typecards">
            {templates
              .filter((item): item is LabelTemplate & { key: Kind } => item.key === "vertical" || item.key === "horizontal")
              .map((item) => (
                <button
                  key={item.key}
                  type="button"
                  className={item.key === kind ? "tcard on" : "tcard"}
                  aria-pressed={item.key === kind}
                  onClick={() => {
                    setChosenKind(item.key);
                    setSkip(0);
                    setPage(1);
                  }}
                >
                  <b>{label(item.label)}</b>
                  <span>
                    {item.layout.width_mm}×{item.layout.height_mm} {t("мм", "mm")} · {t(`${String(grid(item.layout).perPage)} на листе`, `${String(grid(item.layout).perPage)} a sheet`)}
                  </span>
                </button>
              ))}
          </div>
          {others.length > 0 && (
            <div className="hint">
              <span className="hi">
                <Icon name="warn" size={16} />
              </span>
              <div>
                {kind === "vertical"
                  ? t(
                      `У ${String(others.length)} из ${String(printed.length)} выбранных в таблице label_type = h. На этом листе они будут вертикальными.`,
                      `${String(others.length)} of the ${String(printed.length)} selected have label_type = h in the sheet. On this sheet they print vertical.`,
                    )
                  : t(
                      `У ${String(others.length)} из ${String(printed.length)} выбранных тип в таблице не горизонтальный. На этом листе они будут горизонтальными.`,
                      `${String(others.length)} of the ${String(printed.length)} selected are not horizontal in the sheet. On this sheet they print horizontal.`,
                    )}
                <div className="acts">
                  <button className="btn sec" type="button" onClick={printOthersLater}>
                    {t("Убрать их и напечатать отдельно", "Take them out and print them separately")}
                  </button>
                </div>
              </div>
            </div>
          )}
          {later && (
            <div className="hint">
              <span className="hi">
                <Icon name="up" size={16} />
              </span>
              <div>
                {t(
                  `Отложено ${String(later.ids.length)} ${plural(later.ids.length, "растение", "растения", "растений", "")} для ${later.kind === "horizontal" ? "горизонтальных" : "вертикальных"} бирок.`,
                  `${String(later.ids.length)} plants wait for ${later.kind} labels.`,
                )}
                <div className="acts">
                  <button className="btn sec" type="button" onClick={printLaterNow}>
                    {t("Перейти к ним", "Go to them")}
                  </button>
                </div>
              </div>
            </div>
          )}

          <p className="fttl">{t("Подпись", "Caption")}</p>
          <FieldList keys={fields.caption} lockName allowed={allowed} label={fieldLabel} onChange={(caption) => { setFields({ ...fields, caption }); }} />
          <p className="fnote">
            {t("Название обязательно. Свои колонки печатаются как «Колонка: значение».", "The name is required. Your columns print as «Column: value».")}
          </p>
          <p className="fttl">{layout?.burial_text ? t("Зона в грунте", "Burial zone") : t("Дополнительно, после подписи", "Extra, after the caption")}</p>
          <FieldList keys={fields.extra} lockName={false} allowed={allowed.filter((key) => key !== "name")} label={fieldLabel} onChange={(extra) => { setFields({ ...fields, extra }); }} />
          <p className="fnote">
            {layout?.burial_text
              ? t("Каждое поле — строкой «Поле: значение»; что не влезет, обрежется.", "Each field on its own line, «Field: value»; what does not fit is cut.")
              : t("Печатается мельче, если после подписи осталось место; обрезается первым.", "Printed smaller when the caption leaves room; cut first.")}
          </p>

          {cutRows.length > 0 && (
            <div className="hint" role="status">
              <span className="hi">
                <Icon name="warn" size={16} />
              </span>
              <div>
                {t(
                  `На ${String(cutRows.length)} ${cutRows.length === 1 ? "бирке" : "бирках"} текст не влез и обрезан «…»: `,
                  `On ${String(cutRows.length)} label${cutRows.length === 1 ? "" : "s"} the text does not fit and is cut with «…»: `,
                )}
                {cutRows.slice(0, 5).map((row, i) => (
                  <span key={row.plant.id}>
                    {i > 0 && ", "}
                    <button
                      className="more"
                      type="button"
                      title={t("Показать лист с этой биркой", "Show the sheet with this label")}
                      onClick={() => { setPage(pageOf(printed.indexOf(row), skip, perPage)); }}
                    >
                      {row.plant.tag}
                    </button>
                  </span>
                ))}
                {cutRows.length > 5 && " …"}
                {". "}
                {kind === "vertical"
                  ? t("Уберите поле или выберите горизонтальную бирку.", "Remove a field or pick the horizontal label.")
                  : t("Уберите поле.", "Remove a field.")}
              </div>
            </div>
          )}

          <details className="more2">
            <summary>{t("Лист и порядок", "Sheet and order")}</summary>
            <div className="in">
              <div className="row2">
                <span>{t("Порядок", "Order")}</span>
                {(["list", "tag"] as const).map((value) => (
                  <label key={value}>
                    <input type="radio" name="order" checked={order === value} onChange={() => { setOrder(value); }} />
                    {value === "list" ? t("как в списке", "as in the list") : t("по номеру", "by number")}
                  </label>
                ))}
              </div>
              <div className="row2">
                <span>{t("Пропустить первые места", "Skip the first places")}</span>
                <span className="step">
                  <button type="button" aria-label={t("Меньше", "Fewer")} disabled={skip === 0} onClick={() => { setSkip(skip - 1); }}>
                    −
                  </button>
                  <span>{skip}</span>
                  <button type="button" aria-label={t("Больше", "More")} disabled={skip >= perPage - 1} onClick={() => { setSkip(skip + 1); }}>
                    +
                  </button>
                </span>
                <span className="fnote">{t("или щёлкните место на первом листе", "or click a place on the first sheet")}</span>
              </div>
              <div className="row2">
                <span>{t("Язык названий полей", "Field label language")}</span>
                {(["ru", "en"] as const).map((value) => (
                  <label key={value}>
                    <input type="radio" name="flang" checked={fieldLang === value} onChange={() => { setFieldLang(value); }} />
                    {value.toUpperCase()}
                  </label>
                ))}
              </div>
            </div>
          </details>

          <div className="preview">
            {!printed.length ? (
              <div className="empty">
                <p>{t("Выберите растения слева — здесь появится лист.", "Pick plants on the left; the sheet appears here.")}</p>
              </div>
            ) : tooMany ? (
              <p className="problem">
                {t(`За раз печатается не больше ${String(MAX_PLANTS)} бирок.`, `At most ${String(MAX_PLANTS)} labels print at a time.`)}
              </p>
            ) : (
              <>
                <div className="pnav">
                  <button type="button" disabled={shownPage <= 1} aria-label={t("Предыдущий лист", "Previous sheet")} onClick={() => { setPage(shownPage - 1); }}>
                    <Icon name="left" />
                  </button>
                  <span>{t(`Лист ${String(shownPage)} из ${String(pages)}`, `Sheet ${String(shownPage)} of ${String(pages)}`)}</span>
                  <button type="button" disabled={shownPage >= pages} aria-label={t("Следующий лист", "Next sheet")} onClick={() => { setPage(shownPage + 1); }}>
                    <Icon name="right" />
                  </button>
                </div>
                {current?.url ? (
                  // The server's own drawing of the page: what the PDF will hold.
                  <img
                    className={shownPage === 1 ? "sheetimg pick" : "sheetimg"}
                    src={current.url}
                    alt={t(`Лист ${String(shownPage)}`, `Sheet ${String(shownPage)}`)}
                    onClick={onSheetClick}
                  />
                ) : current?.error ? (
                  <p className="problem">{current.error}</p>
                ) : (
                  <div className="sheetimg loading" aria-busy="true" />
                )}
              </>
            )}
          </div>

          {untaggedFound.length > 0 && (
            <details className="excl" open={untaggedFound.length <= 5}>
              <summary>
                <b>{t("Без номера — не напечатаются", "No number, will not print")}</b>
                <span className="c">{untaggedFound.length}</span>
              </summary>
              <p>
                {t(
                  "Камера и бирка узнают растение по номеру. Впишите шестизначный номер в колонку tag этих строк таблицы.",
                  "Labels and the camera know a plant by its number. Type a six-digit number into the tag column of these rows.",
                )}
              </p>
              <ul>
                {untaggedFound.slice(0, 20).map((row) => (
                  <li key={row.plant.id}>
                    <Name runs={row.name} /> · {t("строка", "row")} {row.plant.row}
                  </li>
                ))}
              </ul>
            </details>
          )}
        </section>
      </div>

      <div className="abar">
        <div className="sum">
          <b>{printed.length}</b> {plural(printed.length, "бирка", "бирки", "бирок", "labels")}
          {printed.length > 0 && ` · ${t(`${String(pages)} ${plural(pages, "лист", "листа", "листов", "")}`, `${String(pages)} sheet${pages === 1 ? "" : "s"}`)}`}
          <span>{t("PDF печатать в масштабе 100 %, без «подогнать по размеру».", "Print the PDF at 100 %, not «fit to page».")}</span>
          {downloadError && <span className="problem">{downloadError}</span>}
        </div>
        <button className="btn pri" type="button" disabled={!body || downloading} onClick={download}>
          <Icon name="download" />
          {downloading ? t("Готовим PDF…", "Making the PDF…") : t("Скачать PDF", "Download the PDF")}
        </button>
      </div>
    </div>
  );
}

interface FieldListProps {
  keys: string[];
  lockName: boolean;
  allowed: string[];
  label: (key: string) => string;
  onChange: (keys: string[]) => void;
}

/** Chosen fields as chips that can be moved earlier or removed, and a menu to add one. */
function FieldList({ keys, lockName, allowed, label, onChange }: FieldListProps) {
  const { t } = useI18n();
  const rest = allowed.filter((key) => !keys.includes(key));
  const moveUp = (i: number) => {
    const next = [...keys];
    const [key] = next.splice(i, 1);
    if (key !== undefined) next.splice(i - 1, 0, key);
    onChange(next);
  };
  return (
    <div className="fields">
      {keys.length === 0 && <span className="fnote">{t("Ничего", "Nothing")}</span>}
      {keys.map((key, i) => {
        const locked = lockName && key === "name";
        return (
          <span key={key} className={locked ? "fchip lock" : "fchip"}>
            {label(key)}
            {key.startsWith("c:") && <span className="k">{t("колонка", "column")}</span>}
            <button type="button" disabled={i === 0} aria-label={t("Раньше", "Earlier")} onClick={() => { moveUp(i); }}>
              <Icon name="up" size={13} />
            </button>
            {!locked && (
              <button type="button" aria-label={t("Убрать", "Remove")} onClick={() => { onChange(keys.filter((other) => other !== key)); }}>
                <Icon name="x" size={12} />
              </button>
            )}
          </span>
        );
      })}
      {rest.length > 0 && (
        <select
          className="addsel"
          aria-label={t("Добавить поле", "Add a field")}
          value=""
          onChange={(event) => {
            if (event.target.value) onChange([...keys, event.target.value]);
          }}
        >
          <option value="">{t("+ поле", "+ field")}</option>
          <optgroup label={t("Поля", "Fields")}>
            {rest.filter((key) => !key.startsWith("c:")).map((key) => (
              <option key={key} value={key}>
                {label(key)}
              </option>
            ))}
          </optgroup>
          {rest.some((key) => key.startsWith("c:")) && (
            <optgroup label={t("Свои колонки", "Your columns")}>
              {rest.filter((key) => key.startsWith("c:")).map((key) => (
                <option key={key} value={key}>
                  {key.slice(2)}
                </option>
              ))}
            </optgroup>
          )}
        </select>
      )}
    </div>
  );
}
