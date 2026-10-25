// SPDX-License-Identifier: AGPL-3.0-or-later
import { useState } from "react";
import { checkToken } from "../api/client";
import { setToken } from "../api/token";
import { useI18n } from "../i18n";
import { Icon } from "./common";

/** The first visit: the owner pastes the API token, which is checked, then kept in this browser. */
export function TokenScreen() {
  const { t } = useI18n();
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const submit = () => {
    const token = value.trim();
    if (!token) return;
    setBusy(true);
    setProblem(null);
    void checkToken(token).then((result) => {
      setBusy(false);
      if (result === "ok") setToken(token);
      else if (result === "wrong") setProblem(t("Сервер не принял этот токен.", "The server did not accept this token."));
      else setProblem(t("Сервер не отвечает. Попробуйте позже.", "The server does not answer. Try again later."));
    });
  };

  return (
    <main className="token">
      <form
        className="token-box"
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <h1 className="brand">Square-Pot</h1>
        <p>
          {t(
            "Вставьте токен API, который задан при установке сервера (SQUAREPOT_API_TOKEN). Он хранится только в этом браузере.",
            "Paste the API token set when the server was installed (SQUAREPOT_API_TOKEN). It is kept in this browser only.",
          )}
        </p>
        <label className="search">
          <Icon name="key" size={17} />
          <input
            type="password"
            autoComplete="off"
            spellCheck={false}
            value={value}
            onChange={(event) => {
              setValue(event.target.value);
            }}
            aria-label={t("Токен API", "API token")}
            placeholder={t("Токен API", "API token")}
            autoFocus
          />
        </label>
        {problem && (
          <p className="problem" role="alert">
            {problem}
          </p>
        )}
        <button className="btn pri" type="submit" disabled={busy || !value.trim()}>
          {busy ? t("Проверяем…", "Checking…") : t("Войти", "Sign in")}
        </button>
      </form>
    </main>
  );
}
