// SPDX-License-Identifier: AGPL-3.0-or-later
import { useEffect, useState } from "react";
import { api, apiError } from "../api/client";
import type { LabelTemplate, Plant } from "../api/types";
import { useI18n } from "../i18n";

type Orientation = "vertical" | "horizontal";

interface Preview {
  key: string;
  url: string | null;
  error: string | null;
}

/** One label cut out of the server's SVG sheet: it sits at the page margin, the template's size. */
function cropToLabel(svg: string, template: LabelTemplate): string {
  const doc = new DOMParser().parseFromString(svg, "image/svg+xml");
  const root = doc.documentElement;
  const { margin_mm: margin, width_mm: width, height_mm: height } = template.layout;
  const pad = 1;
  root.setAttribute("viewBox", `${String(margin - pad)} ${String(margin - pad)} ${String(width + 2 * pad)} ${String(height + 2 * pad)}`);
  root.setAttribute("width", `${String(width + 2 * pad)}mm`);
  root.setAttribute("height", `${String(height + 2 * pad)}mm`);
  return new XMLSerializer().serializeToString(doc);
}

/** The label as the server prints it with the «Label» preset, vertical or horizontal. */
export function LabelPreview({ plant, templates }: { plant: Plant; templates: LabelTemplate[] }) {
  const { t, lang, label } = useI18n();
  const [chosen, setChosen] = useState<{ plant: string; orientation: Orientation } | null>(null);
  const orientation: Orientation =
    chosen?.plant === plant.id ? chosen.orientation : plant.fields.label_type === "h" ? "horizontal" : "vertical";
  const template = templates.find((item) => item.key === orientation);
  const key = `${plant.id}|${orientation}|${lang}|${plant.tag ?? ""}|${JSON.stringify(plant.fields)}`;
  const [preview, setPreview] = useState<Preview | null>(null);

  useEffect(() => {
    if (!plant.tag || !template) return;
    const abort = new AbortController();
    let url: string | null = null;
    void api
      .POST("/api/v1/labels", {
        body: {
          plants: [plant.id],
          template: template.key,
          preset: "label",
          language: lang,
          format: "svg",
          layout: { cut_lines: false },
        },
        parseAs: "text",
        signal: abort.signal,
      })
      .then(({ data, error, response }) => {
        if (data === undefined) throw apiError(response, error);
        url = URL.createObjectURL(new Blob([cropToLabel(data, template)], { type: "image/svg+xml" }));
        setPreview({ key, url, error: null });
      })
      .catch((error: unknown) => {
        if (abort.signal.aborted) return;
        setPreview({ key, url: null, error: error instanceof Error ? error.message : String(error) });
      });
    return () => {
      abort.abort();
      if (url) URL.revokeObjectURL(url);
    };
  }, [key, plant.id, plant.tag, template, lang]);

  const current = preview?.key === key ? preview : null;
  return (
    <div className="blk lblprev">
      <h3>{t("Бирка", "Label")}</h3>
      <div className="seg2" role="group" aria-label={t("Тип бирки", "Label type")}>
        {templates
          .filter((item) => item.key === "vertical" || item.key === "horizontal")
          .map((item) => (
            <button
              key={item.key}
              type="button"
              className={item.key === orientation ? "chip on" : "chip"}
              aria-pressed={item.key === orientation}
              onClick={() => {
                setChosen({ plant: plant.id, orientation: item.key as Orientation });
              }}
            >
              {label(item.label)}
            </button>
          ))}
      </div>
      {!plant.tag ? (
        <p className="lblnote">{t("У растения нет номера: печатать нечего.", "The plant has no number: nothing to print.")}</p>
      ) : current?.url ? (
        <img className={`tagimg ${orientation}`} src={current.url} alt={t("Превью бирки", "Label preview")} />
      ) : current?.error ? (
        <p className="lblnote problem">{current.error}</p>
      ) : (
        <div className={`tagimg ${orientation} loading`} aria-busy="true" />
      )}
      <p className="lblnote">
        {t(
          "Пресет «Бирка». Свои колонки попадают на бирку, только если выбрать их при печати.",
          "The «Label» preset. Custom columns appear only when a print request picks them.",
        )}
      </p>
    </div>
  );
}
