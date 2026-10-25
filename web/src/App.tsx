// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useMemo, useState } from "react";
import { setToken, useToken } from "./api/token";
import { useData, resetData } from "./data";
import { plantsOf } from "./domain/copy";
import { filterRows, makeRows, parseListState, serializeListState, sortRows, type ListState, type Row } from "./domain/query";
import { I18nContext, initialLang, makeI18n, saveLang, useI18n, type Lang } from "./i18n";
import { navigate, routePath, useLocation } from "./router";
import { Header } from "./views/Header";
import { ListView } from "./views/List";
import { PlantCard } from "./views/PlantCard";
import { PrintView } from "./views/Print";
import { TokenScreen } from "./views/TokenScreen";

export function App() {
  const [lang, setLang] = useState<Lang>(initialLang);
  const i18n = useMemo(
    () =>
      makeI18n(lang, (next) => {
        saveLang(next);
        setLang(next);
      }),
    [lang],
  );
  const token = useToken();
  return <I18nContext value={i18n}>{token ? <Browse /> : <TokenScreen />}</I18nContext>;
}

function Browse() {
  const { t } = useI18n();
  const { schema, templates, copy, error } = useData();
  const { route, params } = useLocation();
  // Ages count to the day the page was opened.
  const [now] = useState(() => new Date());
  const query = params.toString();
  const state = useMemo(() => parseListState(new URLSearchParams(query)), [query]);
  const collections = useMemo(() => [...(copy?.collections.values() ?? [])], [copy]);
  const collectionId = route.page === "home" ? collections[0]?.id : route.collection;
  const collection = collections.find((item) => item.id === collectionId);

  const rows = useMemo(
    () => (schema && copy && collection ? makeRows(schema, plantsOf(copy, collection.id)) : []),
    [schema, copy, collection],
  );
  const result = useMemo(
    () => (schema ? sortRows(schema, filterRows(rows, state), state.sort, now) : []),
    [schema, rows, state, now],
  );

  useEffect(() => {
    if (route.page === "home" && collectionId) {
      navigate(routePath({ page: "list", collection: collectionId }), { replace: true });
    }
  }, [route.page, collectionId]);

  const forget = () => {
    setToken(null);
    resetData();
  };

  if (!schema || !copy) {
    return (
      <div className="status">
        {error ? (
          <p className="problem" role="alert">
            {t("Не удалось загрузить данные: ", "Could not load the data: ")}
            {error}
          </p>
        ) : (
          <p aria-busy="true">{t("Загружаем коллекцию…", "Loading the collection…")}</p>
        )}
      </div>
    );
  }
  if (!collection) {
    return (
      <div className="status">
        <p>{collections.length ? t("Такой коллекции нет.", "There is no such collection.") : t("На сервере нет коллекций.", "The server has no collections.")}</p>
        {collections[0] && (
          <a className="btn sec" href={routePath({ page: "list", collection: collections[0].id })}>
            {collections[0].name}
          </a>
        )}
      </div>
    );
  }

  const suffix = query ? `?${query}` : "";
  const listHref = routePath({ page: "list", collection: collection.id }) + suffix;
  const plantHref = (row: Row) => routePath({ page: "plant", collection: collection.id, plant: row.plant.id }) + suffix;
  const onState = (next: ListState) => {
    const search = serializeListState(next).toString();
    navigate(routePath({ page: "list", collection: collection.id }) + (search ? `?${search}` : ""), { replace: true });
  };
  const open = route.page === "plant" ? rows.find((row) => row.plant.id === route.plant) : undefined;

  return (
    <div className="app">
      <Header collections={collections} current={collection} plantCount={rows.length} onForget={forget} />
      {error && (
        <p className="problem inline" role="status">
          {t("Не удалось обновить данные: ", "Could not refresh the data: ")}
          {error}
        </p>
      )}
      {route.page === "print" ? (
        <PrintView
          key={collection.id}
          schema={schema}
          collection={collection}
          templates={templates}
          rows={rows}
          found={result}
          state={state}
          onState={(next) => {
            const search = serializeListState(next).toString();
            navigate(routePath({ page: "print", collection: collection.id }) + (search ? `?${search}` : ""), { replace: true });
          }}
          listHref={listHref}
        />
      ) : route.page === "plant" ? (
        open ? (
          <PlantCard
            schema={schema}
            collection={collection}
            templates={templates}
            row={open}
            now={now}
            list={result}
            listHref={listHref}
            plantHref={plantHref}
          />
        ) : (
          <div className="status">
            <p>{t("Этого растения больше нет в таблице.", "This plant is no longer in the sheet.")}</p>
            <a className="btn sec" href={listHref}>
              {t("К списку", "Back to the list")}
            </a>
          </div>
        )
      ) : (
        <ListView
          key={collection.id}
          schema={schema}
          collection={collection}
          rows={rows}
          now={now}
          result={result}
          state={state}
          onState={onState}
          plantHref={plantHref}
          printHref={routePath({ page: "print", collection: collection.id }) + suffix}
        />
      )}
    </div>
  );
}
