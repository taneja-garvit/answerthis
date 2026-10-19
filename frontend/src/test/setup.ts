import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterAll, afterEach, beforeAll } from "vitest";

import { server } from "./server";

beforeAll(() => {
  server.listen({ onUnhandledRequest: "error" });
  // jsdom's AbortSignal is not the one Node's fetch accepts; tests don't rely
  // on aborting, so drop the signal on the way into the (MSW-patched) fetch.
  const patchedFetch = globalThis.fetch;
  globalThis.fetch = (input, init) => patchedFetch(input, init ? { ...init, signal: undefined } : init);
});
afterEach(() => {
  cleanup();
  server.resetHandlers();
});
afterAll(() => server.close());

// jsdom's AbortSignal is not the class Node's fetch/Request accept. React
// Router (navigations) and TanStack Query pass one, so strip it in tests; no
// test depends on aborting a request.
const NodeRequest = globalThis.Request;
globalThis.Request = class extends NodeRequest {
  constructor(input: RequestInfo | URL, init?: RequestInit) {
    super(input, init ? { ...init, signal: undefined } : init);
  }
} as typeof Request;

// jsdom gaps used by the app.
Element.prototype.scrollIntoView ??= () => {};
URL.createObjectURL ??= () => "blob:test";
URL.revokeObjectURL ??= () => {};
