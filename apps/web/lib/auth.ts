const TOKEN_KEY = "aos_access_token";
const USER_KEY = "aos_auth_user";

export type AuthUser = {
  id: string;
  email: string;
  name?: string | null;
};

export function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function getStoredAuthUser(): AuthUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(USER_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AuthUser;
  } catch {
    return null;
  }
}

export function setAuthSession(accessToken: string, user: AuthUser) {
  localStorage.setItem(TOKEN_KEY, accessToken);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
  window.dispatchEvent(new Event("aos-auth-changed"));
}

export function clearAuthSession() {
  try {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  } catch {
    // ignore
  }
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event("aos-auth-changed"));
  }
}

export function isBearerAuthMode(): boolean {
  const mode = (process.env.NEXT_PUBLIC_API_AUTH_MODE || "").trim().toLowerCase();
  return mode === "bearer";
}
