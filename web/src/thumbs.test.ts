// SPDX-License-Identifier: AGPL-3.0-or-later
import { beforeEach, describe, expect, it, vi } from "vitest";

const post = vi.fn();
vi.mock("./api/client", () => ({ api: { POST: post } }));
const { requestThumbnails, resetThumbnails } = await import("./thumbs");

const later = () => new Date(Date.now() + 6 * 3600_000).toISOString();
const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

describe("thumbnail addresses", () => {
  beforeEach(() => {
    post.mockReset();
    resetThumbnails();
  });

  it("are asked for in batches of 200, once while fresh", async () => {
    post.mockImplementation((_path: string, { body }: { body: { ids: string[] } }) =>
      Promise.resolve({ data: { urls: Object.fromEntries(body.ids.map((id) => [id, `/t/${id}`])), expires_at: later() } }),
    );
    const ids = Array.from({ length: 450 }, (_, i) => `id${String(i)}`);
    requestThumbnails([...ids, "id0"]);
    expect(post.mock.calls.map(([, init]) => (init as { body: { ids: string[] } }).body.ids.length)).toEqual([200, 200, 50]);
    await settle();
    requestThumbnails(ids);
    expect(post).toHaveBeenCalledTimes(3);
  });

  it("answered after the token is forgotten are dropped, and asked for again", async () => {
    let answer: (value: unknown) => void = () => undefined;
    post.mockImplementationOnce(() => new Promise((resolve) => { answer = resolve; }));
    requestThumbnails(["a"]);
    resetThumbnails();
    post.mockResolvedValueOnce({ data: { urls: { a: "/new/a" }, expires_at: later() } });
    requestThumbnails(["a"]);
    expect(post).toHaveBeenCalledTimes(2);
    answer({ data: { urls: { a: "/old/a" }, expires_at: later() } });
    await settle();
    requestThumbnails(["a"]);
    expect(post).toHaveBeenCalledTimes(2);
  });

  it("are not asked for again at once after a failure", async () => {
    post.mockResolvedValue({ error: { message: "photos are off" } });
    requestThumbnails(["a"]);
    await settle();
    requestThumbnails(["a"]);
    expect(post).toHaveBeenCalledTimes(1);
  });
});
