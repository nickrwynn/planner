"use client";

import { Capacitor } from "@capacitor/core";

/**
 * Open Google (or any) OAuth authorize URL in a system/in-app browser when possible,
 * falling back to same-tab navigation.
 */
export async function openOAuthAuthorizeUrl(authorizeUrl: string): Promise<"browser" | "redirect"> {
  if (typeof window === "undefined") return "redirect";

  if (Capacitor.isNativePlatform()) {
    try {
      const { Browser } = await import("@capacitor/browser");
      await Browser.open({ url: authorizeUrl, presentationStyle: "popover" });
      return "browser";
    } catch {
      // fall through
    }
  }

  // Desktop/PWA: popup keeps StudyFlows open; Google redirects the popup to our callback.
  const popup = window.open(authorizeUrl, "studyflows-google-oauth", "width=520,height=720,menubar=no,toolbar=no");
  if (popup) {
    return "browser";
  }

  window.location.href = authorizeUrl;
  return "redirect";
}
