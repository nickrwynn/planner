import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/**
 * Visual check of the horizontal flow track. Mirrors the DOM that
 * StudyFlowStepper emits so the CSS states can be verified: completed steps
 * shaded, current step green, upcoming steps plain.
 */

const CSS = fs.readFileSync(path.join(__dirname, "../app/globals.css"), "utf-8");

type Fixture = {
  label: string;
  state: "done" | "active" | "pending";
  rating?: "easy" | "medium" | "hard";
  time?: string;
};

const STEPS: Fixture[] = [
  { label: "Comment", state: "done", rating: "easy", time: "1m 10s" },
  { label: "Ask", state: "done", rating: "medium", time: "2m" },
  { label: "Comment", state: "done", rating: "easy", time: "55s" },
  { label: "Ask", state: "done", rating: "hard", time: "6m 20s" },
  { label: "Sample", state: "done", rating: "hard", time: "11m" },
  { label: "Summarize", state: "active" },
  { label: "Flashcards", state: "pending" },
  { label: "Hide & recall", state: "pending" },
  { label: "Quiz", state: "pending" },
];

const items = STEPS.map((s, i) => {
  const dot = s.rating ? `<span class="flowStepDot is-${s.rating}"></span>` : "";
  const time = s.time ? `<span class="flowStepTime">${s.time}</span>` : "";
  return `<li class="flowStep is-${s.state}"><button type="button">
    <span class="flowStepIndex">${i + 1}</span>
    <span class="flowStepLabel">${s.label}</span>
    ${dot}${time}
  </button></li>`;
}).join("");

const HARNESS = `<!doctype html>
<html><head><meta charset="utf-8"><style>
  body { margin: 0; font-family: system-ui, sans-serif; background: #f3f4f6; }
${CSS}
</style></head>
<body>
  <nav class="flowStepper"><ol class="flowStepperTrack">${items}</ol></nav>
</body></html>`;

test("flow track shows done, active and pending states", async ({ page }) => {
  await page.setViewportSize({ width: 1280, height: 200 });
  await page.setContent(HARNESS);

  const track = page.locator(".flowStepperTrack");
  await expect(track).toBeVisible();
  await expect(page.locator(".flowStep")).toHaveCount(9);

  // The active step must be the green one, and only one step is active.
  await expect(page.locator(".flowStep.is-active")).toHaveCount(1);
  const activeBg = await page.evaluate(
    () => getComputedStyle(document.querySelector(".flowStep.is-active button")!).backgroundColor
  );
  const doneBg = await page.evaluate(
    () => getComputedStyle(document.querySelector(".flowStep.is-done button")!).backgroundColor
  );
  const pendingBg = await page.evaluate(
    () => getComputedStyle(document.querySelector(".flowStep.is-pending button")!).backgroundColor
  );

  // The three states must be visibly different from each other.
  expect(new Set([activeBg, doneBg, pendingBg]).size).toBe(3);

  const rgb = (s: string) => (s.match(/\d+/g) || []).map(Number);
  // Active reads green: more green than red or blue.
  const [ar, ag, ab] = rgb(activeBg);
  expect(ag).toBeGreaterThan(ar);
  expect(ag).toBeGreaterThan(ab);

  // Done is shaded — darker than the untouched pending chip.
  const lum = (s: string) => {
    const [r, g, b] = rgb(s);
    return 0.299 * r + 0.587 * g + 0.114 * b;
  };
  expect(lum(doneBg)).toBeLessThan(lum(pendingBg));

  // The track lays out on one horizontal line.
  const tops = await page.evaluate(() =>
    Array.from(document.querySelectorAll(".flowStep button")).map((el) =>
      Math.round(el.getBoundingClientRect().top)
    )
  );
  expect(new Set(tops).size).toBe(1);

  await page.locator(".flowStepper").screenshot({ path: "test-results/flow-stepper.png" });
});
