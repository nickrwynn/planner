import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  use: {
    baseURL: process.env.E2E_WEB_BASE_URL ?? "http://localhost:3000"
  }
});
