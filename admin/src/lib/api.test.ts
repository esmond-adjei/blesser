import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as api from "./api";

const user: api.StaffUser = {
  id: "staff-1",
  email: "editor@example.test",
  display_name: "Editor",
  role: "editor",
  email_verified: true,
  disabled: false,
  created_at: "2026-11-01T12:00:00Z",
  scans_last_30_days: 2,
};
const loginResult = {
  access_token: "admin-access",
  refresh_token: "admin-refresh",
  user,
};
const refreshed = {
  user,
  tokens: {
    access_token: "new-admin-access",
    refresh_token: "rotated-admin-refresh",
  },
};
const json = (value: unknown, status = 200) =>
  new Response(JSON.stringify(value), {
    status,
    headers: { "Content-Type": "application/json" },
  });
let storage: Map<string, string>;
let fetchMock: ReturnType<typeof vi.fn<typeof fetch>>;
beforeEach(() => {
  storage = new Map([["blesser.refresh_token", "member-session"]]);
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  });
  fetchMock = vi.fn<typeof fetch>();
  vi.stubGlobal("fetch", fetchMock);
  api.clearSession();
});
afterEach(() => {
  api.clearSession();
  vi.unstubAllGlobals();
});

async function signIn() {
  fetchMock.mockResolvedValueOnce(json(loginResult));
  await api.login(user.email, "password");
  fetchMock.mockClear();
}
describe("admin authentication client", () => {
  it("sends the contract login body without a bearer and isolates member tokens", async () => {
    await signIn();
    expect(api.getAccessToken()).toBe("admin-access");
    expect(storage.get(api.REFRESH_KEY)).toBe("admin-refresh");
    expect(storage.get("blesser.refresh_token")).toBe("member-session");
  });
  it("calls the admin login endpoint with exact credentials", async () => {
    fetchMock.mockResolvedValueOnce(json(loginResult));
    await api.login(user.email, "secret");
    const [url, init] = fetchMock.mock.calls[0] ?? [];
    expect(url).toBe("/api/admin/auth/login");
    expect(init?.method).toBe("POST");
    expect(init?.body).toBe(
      JSON.stringify({ email: user.email, password: "secret" }),
    );
    expect(new Headers(init?.headers).has("Authorization")).toBe(false);
  });
  it("refreshes once for concurrent 401s, rotates the refresh token, and replays with the new access token", async () => {
    await signIn();
    let refreshes = 0;
    fetchMock.mockImplementation(async (url, init) => {
      if (String(url).endsWith("/auth/refresh")) {
        refreshes++;
        expect(init?.body).toBe(
          JSON.stringify({ refresh_token: "admin-refresh" }),
        );
        return json(refreshed);
      }
      if (
        new Headers(init?.headers).get("Authorization") ===
        "Bearer new-admin-access"
      )
        return json(user);
      return json({ detail: "Access token expired" }, 401);
    });
    expect(await Promise.all([api.me(), api.me()])).toEqual([user, user]);
    expect(refreshes).toBe(1);
    expect(storage.get(api.REFRESH_KEY)).toBe("rotated-admin-refresh");
    expect(api.getAccessToken()).toBe("new-admin-access");
  });
  it("clears the staff session when refresh is rejected", async () => {
    await signIn();
    fetchMock
      .mockResolvedValueOnce(json({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(json({ detail: "Sign in again" }, 401));
    await expect(api.me()).rejects.toMatchObject({
      status: 401,
      message: "Sign in again",
    });
    expect(api.getSessionUser()).toBeNull();
    expect(api.getAccessToken()).toBeNull();
    expect(storage.has(api.REFRESH_KEY)).toBe(false);
    expect(storage.get("blesser.refresh_token")).toBe("member-session");
  });
  it("does not retry indefinitely when a replay still returns 401", async () => {
    await signIn();
    fetchMock
      .mockResolvedValueOnce(json({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(json(refreshed))
      .mockResolvedValueOnce(json({ detail: "Revoked" }, 401));
    await expect(api.me()).rejects.toMatchObject({ status: 401 });
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(api.getSessionUser()).toBeNull();
  });
  it("keeps refresh credentials after a temporary upstream failure", async () => {
    await signIn();
    fetchMock
      .mockResolvedValueOnce(json({ detail: "Expired" }, 401))
      .mockResolvedValueOnce(json({ detail: "Try again later" }, 503));
    await expect(api.me()).rejects.toMatchObject({ status: 503 });
    expect(storage.get(api.REFRESH_KEY)).toBe("admin-refresh");
    expect(api.getSessionUser()).toEqual(user);
  });
  it("does not resurrect a session when an in-flight refresh finishes after sign-out", async () => {
    await signIn();
    let complete: ((response: Response) => void) | undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          complete = resolve;
        }),
    );
    const flight = api.refreshSession();
    api.clearSession();
    complete?.(json(refreshed));
    await flight;
    expect(api.getSessionUser()).toBeNull();
    expect(storage.has(api.REFRESH_KEY)).toBe(false);
  });
  it("surfaces the API last-admin error without replacing it", async () => {
    await signIn();
    fetchMock.mockResolvedValueOnce(
      json({ detail: "Cannot demote the last admin" }, 409),
    );
    await expect(
      api.updateUser("last-admin", { role: "editor" }),
    ).rejects.toMatchObject({
      status: 409,
      message: "Cannot demote the last admin",
    });
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
  it("encodes filters and parses paginated empty results", async () => {
    await signIn();
    fetchMock.mockResolvedValueOnce(json({ items: [], total: 0 }));
    expect(
      await api.opportunities({
        q: "climate & energy",
        status: "in_review",
        limit: 30,
        offset: 0,
      }),
    ).toEqual({ items: [], total: 0 });
    expect(fetchMock.mock.calls[0]?.[0]).toBe(
      "/api/admin/opportunities?q=climate+%26+energy&status=in_review&limit=30&offset=0",
    );
  });
  it("rejects malformed authenticated responses at the boundary", async () => {
    await signIn();
    fetchMock.mockResolvedValueOnce(json({ items: [], total: "zero" }));
    await expect(api.opportunities()).rejects.toThrow("Expected a number");
  });
  it("signs out locally even if revoking the server token fails", async () => {
    await signIn();
    fetchMock.mockRejectedValueOnce(new TypeError("Network unavailable"));
    await expect(api.logout()).rejects.toThrow("Network unavailable");
    expect(api.getSessionUser()).toBeNull();
    expect(storage.has(api.REFRESH_KEY)).toBe(false);
  });
  it("rejects member login responses", async () => {
    fetchMock.mockResolvedValueOnce(
      json({ ...loginResult, user: { ...user, role: "member" } }),
    );
    await expect(api.login(user.email, "password")).rejects.toMatchObject({
      status: 403,
    });
    expect(api.getAccessToken()).toBeNull();
  });
});

describe("session races and empty responses", () => {
  it("reuses a newer access token when an older request returns a late 401", async () => {
    await signIn();
    let finish: ((response: Response) => void) | undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const oldRequest = api.me();
    fetchMock.mockResolvedValueOnce(json(refreshed));
    await api.refreshSession();
    fetchMock.mockResolvedValueOnce(json(user));
    finish?.(json({ detail: "Expired" }, 401));
    await expect(oldRequest).resolves.toEqual(user);
    expect(fetchMock).toHaveBeenCalledTimes(3);
    expect(
      fetchMock.mock.calls.filter(([url]) =>
        String(url).endsWith("/auth/refresh"),
      ),
    ).toHaveLength(1);
  });
  it("does not clear a newer login when an older refresh is rejected", async () => {
    await signIn();
    let finish: ((response: Response) => void) | undefined;
    fetchMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    const flight = api.refreshSession().catch((error: unknown) => error);
    fetchMock.mockResolvedValueOnce(
      json({ ...loginResult, access_token: "fresh-login" }),
    );
    await api.login(user.email, "password");
    finish?.(json({ detail: "Refresh revoked" }, 401));
    await flight;
    expect(api.getAccessToken()).toBe("fresh-login");
    expect(api.getSessionUser()).toEqual(user);
  });
  it("accepts a successful empty collection deletion response", async () => {
    await signIn();
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }));
    await expect(api.deleteCollection("collection-1")).resolves.toBeUndefined();
    expect(fetchMock.mock.calls[0]?.[1]?.method).toBe("DELETE");
  });
});
