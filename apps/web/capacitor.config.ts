import type { CapacitorConfig } from "@capacitor/cli";

const config: CapacitorConfig = {
  appId: "com.studyflows.app",
  appName: "StudyFlows",
  webDir: ".next",
  server: {
    // Use hosted web URL for Linux-first flow; iOS shell remains thin.
    url: process.env.CAP_SERVER_URL || "https://app.mystudyflow.app",
    cleartext: false
  },
  ios: {
    contentInset: "automatic"
  }
};

export default config;
