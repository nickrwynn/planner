"use client";

import { Capacitor } from "@capacitor/core";
import { apiGet } from "./api";

export type OAuthBrowserMode = "browser" | "popup" | "redirect";

type WaitOpts = {
  /** Poll until this returns true (e.g. Google Drive connected). */
  waitUntil?: () => Promise<boolean>;
  timeoutMs?: number;
  pollMs?: number;
};

/**
 * Open Google (or any) OAuth authorize URL in an in-app/system browser or popup.
 * When waitUntil succeeds, closes the browser/popup from the *app* side so the
 * OAuth window never has to load the authenticated StudyFlows UI.
 */
export async function openOAuthAuthorizeUrl(
  authorizeUrl: string,
  opts?: WaitOpts
): Promise<OAuthBrowserMode> {
  if (typeof window === "undefined") return "redirect";

  const timeoutMs = opts?.timeoutMs ?? 180_000;
  const pollMs = opts?.pollMs ?? 1500;

  if (Capacitor.isNativePlatform()) {
    try {
      const { Browser } = await import("@capacitor/browser");
      await Browser.open({ url: authorizeUrl, presentationStyle: "popover" });

      if (opts?.waitUntil) {
        const started = Date.now();
        const tick = async () => {
          while (Date.now() - started < timeoutMs) {
            try {
              if (await opts.waitUntil!()) {
                try {
                  await Browser.close();
                } catch {
                  // user may have already closed it
                }
                return;
              }
            } catch {
              // status may 401 briefly — keep polling
            }
            await new Promise((r) => setTimeout(r, pollMs));
          }
        };
        void tick();
      }

      return "browser";
    } catch {
      // fall through
    }
  }

  // Desktop/PWA: popup keeps StudyFlows open; Google redirects the popup to /oauth/done.
  const popup = window.open(authorizeUrl, "studyflows-google-oauth", "width=520,height=720,menubar=no,toolbar=no");
  if (popup) {
    const onMessage = (ev: MessageEvent) => {
      if (ev.origin !== window.location.origin) return;
      if (ev.data?.type !== "studyflows-oauth") return;
      try {
        popup.close();
      } catch {
        // ignore
      }
      window.removeEventListener("message", onMessage);
    };
    window.addEventListener("message", onMessage);

    if (opts?.waitUntil) {
      const started = Date.now();
      void (async () => {
        while (Date.now() - started < timeoutMs) {
          if (popup.closed) break;
          try {
            if (await opts.waitUntil!()) {
              try {
                popup.close();
              } catch {
                // ignore
              }
              break;
            }
          } catch {
            // ignore
          }
          await new Promise((r) => setTimeout(r, pollMs));
        }
        window.removeEventListener("message", onMessage);
      })();
    }

    return "popup";
  }

  window.location.href = authorizeUrl;
  return "redirect";
}

/** Convenience poller for Google Drive connection status. */
export async function waitForGoogleConnected(): Promise<boolean> {
  const status = await apiGet<{ connected: boolean }>("/integrations/google/status");
  return !!status.connected;
}
