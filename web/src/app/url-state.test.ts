import { afterEach, describe, expect, it } from "vitest";
import { narrativeIdFromUrl, setUrlNarrative } from "./url-state";

describe("url-state", () => {
  afterEach(() => {
    window.history.replaceState({}, "", "/");
  });

  it("reads narrative id from query", () => {
    window.history.replaceState({}, "", "/?narrative=7");
    expect(narrativeIdFromUrl()).toBe(7);
  });

  it("returns null for invalid narrative", () => {
    window.history.replaceState({}, "", "/?narrative=abc");
    expect(narrativeIdFromUrl()).toBeNull();
  });

  it("writes narrative id to query", () => {
    setUrlNarrative(12);
    expect(new URL(window.location.href).searchParams.get("narrative")).toBe("12");
  });
});
