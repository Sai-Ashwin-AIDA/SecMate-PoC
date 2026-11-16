import { useState } from "react";
import type { FormEvent, ReactNode } from "react";
import type { Session } from "./auth";

type LoginPageProps = {
  onLogin: (email: string, password: string) => Promise<Session | null>;
};

type IconProps = {
  children: ReactNode;
  className?: string;
  viewBox?: string;
};

function Icon({ children, className = "", viewBox = "0 0 24 24" }: IconProps) {
  return (
    <svg
      aria-hidden="true"
      className={className}
      fill="none"
      viewBox={viewBox}
      xmlns="http://www.w3.org/2000/svg"
    >
      {children}
    </svg>
  );
}

function ShieldLogo() {
  return (
    <Icon className="brand-shield" viewBox="0 0 54 64">
      <path d="M27 2 50 10v17c0 15.5-9.2 27.2-23 34C13.2 54.2 4 42.5 4 27V10L27 2Z" fill="rgba(0,145,255,.13)" stroke="#159bff" strokeWidth="3" />
      <path d="m27 10 15 5.1v12.2c0 10.4-5.8 18.8-15 24.4V10Z" fill="#087ff0" opacity=".75" />
      <path d="M27 10 12 15.1v12.2c0 10.4 5.8 18.8 15 24.4V10Z" fill="#159bff" opacity=".38" />
      <path d="M27 10 42 15.1v12.2c0 10.4-5.8 18.8-15 24.4-9.2-5.6-15-14-15-24.4V15.1L27 10Z" stroke="#42b8ff" strokeWidth="1.5" />
    </Icon>
  );
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setError("");
    setNotice("");

    const normalizedUsername = username.trim();

    if (!normalizedUsername || !password) {
      setError("Enter a username and password to continue.");
      return;
    }

    setSubmitting(true);
    try {
      if (!await onLogin(normalizedUsername, password)) setError("Unable to sign in with those local credentials.");
    } catch {
      setError("Sign-in is temporarily unavailable. Try again.");
    } finally {
      setSubmitting(false);
    }
  };

  const showUnavailableMessage = () => {
    setError("");
    setNotice("Enterprise SSO is not connected. This PoC uses local authentication.");
  };

  return (
    <main className="login-screen">
      <section className="brand-section" aria-label="SecMate introduction">
        <div className="brand-lockup">
          <ShieldLogo />
          <div>
            <div className="brand-name">SecMate</div>
            <div className="brand-tagline">Secure AI. Trust what runs.</div>
          </div>
        </div>

        <div className="environment-pills" aria-label="Environment status">
          <span className="status-pill"><span className="status-dot" />SecMate PoC</span>
          <span className="gateway-pill">Local access</span>
        </div>

        <div className="hero-copy">
          <h1>
            Review AI agent security
            <span>with clarity and control.</span>
          </h1>
          <p>
            Explore guardrails, action-space behavior, and advisory findings
            for authorized internal Targets in one controlled workspace.
          </p>
        </div>
      </section>

      <section className="login-panel" aria-labelledby="login-heading">
        <a className="support-link" href="mailto:support@paramountcs.com">
          <Icon className="support-icon">
            <path d="M4 13v-1a8 8 0 0 1 16 0v1" stroke="currentColor" strokeLinecap="round" strokeWidth="1.8" />
            <path d="M5 12H4a2 2 0 0 0-2 2v3a2 2 0 0 0 2 2h2v-7H5Zm14 0h1a2 2 0 0 1 2 2v3a2 2 0 0 1-2 2h-2v-7h1ZM18 19c-.5 1.3-1.6 2-3.2 2H13" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.8" />
          </Icon>
          <span>Contact support</span>
        </a>

        <header className="login-heading">
          <h2 id="login-heading">Sign in</h2>
          <p>Enter a username and password for local PoC access. Enterprise SSO is not connected.</p>
        </header>

        <form onSubmit={submit} className="login-form" noValidate>
          <label>
            <span>Username</span>
            <div className="input-shell">
              <Icon className="field-icon">
                <rect x="3" y="5" width="18" height="14" rx="2" stroke="currentColor" strokeWidth="1.7" />
                <path d="m4 7 8 6 8-6" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
              </Icon>
              <input
                aria-invalid={Boolean(error)}
                disabled={submitting}
                type="text"
                value={username}
                onChange={(event) => setUsername(event.target.value)}
                placeholder="Enter a local username"
                autoComplete="username"
              />
            </div>
          </label>

          <label>
            <span>Password</span>
            <div className="input-shell password-field">
              <Icon className="field-icon">
                <rect x="4" y="10" width="16" height="11" rx="2" stroke="currentColor" strokeWidth="1.7" />
                <path d="M8 10V7a4 4 0 0 1 8 0v3" stroke="currentColor" strokeLinecap="round" strokeWidth="1.7" />
              </Icon>
              <input
                aria-invalid={Boolean(error)}
                disabled={submitting}
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                placeholder="Enter your password"
                autoComplete="current-password"
              />
              <button
                aria-label={showPassword ? "Hide password" : "Show password"}
                className="password-toggle"
                disabled={submitting}
                type="button"
                onClick={() => setShowPassword((value) => !value)}
              >
                <Icon>
                  <path d="M2.5 12s3.5-5 9.5-5 9.5 5 9.5 5-3.5 5-9.5 5-9.5-5-9.5-5Z" stroke="currentColor" strokeLinejoin="round" strokeWidth="1.7" />
                  <circle cx="12" cy="12" r="2.5" stroke="currentColor" strokeWidth="1.7" />
                </Icon>
              </button>
            </div>
          </label>

          <a className="forgot-link" href="mailto:security-admin@paramountcs.com">Need help signing in?</a>

          {error && <div className="form-error" role="alert">{error}</div>}
          {notice && <div className="form-notice" role="status">{notice}</div>}

          <button className="primary-button" disabled={submitting} type="submit">{submitting ? "Signing in..." : "Continue"}</button>

          <div className="divider"><span>or</span></div>

          <button className="sso-button" disabled={submitting} type="button" onClick={showUnavailableMessage}>
            <Icon className="sso-icon">
              <path d="M4 21h16M6 21V7l6-4 6 4v14M9 10h1m4 0h1m-6 4h1m4 0h1m-6 4h1m4 0h1" stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="1.7" />
            </Icon>
            <span className="sso-copy">
              <strong>Continue with SSO</strong>
              <small>Not connected; local access only</small>
            </span>
          </button>
        </form>

        <p className="admin-note">Need access? <a href="mailto:security-admin@paramountcs.com">Contact your administrator</a></p>
      </section>
    </main>
  );
}
