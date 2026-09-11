import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  api,
  clearStoredToken,
  downloadFile,
  getStoredToken,
  setStoredToken,
  setUnauthorizedHandler,
  TOKEN_KEY,
} from "./api";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function makeToken(expDeltaSeconds: number | null): string {
  const payload =
    expDeltaSeconds === null
      ? { sub: "1" }
      : { sub: "1", exp: Math.floor(Date.now() / 1000) + expDeltaSeconds };
  return `h.${btoa(JSON.stringify(payload))}.sig`;
}

function stubFetchWith(status: number, body: unknown = {}) {
  const mock = vi.fn().mockResolvedValue(
    new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }),
  );
  vi.stubGlobal("fetch", mock);
  return mock;
}

beforeEach(() => {
  localStorage.clear();
  window.history.pushState({}, "", "http://localhost:3000/projects");
});

afterEach(async () => {
  setUnauthorizedHandler(null);
  clearStoredToken();
  vi.unstubAllGlobals();
  await sleep(350);
});

describe("api client 401 handling", () => {
  it("clears the token and invokes the unauthorized handler on a 401", async () => {
    setStoredToken(makeToken(3600));
    stubFetchWith(401, { detail: "Not authenticated" });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await expect(api.get("/projects")).rejects.toMatchObject({ status: 401 });

    expect(handler).toHaveBeenCalledOnce();
    expect(handler).toHaveBeenCalledWith("/projects");
    expect(getStoredToken()).toBeNull();
  });

  it("does not treat 401s on auth endpoints as session expiry", async () => {
    setStoredToken(makeToken(3600));
    stubFetchWith(401, { detail: "Incorrect email or password" });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await expect(
      api.post("/auth/login", { email: "a@b.c", password: "wrong" }),
    ).rejects.toMatchObject({ status: 401 });

    expect(handler).not.toHaveBeenCalled();
    expect(getStoredToken()).not.toBeNull();
  });

  it("rejects an expired stored token without a network call", async () => {
    setStoredToken(makeToken(-60));
    const fetchMock = stubFetchWith(401);
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await expect(api.get("/projects")).rejects.toMatchObject({
      status: 401,
      detail: "Session expired. Please log in again.",
    });

    expect(fetchMock).not.toHaveBeenCalled();
    expect(handler).toHaveBeenCalledOnce();
    expect(getStoredToken()).toBeNull();
  });

  it("only redirects once for a burst of concurrent 401s", async () => {
    setStoredToken(makeToken(3600));
    stubFetchWith(401);
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await Promise.all([
      api.get("/projects").catch(() => undefined),
      api.get("/projects/1").catch(() => undefined),
      api.get("/projects/1/export").catch(() => undefined),
    ]);

    expect(handler).toHaveBeenCalledOnce();

    await sleep(400);
    await api.get("/projects").catch(() => undefined);
    expect(handler).toHaveBeenCalledTimes(2);
  });

  it("still clears the token when no handler is registered", async () => {
    setStoredToken(makeToken(3600));
    stubFetchWith(401);

    await expect(api.get("/projects")).rejects.toMatchObject({ status: 401 });

    expect(getStoredToken()).toBeNull();
  });

  it("never redirects while already on the login page", async () => {
    window.history.pushState({}, "", "/login");
    setStoredToken(makeToken(3600));
    stubFetchWith(401);
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    await expect(api.get("/projects")).rejects.toMatchObject({ status: 401 });

    expect(handler).not.toHaveBeenCalled();
  });
});

describe("downloadFile 401 handling", () => {
  it("triggers the unauthorized handler and suppresses the alert on 401", async () => {
    setStoredToken(makeToken(3600));
    stubFetchWith(401, { detail: "Not authenticated" });
    const handler = vi.fn();
    setUnauthorizedHandler(handler);
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => undefined);

    downloadFile("/projects/1/export", "x.md");
    await vi.waitFor(() => expect(handler).toHaveBeenCalled());

    expect(alertSpy).not.toHaveBeenCalled();
    expect(getStoredToken()).toBeNull();
  });

  it("alerts on non-401 download failures", async () => {
    setStoredToken(makeToken(3600));
    stubFetchWith(500);
    const alertSpy = vi.spyOn(window, "alert").mockImplementation(() => undefined);

    downloadFile("/projects/1/export", "x.md");
    await vi.waitFor(() => expect(alertSpy).toHaveBeenCalledOnce());
  });

  it("never redirects while already on the login page", async () => {
    window.history.pushState({}, "", "/login");
    setStoredToken(makeToken(3600));
    stubFetchWith(401);
    const handler = vi.fn();
    setUnauthorizedHandler(handler);

    downloadFile("/projects/1/export", "x.md");
    await sleep(50);

    expect(handler).not.toHaveBeenCalled();
  });
});

describe("token storage helpers", () => {
  it("reads and writes the shared token key", () => {
    expect(getStoredToken()).toBeNull();
    setStoredToken("abc");
    expect(getStoredToken()).toBe("abc");
    expect(localStorage.getItem(TOKEN_KEY)).toBe("abc");
    clearStoredToken();
    expect(getStoredToken()).toBeNull();
  });
});
