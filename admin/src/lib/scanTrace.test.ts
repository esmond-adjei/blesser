import { describe, expect, it } from "vitest";
import { describeLog, parseSummary, shortUrl, timeSpan } from "./scanTrace";

describe("parseSummary", () => {
  it("splits lead lines, saved titles and skipped pages", () => {
    const summary = parseSummary(
      [
        "Crawler: 8 extracted, 8 new saves across pipeline and agent.",
        "Stopped after 5 turns without a new save.",
        "Saved: GETFund Scholarship 2026/27; Application Fee Waiver",
        "Skipped: https://a.example/x | A title; with semicolon | deadline: 2026-11-27 | saved; https://b.example/y | [Could not fetch https://b.example/y: http_405. Use another source.] | deadline: none stated | fetch failed",
      ].join("\n"),
    );
    expect(summary.lead).toEqual([
      "Crawler: 8 extracted, 8 new saves across pipeline and agent.",
      "Stopped after 5 turns without a new save.",
    ]);
    expect(summary.saved).toEqual(["GETFund Scholarship 2026/27", "Application Fee Waiver"]);
    expect(summary.skipped).toEqual([
      { url: "https://a.example/x", title: "A title; with semicolon", deadline: "2026-11-27", outcome: "saved" },
      { url: "https://b.example/y", title: "", deadline: "none stated", outcome: "fetch failed" },
    ]);
  });

  it("treats None as nothing saved", () => {
    expect(parseSummary("Saved: None").saved).toEqual([]);
  });
});

describe("describeLog", () => {
  it("names each step and keeps its result readable", () => {
    const steps = describeLog([
      { turn: 1, tool: "search_web", input: { query: "ghana grants" }, ok: true, at: "2026-11-09T20:45:00Z", result_preview: "a\\nb" },
      { turn: 1, tool: "crawl_candidate", input: { url: "https://x.example" }, ok: false, at: "2026-11-09T20:46:30Z" },
      { turn: 2, kind: "turn", note: "Trying another source", at: "2026-11-09T20:47:00Z" },
    ]);
    expect(steps.map((s) => [s.label, s.detail, s.ok])).toEqual([
      ["Searched the web", "ghana grants", true],
      ["Checked a source", "https://x.example", false],
      ["Note", "Trying another source", true],
    ]);
    expect(steps[0].result).toBe("a\nb");
    expect(timeSpan(steps)).toBe("2m 0s");
  });
});

describe("shortUrl", () => {
  it("drops the scheme and www and trims long paths", () => {
    expect(shortUrl("https://www.example.org/")).toBe("example.org");
    expect(shortUrl(`https://example.org/${"a".repeat(80)}`, 20)).toHaveLength(20);
  });
});
