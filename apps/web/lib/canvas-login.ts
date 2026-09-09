import { Capacitor, registerPlugin } from "@capacitor/core";

export type CanvasLoginResult = {
  sessionCookie: string;
  baseUrl: string;
};

type CanvasLoginPlugin = {
  loginAndCaptureSession(options: { baseUrl: string }): Promise<CanvasLoginResult>;
};

const CanvasLogin = registerPlugin<CanvasLoginPlugin>("CanvasLogin");

export function canAutoCaptureCanvasSession(): boolean {
  return Capacitor.isNativePlatform();
}

export async function captureCanvasSession(baseUrl: string): Promise<CanvasLoginResult> {
  if (!Capacitor.isNativePlatform()) {
    throw new Error(
      "Automatic Canvas sign-in works in the StudyFlows iPad app. On the web, paste a session cookie or use OAuth when a developer key is available."
    );
  }
  return CanvasLogin.loginAndCaptureSession({ baseUrl });
}
