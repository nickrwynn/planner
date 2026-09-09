/**
 * Cached check for whether the cloud LLM is configured on the API.
 *
 * Cached because it gates per-keystroke and per-stroke code paths — without
 * this, every recognition would wait on a round trip that is doomed to fail
 * when no key is set.
 */

let configured: boolean | null = null;
let inFlight: Promise<boolean> | null = null;

export async function isCloudAiAvailable(): Promise<boolean> {
  if (configured !== null) return configured;
  if (inFlight) return inFlight;

  inFlight = (async () => {
    try {
      const { apiGet } = await import("./api");
      const status = await apiGet<{ configured: boolean }>("/ai/status");
      configured = Boolean(status?.configured);
    } catch {
      configured = false;
    }
    inFlight = null;
    return configured;
  })();

  return inFlight;
}

/** Call after the API key changes so the next check re-probes. */
export function resetCloudAiAvailability() {
  configured = null;
  inFlight = null;
}
