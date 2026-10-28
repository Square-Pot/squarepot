// SPDX-License-Identifier: AGPL-3.0-or-later
// The batch import page (ADR 0008, stage 2, mockups v2 §4): send a pack of old
// photos, watch the server read its codes, and file or discard what it could
// not — no code, an unknown label, or two labels in one frame.
import { useMemo, useRef, useState } from "react";
import type { ImportedPhoto } from "../api/types";
import { importCounts, importGroup, resolveTag, type PlantLookup } from "../domain/imports";
import { UPLOAD_TYPES, uploadProblem } from "../domain/photos";
import type { Row } from "../domain/query";
import { useFormat } from "../format";
import { useI18n } from "../i18n";
import { useImports, type ImportUpload } from "../imports";
import { onLinkClick } from "../router";
import { Icon } from "./common";

interface Props {
  rows: Row[];
  listHref: string;
}

/** The two live groups of the waiting list. */
type Tab = "reading" | "review";

/** How many cards show before «show more». */
const SHOWN = 60;

/** Key the page by collection, so another collection starts afresh. */
export function ImportView({ rows, listHref }: Props) {
  const { t } = useI18n();
  const imports = useImports();
  const [picked, setPicked] = useState<Tab | null>(null);
  const [shown, setShown] = useState(SHOWN);
  const [problem, setProblem] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const plants = useMemo(
    (): PlantLookup[] => rows.flatMap((row) => (row.plant.tag ? [{ tag: row.plant.tag, name: row.nameText }] : [])),
    [rows],
  );
  const names = useMemo(() => new Map(plants.map((plant) => [plant.tag, plant.name])), [plants]);
  const nameOf = (tag: string): string => names.get(tag) ?? "";

  const photos = imports.photos ?? [];
  const counts = importCounts(photos);
  // The server's list holds only what still waits, so the tabs are the reader's
  // work and the manual queue; what left it is counted per visit below.
  const tab: Tab = picked ?? (counts.review > 0 ? "review" : "reading");
  const ofTab = photos.filter((item) => importGroup(item) === tab);
  const cards = ofTab.slice(0, shown);

  const onFiles = (input: HTMLInputElement) => {
    const files = [...(input.files ?? [])];
    input.value = "";
    const bad = files.filter((file) => uploadProblem(file));
    const good = files.filter((file) => !uploadProblem(file));
    setProblem(
      bad.length
        ? t(
            `Не загружены (нужен JPEG, PNG или WebP до 30 МБ): ${bad.map((file) => file.name).join(", ")}`,
            `Not uploaded (JPEG, PNG or WebP up to 30 MB): ${bad.map((file) => file.name).join(", ")}`,
          )
        : null,
    );
    if (good.length) imports.upload(good);
  };

  return (
    <div className="imppage">
      <div className="imphead">
        <h2>{t("Пакетный импорт", "Batch import")}</h2>
        <a className="btn sec" href={listHref} onClick={(event) => { onLinkClick(event, listHref); }}>
          {t("К списку", "Back to the list")}
        </a>
      </div>
      <p className="impsub">
        {t(
          "Загрузите пачку старых снимков: сервер прочитает в них коды Data Matrix и даты EXIF и разложит снимки с одной известной биркой. Остальные — без кода, с неизвестной биркой или с двумя бирками — ждут разбора здесь.",
          "Upload a pack of old photos: the server reads the Data Matrix codes and the EXIF dates in them, and files the ones with one known label. The rest — no code, an unknown label, or two labels — wait here for you.",
        )}
      </p>

      {imports.unavailable && (
        <p className="problem inline" role="alert">
          {t(
            "На этом сервере не настроено хранение фото — пакетный импорт недоступен.",
            "Photo storage is not set up on this server; the batch import is not available.",
          )}
        </p>
      )}
      {imports.error && (
        <p className="problem inline" role="alert">
          {t("Не удалось получить список снимков: ", "Could not load the photos: ")}
          {imports.error}
        </p>
      )}

      {!imports.unavailable && (
        <>
          <div className="impadd">
            <button className="btn pri" type="button" onClick={() => { picker.current?.click(); }}>
              <Icon name="camera" />
              {t("Выбрать снимки", "Choose photos")}
            </button>
            <input
              ref={picker}
              type="file"
              accept={UPLOAD_TYPES.join(",")}
              multiple
              hidden
              onChange={(event) => { onFiles(event.target); }}
            />
            <span className="pnote">
              {t(
                "Снимки с биркой в кадре разложатся сами, остальные — сюда. Файлы уходят по одному.",
                "Photos with a label in view file themselves; the rest come here. Files are sent one at a time.",
              )}
            </span>
          </div>
          <UploadList
            uploads={imports.uploads}
            onRetry={(id) => { imports.retry(id); }}
            onClear={() => { imports.clearUploads(); }}
          />
          {problem && (
            <p className="problem inline" role="alert">
              {problem}
            </p>
          )}

          {imports.photos === null && !imports.error ? (
            <p className="pnote" aria-busy="true">
              {t("Загружаем…", "Loading…")}
            </p>
          ) : (
            <>
              <div className="imp-sum">
                <button
                  type="button"
                  className={`tile warn${tab === "reading" ? " on" : ""}`}
                  aria-pressed={tab === "reading"}
                  onClick={() => {
                    setPicked("reading");
                    setShown(SHOWN);
                  }}
                >
                  <b>{String(counts.reading)}</b>
                  <span>{t("читаем коды", "reading the codes")}</span>
                </button>
                <button
                  type="button"
                  className={`tile err${tab === "review" ? " on" : ""}`}
                  aria-pressed={tab === "review"}
                  onClick={() => {
                    setPicked("review");
                    setShown(SHOWN);
                  }}
                >
                  <b>{String(counts.review)}</b>
                  <span>{t("разобрать вручную", "to file by hand")}</span>
                </button>
                <div className="tile dim">
                  <b>{String(imports.done.filed)}</b>
                  <span>{t("разложено за этот визит", "filed during this visit")}</span>
                </div>
                <div className="tile dim">
                  <b>{String(imports.done.discarded)}</b>
                  <span>{t("убрано за этот визит", "discarded during this visit")}</span>
                </div>
              </div>

              {tab === "review" && counts.review > 0 && (
                <p className="pnote">
                  {t(
                    "Код не прочитан, на снимке две бирки или такой бирки нет. Укажите, чей снимок, — номером, названием или одной из бирок, — или уберите его.",
                    "No code read, two labels in the photo, or no such label. Say whose photo it is, by number, by name or by one of the labels, or discard it.",
                  )}
                </p>
              )}

              {counts.reading + counts.review === 0 ? (
                <p className="pnote">{t("Очередь пуста: загрузите пачку снимков.", "The queue is empty: upload a pack of photos.")}</p>
              ) : cards.length === 0 ? (
                <p className="pnote">
                  {tab === "reading"
                    ? t("Сейчас сервер ничего не читает.", "The server is not reading anything now.")
                    : t("Ручного разбора нет.", "Nothing to file by hand.")}
                </p>
              ) : (
                <div className="igrid">
                  {cards.map((item) =>
                    tab === "review" ? (
                      <ReviewCard key={item.id} item={item} plants={plants} nameOf={nameOf} imports={imports} />
                    ) : (
                      <ReadingCard key={item.id} item={item} />
                    ),
                  )}
                </div>
              )}
              {ofTab.length > shown && (
                <button className="more" type="button" onClick={() => { setShown(shown + 120); }}>
                  {t(`Показать ещё ${String(ofTab.length - shown)}`, `Show ${String(ofTab.length - shown)} more`)}
                </button>
              )}
            </>
          )}
        </>
      )}
    </div>
  );
}

function UploadList({
  uploads,
  onRetry,
  onClear,
}: {
  uploads: ImportUpload[];
  onRetry: (id: string) => void;
  onClear: () => void;
}) {
  const { t } = useI18n();
  if (!uploads.length) return null;
  const finished = uploads.every((upload) => upload.state === "done" || upload.state === "failed");
  return (
    <ul className="uploads" aria-live="polite">
      {uploads.map((upload) => (
        <li key={upload.id} className={upload.state}>
          <span className="fn">{upload.file.name}</span>
          <span className="st">
            {upload.state === "waiting"
              ? t("ждёт", "waiting")
              : upload.state === "sending"
                ? t("загружается…", "uploading…")
                : upload.state === "done"
                  ? t("загружено", "uploaded")
                  : `${t("ошибка", "failed")}: ${upload.error ?? ""}`}
          </span>
          {upload.state === "failed" && (
            <button className="lnk" type="button" onClick={() => { onRetry(upload.id); }}>
              {t("Повторить", "Retry")}
            </button>
          )}
        </li>
      ))}
      {finished && (
        <li>
          <button className="lnk" type="button" onClick={onClear}>
            {t("Скрыть", "Hide")}
          </button>
        </li>
      )}
    </ul>
  );
}

function Thumb({ item }: { item: ImportedPhoto }) {
  return item.url ? <img src={item.url} alt="" loading="lazy" /> : <span className="noimg" aria-hidden="true" />;
}

function When({ item }: { item: ImportedPhoto }) {
  const format = useFormat();
  return (
    <span className="mt">
      <span>{item.file_time ? format.day(item.file_time) : format.time(item.uploaded_at)}</span>
    </span>
  );
}

function ReadingCard({ item }: { item: ImportedPhoto }) {
  const { t } = useI18n();
  const state =
    item.state === "queued"
      ? t("ждёт очереди", "waiting for the reader")
      : item.state === "decoding"
        ? t("читаем коды…", "reading the codes…")
        : t("прочитано — раскладываем…", "codes read — filing…");
  return (
    <div className="icard">
      <Thumb item={item} />
      <div className="ib">
        <span className="st">{state}</span>
        <When item={item} />
      </div>
    </div>
  );
}

function ReviewCard({
  item,
  plants,
  nameOf,
  imports,
}: {
  item: ImportedPhoto;
  plants: PlantLookup[];
  nameOf: (tag: string) => string;
  imports: ReturnType<typeof useImports>;
}) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const label =
    item.reason === "several_numbers"
      ? item.numbers.length === 2
        ? t("Две бирки — чей снимок?", "Two labels: whose photo?")
        : t("Несколько бирок — чей снимок?", "Several labels: whose photo?")
      : item.reason === "unknown_number"
        ? t(
            `Бирка ${item.numbers[0] ?? "—"} — нет в коллекции`,
            `Label ${item.numbers[0] ?? "—"} is not in the collection`,
          )
        : item.reason === "unreadable"
          ? t("Файл не удалось прочитать", "The file could not be read")
          : t("Код не прочитан", "No code read");

  const act = (action: Promise<void>) => {
    setBusy(true);
    setProblem(null);
    action
      .catch((failure: unknown) => {
        setProblem(failure instanceof Error ? failure.message : String(failure));
      })
      .then(() => {
        setBusy(false);
      });
  };

  const submit = () => {
    const lookup = resolveTag(text, plants);
    if (lookup.status === "found") act(imports.file(item.id, lookup.tag));
    else if (lookup.status === "ambiguous")
      setProblem(t("Таких растений несколько — укажите номер.", "Several plants match — give the number."));
    else setProblem(t("Нет растения с таким номером или названием.", "There is no plant with this number or name."));
  };

  const discard = (
    <button className="ibtn" type="button" disabled={busy} onClick={() => { act(imports.discard(item.id)); }}>
      {t("Убрать", "Discard")}
    </button>
  );

  return (
    <div className="icard review">
      <Thumb item={item} />
      <div className="ib">
        <span className="warn">{label}</span>
        {item.reason === "several_numbers" && (
          <div className="ia">
            {item.numbers.map((number) => (
              <button
                key={number}
                type="button"
                className="ibtn"
                disabled={busy}
                title={nameOf(number)}
                onClick={() => { act(imports.file(item.id, number)); }}
              >
                {number}
              </button>
            ))}
          </div>
        )}
        {item.reason === "unreadable" ? (
          <div className="ia">{discard}</div>
        ) : (
          <form
            className="ifile"
            onSubmit={(event) => {
              event.preventDefault();
              submit();
            }}
          >
            <input
              value={text}
              onChange={(event) => { setText(event.target.value); }}
              placeholder={t("Номер или название", "Number or name")}
              aria-label={t("Растение", "Plant")}
              disabled={busy}
            />
            <div className="ia">
              <button className="ibtn pri" type="submit" disabled={busy || !text.trim()}>
                {t("Разложить", "File")}
              </button>
              {discard}
            </div>
          </form>
        )}
        {problem && (
          <span className="why err" role="alert">
            {problem}
          </span>
        )}
        {item.reason === "unknown_number" && (
          <span className="why">
            {t(
              "Растение добавили в таблицу позже? Обновите копию и разберите снова.",
              "Was the plant added to the sheet later? Refresh the copy and review again.",
            )}
          </span>
        )}
        <When item={item} />
      </div>
    </div>
  );
}
