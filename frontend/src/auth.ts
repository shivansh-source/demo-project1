// DEMO LOGIN ONLY. This is a front-end gate for the demo, not security: the credentials are
// public (they are shown on the login page) and the API itself has no authentication.
export const DEMO_EMAIL = "demo@leadqual.dev";
export const DEMO_PASSWORD = "demo1234";
const KEY = "leadqual.demo.session";

export function isLoggedIn(): boolean {
  try {
    return sessionStorage.getItem(KEY) === DEMO_EMAIL;
  } catch {
    return false;
  }
}

export function login(email: string, password: string): boolean {
  if (email.trim().toLowerCase() !== DEMO_EMAIL || password !== DEMO_PASSWORD) return false;
  try {
    sessionStorage.setItem(KEY, DEMO_EMAIL);
  } catch {
    /* sessionStorage unavailable: the session just will not persist across reloads */
  }
  return true;
}

export function logout(): void {
  try {
    sessionStorage.removeItem(KEY);
  } catch {
    /* ignore */
  }
}
