export type Session = {
  email: string;
  role: string;
  displayName: string;
};

export const SESSION_KEY = "secmate.demo.session";

export function createSession(username: string, password: string): Session | null {
  const normalizedUsername = username.trim();
  if (!normalizedUsername || !password) return null;

  return {
    email: normalizedUsername,
    displayName: normalizedUsername,
    role: "Local Preview",
  };
}

export function readSession(): Session | null {
  const storedSession = window.localStorage.getItem(SESSION_KEY);
  if (!storedSession) return null;

  try {
    const session = JSON.parse(storedSession) as Session;
    if (session.email && session.displayName && session.role) return session;
  } catch {
    // Preserve sessions created by the previous email-only local preview.
    return {
      email: storedSession,
      displayName: storedSession,
      role: "Local Preview",
    };
  }

  window.localStorage.removeItem(SESSION_KEY);
  return null;
}

export function saveSession(session: Session) {
  window.localStorage.setItem(SESSION_KEY, JSON.stringify(session));
}

export function clearSession() {
  window.localStorage.removeItem(SESSION_KEY);
}
