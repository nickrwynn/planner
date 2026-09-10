import { expect, test } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/**
 * Renders representative chrome against the real stylesheet in each theme.
 *
 * The bug this guards against is a component painting itself a light colour
 * while the page chrome goes dark: the tokens are only useful if nothing
 * bypasses them.
 */

const CSS = fs.readFileSync(path.join(__dirname, "../app/globals.css"), "utf-8");

const BODY = `
<div class="appShell" style="grid-template-columns: 220px 1fr;">
  <aside class="sidebar">
    <div class="brandMark">StudyFlows</div>
    <a class="navLink navLinkActive" href="#">Calendar</a>
    <a class="navLink" href="#">Courses</a>
    <a class="navLink" href="#">Resources</a>
  </aside>
  <main style="padding: 16px; display: grid; gap: 16px;">
    <div>
      <h1 style="margin:0;">Calendar</h1>
      <div class="calendarMore">Click a day to open your daily planner.</div>
    </div>

    <div class="calendarGrid" style="grid-template-columns: repeat(4, minmax(0,1fr));">
      <div class="calendarWeekday">Wed</div>
      <div class="calendarWeekday">Thu</div>
      <div class="calendarWeekday">Fri</div>
      <div class="calendarWeekday">Sat</div>
      <div class="calendarCell calendarCellToday">
        <div class="calendarDayNum">9</div>
        <span class="calendarEvent is-red">Email Prof. Bhalerao</span>
        <span class="calendarEvent">Wednesday Code Along</span>
      </div>
      <div class="calendarCell">
        <div class="calendarDayNum">10</div>
        <span class="calendarEvent is-yellow">Reading 3, Recursion</span>
        <span class="calendarEvent is-done">Knowledge Check 1</span>
      </div>
      <div class="calendarCell calendarCellSelected">
        <div class="calendarDayNum">11</div>
        <span class="calendarEvent is-green">HW_02</span>
        <div class="calendarMore">+2 more</div>
      </div>
      <div class="calendarCell calendarCellMuted">
        <div class="calendarDayNum">12</div>
      </div>
    </div>

    <nav class="flowStepper"><ol class="flowStepperTrack">
      <li class="flowStep is-done"><button type="button"><span class="flowStepIndex">1</span><span>Comment</span><span class="flowStepDot is-easy"></span><span class="flowStepTime">1m</span></button></li>
      <li class="flowStep is-done"><button type="button"><span class="flowStepIndex">2</span><span>Ask</span><span class="flowStepDot is-hard"></span><span class="flowStepTime">6m</span></button></li>
      <li class="flowStep is-active"><button type="button"><span class="flowStepIndex">3</span><span>Summarize</span></button></li>
      <li class="flowStep is-pending"><button type="button"><span class="flowStepIndex">4</span><span>Quiz</span></button></li>
    </ol></nav>

    <div class="card" style="display:grid; gap:6px; padding:12px; border:1px solid var(--border); border-radius: var(--radius-lg); background: var(--bg-elevated);">
      <div class="studySideTitle">Progress &amp; effort</div>
      <div class="metricRow"><span class="metricLabel">Mastery</span><span class="metricBar"><span class="metricFill is-mid" style="width:62%"></span></span><span class="metricValue">62%</span></div>
      <div class="metricRow"><span class="metricLabel">Comprehension</span><span class="metricBar"><span class="metricFill is-high" style="width:91%"></span></span><span class="metricValue">91%</span></div>
      <div class="metricRow"><span class="metricLabel">Effort mix</span><span class="metricChips"><span class="metricChip is-easy">2 easy</span><span class="metricChip is-medium">1 med</span><span class="metricChip is-hard">1 hard</span></span></div>
    </div>
  </main>
</div>`;

function harness(theme: string) {
  return `<!doctype html><html data-theme="${theme}"><head><meta charset="utf-8"><style>${CSS}</style></head><body>${BODY}</body></html>`;
}

/** Parse "rgb(r, g, b)" and return perceived luminance, 0 (black) to 255. */
function luminance(rgb: string): number {
  const m = rgb.match(/\d+/g);
  if (!m) return -1;
  const [r, g, b] = m.map(Number);
  return 0.299 * r + 0.587 * g + 0.114 * b;
}

test("dark theme paints every surface dark", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.setContent(harness("dark"));

  const surfaces = [".appShell", ".sidebar", ".calendarCell", ".card", ".flowStepper"];
  for (const selector of surfaces) {
    const bg = await page.evaluate(
      (sel) => getComputedStyle(document.querySelector(sel)!).backgroundColor,
      selector
    );
    // Anything above mid-grey means the element ignored the theme tokens.
    expect(luminance(bg), `${selector} background ${bg}`).toBeLessThan(90);
  }

  // Body text must stay light against those dark surfaces.
  const fg = await page.evaluate(() => getComputedStyle(document.body).color);
  expect(luminance(fg)).toBeGreaterThan(140);

  await page.screenshot({ path: "test-results/theme-dark.png", fullPage: true });
});

test("light theme still paints surfaces light", async ({ page }) => {
  await page.setViewportSize({ width: 1100, height: 900 });
  await page.setContent(harness("default"));

  for (const selector of [".calendarCell", ".card"]) {
    const bg = await page.evaluate(
      (sel) => getComputedStyle(document.querySelector(sel)!).backgroundColor,
      selector
    );
    expect(luminance(bg), `${selector} background ${bg}`).toBeGreaterThan(200);
  }

  await page.screenshot({ path: "test-results/theme-light.png", fullPage: true });
});

test("task colour and completion are distinguishable in dark mode", async ({ page }) => {
  await page.setContent(harness("dark"));

  const read = (sel: string) =>
    page.evaluate((s) => {
      const el = document.querySelector(s)!;
      const cs = getComputedStyle(el);
      return { bg: cs.backgroundColor, fg: cs.color, border: cs.borderLeftColor, deco: cs.textDecorationLine };
    }, sel);

  const red = await read(".calendarEvent.is-red");
  const yellow = await read(".calendarEvent.is-yellow");
  const green = await read(".calendarEvent.is-green");
  const done = await read(".calendarEvent.is-done");
  const plain = await read(".calendarEvent:not([class*=is-])");

  // Each band is visibly its own colour, not all the same chip.
  const bands = [red.bg, yellow.bg, green.bg, plain.bg];
  expect(new Set(bands).size).toBe(4);

  // Red really is reddish, green really is greenish.
  const rgb = (s: string) => (s.match(/\d+/g) || []).map(Number);
  expect(rgb(red.border)[0]).toBeGreaterThan(rgb(red.border)[1]);
  expect(rgb(green.border)[1]).toBeGreaterThan(rgb(green.border)[0]);

  // Completed work is struck through and dimmer than an open task.
  expect(done.deco).toContain("line-through");
  expect(luminance(done.fg)).toBeLessThan(luminance(red.fg) + 60);
});
