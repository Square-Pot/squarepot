// SPDX-License-Identifier: AGPL-3.0-or-later
// The plant card's photos, timeline variant A of the accepted mockup (task #164):
// years newest first, the plant's age and the comment at each photo, the main
// photo beside them, uploads, and deleted photos that can come back for 30 days.
import { useRef, useState } from "react";
import type { FieldSchema, Photo, Plant } from "../api/types";
import { ageAt, byYear, localDay, mainPhoto, newest, pinned, UPLOAD_TYPES, uploadProblem } from "../domain/photos";
import { useFormat } from "../format";
import { useI18n } from "../i18n";
import { usePlantPhotos, type PlantPhotos } from "../photos";
import { Icon } from "./common";

interface Props {
  schema: FieldSchema;
  plant: Plant;
}

/** Key it by the plant's number, so another plant starts with its own photos and uploads. */
export function Photos({ schema, plant }: Props) {
  const { t } = useI18n();
  const format = useFormat();
  const photos = usePlantPhotos(plant.tag);
  const [problem, setProblem] = useState<string | null>(null);
  const [editing, setEditing] = useState<string | null>(null);
  const picker = useRef<HTMLInputElement>(null);

  const all = photos.photos ?? [];
  const live = all.filter((photo) => !photo.deleted_at);
  const deleted = all.filter((photo) => photo.deleted_at);
  const main = mainPhoto(live);
  const isPinned = pinned(live);
  const latest = newest(live);

  const act = (action: Promise<void>) => {
    setProblem(null);
    action.catch((error: unknown) => {
      setProblem(error instanceof Error ? error.message : String(error));
    });
  };

  const age = (iso: string): string => {
    const at = ageAt(plant.fields, iso);
    if (!at) return "";
    const span = format.span(at.months);
    return at.from === "seeding" ? span : t(`в коллекции ${span}`, `${span} in the collection`);
  };

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
    if (good.length) photos.upload(good);
  };

  const status = plant.fields.status;
  const statusLabel = status
    ? schema.fields.find((field) => field.key === "status")?.values?.find((value) => value.key === status)?.label
    : undefined;
  const statusText = status ? (statusLabel ? `${t(statusLabel.ru, statusLabel.en)} (${status})` : status) : t("нет", "none");

  return (
    <section className="blk photos" aria-label={t("Фото", "Photos")}>
      <h3>
        <span>
          {t("Фото", "Photos")}
          {live.length > 0 && <small> · {live.length}</small>}
        </span>
        {plant.tag && (
          <>
            <button className="btn sec" type="button" onClick={() => { picker.current?.click(); }}>
              <Icon name="camera" />
              {t("Добавить фото", "Add photos")}
            </button>
            <input ref={picker} type="file" accept={UPLOAD_TYPES.join(",")} multiple hidden onChange={(event) => { onFiles(event.target); }} />
          </>
        )}
      </h3>

      {problem && (
        <p className="problem inline" role="alert">
          {problem}
        </p>
      )}
      {photos.error && (
        <p className="problem inline" role="alert">
          {t("Не удалось загрузить фото: ", "Could not load the photos: ")}
          {photos.error}
        </p>
      )}
      <UploadList photos={photos} />

      {!plant.tag ? (
        <p className="pnote">
          {t(
            "Фото хранятся по номеру растения. Когда номер будет выдан в таблице, сюда можно будет добавить снимки.",
            "Photos are kept by the plant's number. Once the sheet gives it a number, photos can be added here.",
          )}
        </p>
      ) : photos.photos === null && !photos.error ? (
        <p className="pnote" aria-busy="true">
          {t("Загружаем фото…", "Loading the photos…")}
        </p>
      ) : !live.length ? (
        <div className="pempty">
          <span className="si">
            <Icon name="camera" />
          </span>
          <div>
            <b>{t("Фото пока нет", "No photos yet")}</b>
            <p>
              {t(
                "Снимите растение телефоном в режиме инвентаризации или добавьте снимки здесь. Первый снимок сразу станет главным.",
                "Photograph it with the phone's inventory mode, or add photos here. The first photo becomes the main one.",
              )}{" "}
              {t("Последний визит: ", "Last visit: ")}
              {plant.last_seen ? format.day(plant.last_seen) : t("никогда", "never")}.
            </p>
          </div>
        </div>
      ) : (
        <div className="chA">
          <div className="tl">
            {byYear(live).map((year) => (
              <div key={year.year} className="tyear">
                <div className="yr">
                  {year.year}
                  <small>
                    {t(`${String(year.photos.length)} фото`, `${String(year.photos.length)} ${year.photos.length === 1 ? "photo" : "photos"}`)}
                  </small>
                </div>
                {year.photos.map((photo) => (
                  <div key={photo.id} className="ev">
                    <button
                      className="pthumb"
                      type="button"
                      title={t("Сделать главным", "Make it the main photo")}
                      aria-label={t(`Сделать главным снимок от ${format.day(photo.taken_at)}`, `Make the photo of ${format.day(photo.taken_at)} the main one`)}
                      aria-pressed={photo === main}
                      onClick={() => {
                        // The newest is the main photo by itself; picking it keeps it so.
                        if (photo !== main) act(photos.chooseMain(photo === latest ? null : photo.id));
                      }}
                    >
                      <img src={photo.thumbnail_url} alt="" loading="lazy" width={photo.width} height={photo.height} />
                      {photo === main && <span className="star">{t("главное", "main")}</span>}
                    </button>
                    <div className="d">
                      {age(photo.taken_at) && <span className="age">{age(photo.taken_at)}</span>}
                      <span className="dt">{format.day(photo.taken_at)}</span>
                      {editing === photo.id ? (
                        <EditPhoto
                          photo={photo}
                          onCancel={() => { setEditing(null); }}
                          onSave={(change) => {
                            setEditing(null);
                            act(photos.change(photo.id, change));
                          }}
                        />
                      ) : (
                        <>
                          {photo.comment && <span className="nt">{photo.comment}</span>}
                          <span className="acts">
                            <a className="lnk" href={photo.url} target="_blank" rel="noopener noreferrer">
                              {t("Открыть", "Open")}
                            </a>
                            <button className="lnk" type="button" onClick={() => { setEditing(photo.id); }}>
                              {photo.comment ? t("Изменить", "Edit") : t("Комментарий или дата", "Comment or date")}
                            </button>
                            <button className="lnk" type="button" onClick={() => { act(photos.remove(photo.id)); }}>
                              {t("Удалить", "Delete")}
                            </button>
                          </span>
                        </>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            ))}
            {plant.fields.seeding_date && (
              <div className="tyear">
                <div className="yr">
                  {plant.fields.seeding_date.slice(0, 4)}
                  <small>{t("посев", "sown")}</small>
                </div>
                <div className="ev noph">
                  <span className="pthumb">{t("без фото", "no photo")}</span>
                  <div className="d">
                    <span className="age">{t("посев", "sown")}</span>
                    <span className="dt">{format.date(plant.fields.seeding_date)}</span>
                    <span className="nt">{t("Дата из таблицы.", "Date from the sheet.")}</span>
                  </div>
                </div>
              </div>
            )}
          </div>

          <aside className="pside">
            {main && (
              <div className="pmain">
                <a href={main.url} target="_blank" rel="noopener noreferrer">
                  <img src={main.url} alt={t("Главное фото", "Main photo")} width={main.width} height={main.height} />
                </a>
                <div className="cap">
                  <span>
                    {t("Главное фото", "Main photo")} · {format.day(main.taken_at)}
                  </span>
                  <span>{age(main.taken_at)}</span>
                </div>
                <div className="cap">
                  <span>{isPinned ? t("Выбрано вами", "Picked by you") : t("Самое новое — выбирается само", "The newest, chosen by itself")}</span>
                  {isPinned && (
                    <button className="lnk" type="button" onClick={() => { act(photos.chooseMain(null)); }}>
                      {t("Вернуть самое новое", "Back to the newest")}
                    </button>
                  )}
                </div>
              </div>
            )}
            <div className="invbox">
              <h4>{t("Инвентаризация", "Inventory")}</h4>
              <div className="r">
                <span>{t("Последний визит", "Last visit")}</span>
                <span>{plant.last_seen ? format.day(plant.last_seen) : t("никогда", "never")}</span>
              </div>
              <div className="r">
                <span>{t("Фото", "Photos")}</span>
                <span>{live.length}</span>
              </div>
              <div className="r">
                <span>{t("Последнее фото", "Last photo")}</span>
                <span>{latest ? format.day(latest.taken_at) : "—"}</span>
              </div>
              <div className="r">
                <span>{t("Статус", "Status")}</span>
                <span>{statusText}</span>
              </div>
            </div>
            <p className="pnote">
              {t(
                "Щёлкните снимок, чтобы сделать его главным; новые снимки его тогда не заменят.",
                "Click a photo to make it the main one; new photos will not replace it then.",
              )}
            </p>
          </aside>
        </div>
      )}

      {deleted.length > 0 && (
        <details className="pdeleted">
          <summary>
            {t(`Удалённые · ${String(deleted.length)}`, `Deleted · ${String(deleted.length)}`)}
            <small>{t(" — можно вернуть в течение 30 дней", " — can be restored for 30 days")}</small>
          </summary>
          <ul>
            {deleted.map((photo) => (
              <li key={photo.id}>
                <img src={photo.thumbnail_url} alt="" loading="lazy" />
                <span>
                  {format.day(photo.taken_at)}
                  {photo.comment && ` · ${photo.comment}`}
                </span>
                <button className="btn sec" type="button" onClick={() => { act(photos.restore(photo.id)); }}>
                  {t("Вернуть", "Restore")}
                </button>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}

function UploadList({ photos }: { photos: PlantPhotos }) {
  const { t } = useI18n();
  if (!photos.uploads.length) return null;
  const finished = photos.uploads.every((upload) => upload.state === "done" || upload.state === "failed");
  return (
    <ul className="uploads" aria-live="polite">
      {photos.uploads.map((upload) => (
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
            <button className="lnk" type="button" onClick={() => { photos.retry(upload.id); }}>
              {t("Повторить", "Retry")}
            </button>
          )}
        </li>
      ))}
      {finished && (
        <li>
          <button className="lnk" type="button" onClick={photos.clearUploads}>
            {t("Скрыть", "Hide")}
          </button>
        </li>
      )}
    </ul>
  );
}

function EditPhoto({
  photo,
  onSave,
  onCancel,
}: {
  photo: Photo;
  onSave: (change: { comment?: string; taken_at?: string }) => void;
  onCancel: () => void;
}) {
  const { t } = useI18n();
  const [comment, setComment] = useState(photo.comment);
  const [day, setDay] = useState(localDay(photo.taken_at));

  const submit = () => {
    const change: { comment?: string; taken_at?: string } = {};
    if (comment.trim() !== photo.comment) change.comment = comment.trim();
    // A new day keeps the time of day the photo had.
    if (day && day !== localDay(photo.taken_at)) {
      const taken = new Date(photo.taken_at);
      const [year, month, date] = day.split("-").map(Number);
      if (year && month && date) {
        taken.setFullYear(year, month - 1, date);
        change.taken_at = taken.toISOString();
      }
    }
    if (Object.keys(change).length) onSave(change);
    else onCancel();
  };

  return (
    <form
      className="pedit"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <input
        type="text"
        value={comment}
        maxLength={1000}
        placeholder={t("Комментарий: «зацвёл», «пересадка»…", "Comment: «first flower», «repotted»…")}
        aria-label={t("Комментарий", "Comment")}
        onChange={(event) => { setComment(event.target.value); }}
      />
      <input type="date" value={day} required aria-label={t("Дата съёмки", "Date taken")} onChange={(event) => { setDay(event.target.value); }} />
      <span className="acts">
        <button className="btn pri" type="submit">
          {t("Сохранить", "Save")}
        </button>
        <button className="btn sec" type="button" onClick={onCancel}>
          {t("Отмена", "Cancel")}
        </button>
      </span>
    </form>
  );
}
