import { describe, expect, it } from "vitest";
import { escapeHtml, labelList, safeText } from "./safe-text";

describe("safeText", () => {
  it("returns strings unchanged", () => {
    expect(safeText("hello")).toBe("hello");
  });

  it("coerces numbers", () => {
    expect(safeText(42)).toBe("42");
  });

  it("falls back for objects", () => {
    expect(safeText({})).toBe("");
    expect(safeText(null, "n/a")).toBe("n/a");
  });
});

describe("escapeHtml", () => {
  it("escapes markup", () => {
    expect(escapeHtml('<script>"x"</script>')).toBe(
      "&lt;script&gt;&quot;x&quot;&lt;/script&gt;"
    );
  });
});

describe("labelList", () => {
  it("filters empty labels", () => {
    expect(labelList([" a ", "", 3])).toEqual(["a", "3"]);
  });
});
