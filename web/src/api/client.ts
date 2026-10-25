// SPDX-License-Identifier: AGPL-3.0-or-later
// The API client, typed from server/openapi.json (`npm run gen`).
import createClient, { type Middleware } from "openapi-fetch";
import type { paths } from "./schema";
import { getToken, setToken } from "./token";

const auth: Middleware = {
  onRequest({ request }) {
    const token = getToken();
    if (token) request.headers.set("Authorization", `Bearer ${token}`);
    return request;
  },
  onResponse({ response }) {
    // A token the server no longer takes is forgotten, and the app asks for a new one.
    if (response.status === 401) setToken(null);
    return response;
  },
};

export const api = createClient<paths>({ baseUrl: "" });
api.use(auth);

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
  }
}

/** The server's error message, or the HTTP status when it sent none. */
export function apiError(response: Response, body: unknown): ApiError {
  const message =
    typeof body === "object" && body !== null && "message" in body && typeof body.message === "string"
      ? body.message
      : `HTTP ${String(response.status)}`;
  return new ApiError(response.status, message);
}

/** Whether `token` opens the API, without storing it. */
export async function checkToken(token: string): Promise<"ok" | "wrong" | "unreachable"> {
  try {
    const response = await fetch("/api/v1/collections", {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (response.ok) return "ok";
    return response.status === 401 ? "wrong" : "unreachable";
  } catch {
    return "unreachable";
  }
}
