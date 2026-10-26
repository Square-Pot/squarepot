// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useRef, useState, type ReactNode } from "react";
import type { Collection, FieldSchema } from "../api/types";
import { age } from "../domain/names";
import { localDay } from "../domain/photos";
import {
  clearFilters,
  facets as countFacets,
  fieldNumberMatches,
  filterCount,
  isFormer,
  own,
  PHOTO_AGES,
  tagMatch,
  type Facets,
  type ListState,
  type Row,
} from "../domain/query";
import { useFormat } from "../format";
import { useI18n } from "../i18n";
import { navigate, onLinkClick } from "../router";
import { allColumns, loadColumns, saveColumns } from "./columns";
import { Icon, Marked, Name } from "./common";

const PAGE = 100;

interface Props {
  schema: FieldSchema;
  collection: Collection;
  rows: Row[];
  now: Date;
  result: Row[];
  state: ListState;
  onState: (next: ListState) => void;
  plantHref: (row: Row) => string;
  printHref: string;
}

export function ListView({ schema, collection, rows, now, result, state, onState, plantHref, printHref }: Props) {
  const { t, label } = useI18n();
  const format = useFormat();
  const search = useRef<HTMLInputElement>(null);
  const available = allColumns(schema, collection.custom_columns);
  const [columns, setColumns] = useState(() => loadColumns(collection.id, available));
  const [columnsOpen, setColumnsOpen] = useState(false);
  const [sheetOpen, setSheetOpen] = useState(false);
  // «Show more» counts from the start again whenever the search, filters or sort change.
  const listKey = JSON.stringify(state);
  const [paging, setPaging] = useState({ key: listKey, shown: PAGE });
  const shown = paging.key === listKey ? paging.shown : PAGE;
  const query = state.q.trim();
  const filters = filterCount(state);
  const facets = countFacets(rows, state, collection.custom_columns, now);
  const page = result.slice(0, shown);
  // Former plants are left out of the counts, as of the default list.
  const active = rows.filter((row) => !isFormer(row));
  const untagged = active.filter((row) => !row.plant.tag).length;
  const former = rows.length - active.length;

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const typing = event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement;
      if (event.key === "/" && !typing) {
        event.preventDefault();
        search.current?.focus();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  const columnLabel = (key: string): string => {
    if (key.startsWith("c:")) return key.slice(2);
    if (key === "last_photo") return t("Последнее фото", "Last photo");
    if (key === "last_seen") return t("Видели", "Seen");
    const field =
      schema.fields.find((definition) => definition.key === key) ??
      schema.computed.find((definition) => definition.key === key);
    return field ? label(field.label) : key;
  };

  const toggleColumn = (key: string) => {
    const next = columns.includes(key)
      ? columns.filter((column) => column !== key)
      : available.filter((column) => column === key || columns.includes(column));
    setColumns(next);
    saveColumns(collection.id, next);
  };

  const sortBy = (key: string) => {
    onState({ ...state, sort: { key, desc: state.sort.key === key ? !state.sort.desc : false } });
  };

  const cell = (row: Row, key: string) => {
    const { plant } = row;
    if (key === "name") {
      return (
        <td key={key} className="nm">
          <a
            href={plantHref(row)}
            onClick={(event) => {
              event.stopPropagation();
              onLinkClick(event, plantHref(row));
            }}
          >
            <Name runs={row.name} query={query} />
          </a>
        </td>
      );
    }
    if (key === "last_photo") {
      if (!plant.last_photo) return <td key={key} className="dt"><span className="none">{t("нет", "none")}</span></td>;
      const old = new Date(now);
      old.setMonth(old.getMonth() - state.photoAge);
      return (
        <td key={key} className="dt">
          <span className={Date.parse(plant.last_photo) < old.getTime() ? "warn" : ""}>{format.day(plant.last_photo)}</span>
        </td>
      );
    }
    if (key === "last_seen") {
      if (!plant.last_seen) return <td key={key} className="dt"><span className="warn">{t("никогда", "never")}</span></td>;
      const before = state.seen === "since" && state.since && localDay(plant.last_seen) < state.since;
      return (
        <td key={key} className="dt">
          <span className={before ? "warn" : ""}>{format.day(plant.last_seen)}</span>
        </td>
      );
    }
    const bad = plant.invalid[key];
    if (bad) {
      return (
        <td key={key} className="dt">
          <span className="warn" title={`${bad.cell}: ${bad.reason}`}>
            <Icon name="warn" size={13} /> {bad.value}
          </span>
        </td>
      );
    }
    if (key === "tag") {
      return (
        <td key={key} className="num">
          {plant.tag ? <Marked text={plant.tag} query={tagMatch(plant.tag, query)} /> : <span className="none">{t("нет номера", "no number")}</span>}
        </td>
      );
    }
    if (key === "field_number") {
      const value = plant.fields.field_number ?? "";
      return (
        <td key={key} className="num">
          {fieldNumberMatches(value, query) ? <mark>{value}</mark> : value}
        </td>
      );
    }
    if (key === "age") return <td key={key} className="dt">{format.age(age(plant.fields, now))}</td>;
    if (key.startsWith("c:")) return <td key={key}>{own(plant.custom, key.slice(2)) ?? ""}</td>;
    const type = schema.fields.find((field) => field.key === key)?.type;
    const value = plant.fields[key] ?? "";
    if (type === "date") return <td key={key} className="dt">{format.date(value)}</td>;
    if (key === "price" && value) return <td key={key} className="dt">{`${value} ${plant.fields.currency ?? ""}`}</td>;
    return <td key={key}>{value}</td>;
  };

  const facetPanel = (where: string) => (
    <FacetPanel facets={facets} state={state} onState={onState} where={where} now={now} />
  );

  return (
    <div className="lay">
      <aside className="facets" aria-label={t("Фильтры", "Filters")}>
        {facetPanel("side")}
      </aside>
      <div className="main">
        <div className="tools">
          <label className="search">
            <Icon name="search" size={17} />
            <input
              ref={search}
              type="search"
              value={state.q}
              onChange={(event) => {
                onState({ ...state, q: event.target.value });
              }}
              placeholder={t("Номер, название или полевой номер", "Number, name or field number")}
              aria-label={t("Поиск", "Search")}
              autoComplete="off"
            />
            {state.q ? (
              <button className="clr" type="button" aria-label={t("Очистить", "Clear")} onClick={() => { onState({ ...state, q: "" }); }}>
                <Icon name="x" size={15} />
              </button>
            ) : (
              <kbd>/</kbd>
            )}
          </label>
          <button className="btn sec fbtn" type="button" onClick={() => { setSheetOpen(true); }}>
            <Icon name="filter" />
            {t("Фильтры", "Filters")}
            {filters ? ` · ${String(filters)}` : ""}
          </button>
          <span className="selwrap">
            <Icon name="sort" size={15} />
            <select
              aria-label={t("Сортировка", "Sort")}
              value={state.sort.key}
              onChange={(event) => {
                onState({ ...state, sort: { key: event.target.value, desc: false } });
              }}
            >
              {available.map((key) => (
                <option key={key} value={key}>
                  {columnLabel(key)}
                </option>
              ))}
            </select>
          </span>
          <a className="btn sec" href={printHref} onClick={(event) => { onLinkClick(event, printHref); }}>
            <Icon name="print" />
            <span className="tx">{t("Напечатать бирки", "Print labels")}</span>
          </a>
          <span className="colsbtn">
            <button className="btn sec" type="button" aria-expanded={columnsOpen} onClick={() => { setColumnsOpen(!columnsOpen); }}>
              <Icon name="cols" />
              {t("Колонки", "Columns")}
            </button>
            {columnsOpen && (
              <div className="pop">
                {available.map((key) => (
                  <label key={key} className="fopt">
                    <input type="checkbox" checked={columns.includes(key)} disabled={key === "name"} onChange={() => { toggleColumn(key); }} />
                    <span>
                      {columnLabel(key)}
                      {key.startsWith("c:") && <span className="cus">{t("колонка", "column")}</span>}
                    </span>
                    <span />
                  </label>
                ))}
              </div>
            )}
          </span>
        </div>

        {filters > 0 && <ActiveFilters state={state} onState={onState} />}

        <div className="rcount">
          {query || filters ? (
            <>
              {t("Найдено ", "")}
              <b>{result.length}</b>
              {t(` из ${String(active.length)}`, ` of ${String(active.length)} match`)}
            </>
          ) : (
            <>
              <b>{active.length}</b>
              {t(` растений · ${String(untagged)} без номера`, ` plants · ${String(untagged)} without a number`)}
              {former > 0 && t(` · ${String(former)} выбывших скрыто`, ` · ${String(former)} former hidden`)}
            </>
          )}
        </div>

        {result.length ? (
          <>
            <div className="tbl-wrap">
              <table>
                <thead>
                  <tr>
                    {columns.map((key) => {
                      const on = state.sort.key === key;
                      return (
                        <th key={key} aria-sort={on ? (state.sort.desc ? "descending" : "ascending") : undefined}>
                          <button type="button" onClick={() => { sortBy(key); }}>
                            {columnLabel(key)}
                            {key.startsWith("c:") && <span className="cus">{t("колонка", "column")}</span>}
                            {on && <Icon name={state.sort.desc ? "down" : "up"} size={12} />}
                          </button>
                        </th>
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {page.map((row) => (
                    <tr key={row.plant.id} onClick={() => { navigate(plantHref(row)); }}>
                      {columns.map((key) => cell(row, key))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="cards">
              {page.map((row) => (
                <a key={row.plant.id} className="pcard" href={plantHref(row)} onClick={(event) => { onLinkClick(event, plantHref(row)); }}>
                  <span className="nm">
                    <Name runs={row.name} query={query} />
                  </span>
                  <span className="mt">
                    <span className="num">{row.plant.tag ?? t("без номера", "no number")}</span>
                    {row.plant.fields.field_number && <span className="num">{row.plant.fields.field_number}</span>}
                    {row.plant.fields.ex && <span>ex {row.plant.fields.ex}</span>}
                  </span>
                </a>
              ))}
            </div>
            <div className="pager">
              <span>
                {t(
                  `Показано ${String(page.length)} из ${String(result.length)}`,
                  `Showing ${String(page.length)} of ${String(result.length)}`,
                )}
              </span>
              {result.length > shown && (
                <button className="btn sec" type="button" onClick={() => { setPaging({ key: listKey, shown: shown + PAGE }); }}>
                  {t("Показать ещё 100", "Show 100 more")}
                </button>
              )}
              <span className="ro">
                <Icon name="lock" size={13} />
                {t("Только просмотр. Править — в таблице.", "View only. Edit in the sheet.")}
              </span>
            </div>
          </>
        ) : (
          <div className="empty">
            <h3>{t("Ничего не нашлось", "Nothing found")}</h3>
            <p>
              {query
                ? t(
                    `Нет растений, где номер, название или полевой номер содержит «${query}»${filters ? " среди выбранных фильтров" : ""}.`,
                    `No plant has «${query}» in its number, name or field number${filters ? " within the chosen filters" : ""}.`,
                  )
                : t("Под эти фильтры не подходит ни одно растение.", "No plant fits these filters.")}{" "}
              {t(
                "Если растение добавили в таблицу недавно, оно появится после следующего чтения таблицы.",
                "A plant added to the sheet recently appears after the next read of the sheet.",
              )}
            </p>
            <div className="empty-actions">
              {query && (
                <button className="btn sec" type="button" onClick={() => { onState({ ...state, q: "" }); }}>
                  {t("Очистить поиск", "Clear the search")}
                </button>
              )}
              {filters > 0 && (
                <button className="btn sec" type="button" onClick={() => { onState(clearFilters(state)); }}>
                  {t("Сбросить фильтры", "Clear the filters")}
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {sheetOpen && (
        <div className="sheet" role="dialog" aria-modal="true" aria-label={t("Фильтры", "Filters")}>
          <div className="in">
            <div className="sh">
              <b>{t("Фильтры", "Filters")}</b>
              <button className="btn pri" type="button" onClick={() => { setSheetOpen(false); }}>
                {t(`Показать ${String(result.length)}`, `Show ${String(result.length)}`)}
              </button>
            </div>
            {facetPanel("sheet")}
          </div>
        </div>
      )}
    </div>
  );
}

/** The custom-column choices with one column's values replaced; none drops the column. */
const withCustom = (custom: Record<string, string[]>, column: string, values: string[]) =>
  Object.fromEntries([
    ...Object.entries(custom).filter(([key]) => key !== column),
    ...(values.length ? [[column, values] as const] : []),
  ]);

const toggle = (values: string[], value: string): string[] =>
  values.includes(value) ? values.filter((v) => v !== value) : [...values, value];

function FacetPanel({
  facets,
  state,
  onState,
  where,
  now,
}: {
  facets: Facets;
  state: ListState;
  onState: (next: ListState) => void;
  where: string;
  now: Date;
}) {
  const { t } = useI18n();
  const [allGenera, setAllGenera] = useState(false);
  const genera = allGenera ? facets.genus : facets.genus.slice(0, 8);
  const setCustom = (column: string, values: string[]) => {
    onState({ ...state, custom: withCustom(state.custom, column, values) });
  };

  return (
    <>
      <div className="fhead">
        <p className="fttl">{t("Фильтры", "Filters")}</p>
        {filterCount(state) > 0 && (
          <button className="more" type="button" onClick={() => { onState(clearFilters(state)); }}>
            {t("Сбросить", "Clear")}
          </button>
        )}
      </div>
      <div className="fgroup">
        <p className="fttl small">{t("Род", "Genus")}</p>
        {genera.map(({ value, count }) => (
          <label key={value} className={count ? "fopt" : "fopt zero"}>
            <input type="checkbox" checked={state.genus.includes(value)} onChange={() => { onState({ ...state, genus: toggle(state.genus, value) }); }} />
            <i className="nmv">{value}</i>
            <span className="c">{count}</span>
          </label>
        ))}
        {facets.genus.length > genera.length && (
          <button className="more" type="button" onClick={() => { setAllGenera(true); }}>
            {t(`Ещё ${String(facets.genus.length - genera.length)}`, `${String(facets.genus.length - genera.length)} more`)}
          </button>
        )}
      </div>
      <div className="fgroup">
        <p className="fttl small">{t("Бирка", "Label")}</p>
        {(
          [
            ["all", t("Все", "All"), null],
            ["yes", t("С номером", "With a number"), facets.tagged.yes],
            ["no", t("Без номера", "Without a number"), facets.tagged.no],
          ] as const
        ).map(([value, text, count]) => (
          <label key={value} className="fopt">
            <input type="radio" name={`tagged-${where}`} checked={state.tagged === value} onChange={() => { onState({ ...state, tagged: value }); }} />
            <span>{text}</span>
            <span className="c">{count ?? ""}</span>
          </label>
        ))}
      </div>
      <div className="fgroup">
        <p className="fttl small">{t("Фото", "Photo")}</p>
        {(
          [
            ["any", t("Любое", "Any")],
            ["none", t("Нет фото", "No photo")],
            ["old", t("Последнее старше…", "Last one older than…")],
          ] as const
        ).map(([value, text]) => (
          <label key={value} className="fopt">
            <input type="radio" name={`photo-${where}`} checked={state.photo === value} onChange={() => { onState({ ...state, photo: value }); }} />
            <span>{text}</span>
            <span className="c">{facets.photo[value]}</span>
          </label>
        ))}
        <select
          className="finp"
          aria-label={t("Старше", "Older than")}
          value={state.photoAge}
          onChange={(event) => { onState({ ...state, photo: "old", photoAge: Number(event.target.value) }); }}
        >
          {PHOTO_AGES.map((months) => (
            <option key={months} value={months}>
              {months === 6 ? t("полугода", "six months") : months === 12 ? t("года", "a year") : t("двух лет", "two years")}
            </option>
          ))}
        </select>
      </div>
      <div className="fgroup">
        <p className="fttl small">{t("Визит", "Visit")}</p>
        {(
          [
            ["any", t("Любой", "Any")],
            ["since", t("Не видели с…", "Not seen since…")],
            ["never", t("Ни разу", "Never")],
          ] as const
        ).map(([value, text]) => (
          <label key={value} className="fopt">
            <input
              type="radio"
              name={`seen-${where}`}
              checked={state.seen === value}
              onChange={() => {
                // «Since» starts a month back until a day is picked.
                const monthAgo = new Date(now);
                monthAgo.setMonth(monthAgo.getMonth() - 1);
                onState({ ...state, seen: value, since: value === "since" ? state.since || localDay(monthAgo.toISOString()) : "" });
              }}
            />
            <span>{text}</span>
            <span className="c">{value === "since" && !state.since ? "" : facets.seen[value]}</span>
          </label>
        ))}
        <input
          className="finp"
          type="date"
          aria-label={t("Не видели с", "Not seen since")}
          value={state.since}
          onChange={(event) => {
            const since = event.target.value;
            onState({ ...state, seen: since ? "since" : "any", since });
          }}
        />
        <p className="sub2">{t("Считает и визиты без фото, и снимки.", "Counts visits without a photo and photos alike.")}</p>
      </div>
      <div className="fgroup">
        <p className="fttl small">{t("Выбывшие", "Former plants")}</p>
        <p className="sub2">{t("Со статусом: погиб, подарен, продан, потерян", "With a status: dead, gifted, sold, lost")}</p>
        {(
          [
            ["hide", t("Скрыть", "Hide")],
            ["show", t("Показать тоже", "Show too")],
            ["only", t("Только выбывшие", "Only them")],
          ] as const
        ).map(([value, text]) => (
          <label key={value} className="fopt">
            <input type="radio" name={`former-${where}`} checked={state.former === value} onChange={() => { onState({ ...state, former: value }); }} />
            <span>{text}</span>
            <span className="c">{facets.former[value]}</span>
          </label>
        ))}
      </div>
      {facets.custom.length > 0 && (
        <div className="fgroup">
          <p className="fttl small">{t("Свои колонки", "Your columns")}</p>
          <p className="sub2">{t("Из таблицы, как есть", "From the sheet, as they are")}</p>
          {facets.custom.map(({ column, values }, i) => {
            const chosen = own(state.custom, column) ?? [];
            return (
              <details key={column} className="cc" open={i === 0 || chosen.length > 0}>
                <summary>
                  {column}
                  {chosen.length > 0 && <span className="on">{chosen.length}</span>}
                </summary>
                <div className="fgroup">
                  {values.map(({ value, count }) => (
                    <label key={value} className={count ? "fopt" : "fopt zero"}>
                      <input type="checkbox" checked={chosen.includes(value)} onChange={() => { setCustom(column, toggle(chosen, value)); }} />
                      <span className={value ? "" : "emp"}>{value || t("пусто", "empty")}</span>
                      <span className="c">{count}</span>
                    </label>
                  ))}
                </div>
              </details>
            );
          })}
        </div>
      )}
    </>
  );
}

function ActiveFilters({ state, onState }: { state: ListState; onState: (next: ListState) => void }) {
  const { t } = useI18n();
  const format = useFormat();
  const chips: { key: string; text: ReactNode; remove: () => void }[] = [
    ...state.genus.map((genus) => ({
      key: `g:${genus}`,
      text: <i>{genus}</i>,
      remove: () => { onState({ ...state, genus: state.genus.filter((g) => g !== genus) }); },
    })),
    ...Object.entries(state.custom).flatMap(([column, values]) =>
      values.map((value) => ({
        key: `c:${column}:${value}`,
        text: `${column} = ${value || t("пусто", "empty")}`,
        remove: () => {
          const rest = values.filter((v) => v !== value);
          onState({ ...state, custom: withCustom(state.custom, column, rest) });
        },
      })),
    ),
  ];
  if (state.tagged !== "all") {
    chips.push({
      key: "tagged",
      text: state.tagged === "yes" ? t("С номером", "With a number") : t("Без номера", "Without a number"),
      remove: () => { onState({ ...state, tagged: "all" }); },
    });
  }
  if (state.photo !== "any") {
    const older = state.photoAge === 6 ? t("полугода", "six months") : state.photoAge === 12 ? t("года", "a year") : t("двух лет", "two years");
    chips.push({
      key: "photo",
      text: state.photo === "none" ? t("Нет фото", "No photo") : t(`Фото старше ${older}`, `Photo older than ${older}`),
      remove: () => { onState({ ...state, photo: "any" }); },
    });
  }
  if (state.seen !== "any") {
    chips.push({
      key: "seen",
      text: state.seen === "never" ? t("Ни разу не видели", "Never seen") : t(`Не видели с ${format.date(state.since)}`, `Not seen since ${format.date(state.since)}`),
      remove: () => { onState({ ...state, seen: "any", since: "" }); },
    });
  }
  if (state.former !== "hide") {
    chips.push({
      key: "former",
      text: state.former === "only" ? t("Только выбывшие", "Only former plants") : t("С выбывшими", "With former plants"),
      remove: () => { onState({ ...state, former: "hide" }); },
    });
  }
  return (
    <div className="active">
      {chips.map((chip) => (
        <button key={chip.key} className="achip" type="button" onClick={chip.remove} title={t("Убрать фильтр", "Remove the filter")}>
          {chip.text}
          <span className="x">
            <Icon name="x" size={12} />
          </span>
        </button>
      ))}
    </div>
  );
}
