import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.studyflows.app",
  appName: "StudyFlows",
  webDir: ".next",
  server: {
    // TestFlight loads this remote URL. mystudyflow.app is blocked on TAMU OpenDNS —
    // use a trycloudflare tunnel (or other unblocked HTTPS) until a clean domain/VPS.
    // CI sets CAP_SERVER_URL; keep this default in sync with the live tunnel.
    url: process.env.CAP_SERVER_URL || "https://asian-spice-refrigerator-sunrise.trycloudflare.com",
    cleartext: false
  },
  ios: {
    contentInset: "automatic"
  }
};

export default config;
