import { useState } from "react";
import { DEMO_EMAIL, DEMO_PASSWORD, login } from "../auth";

export function LoginPage({ onSuccess }: { onSuccess: () => void }) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);

  function submit(e: React.FormEvent) {
    e.preventDefault();
    if (login(email, password)) onSuccess();
    else setError("Wrong email or password. Use the demo account below.");
  }

  function useDemo() {
    if (login(DEMO_EMAIL, DEMO_PASSWORD)) onSuccess();
  }

  return (
    <div className="auth-wrap">
      <form className="card auth-card" onSubmit={submit}>
        <h2>Sign in</h2>
        <p className="muted">Sign in to open the lead dashboard.</p>
        <label className="field">
          Email
          <input type="email" value={email} onChange={(e) => setEmail(e.target.value)} autoComplete="username" />
        </label>
        <label className="field">
          Password
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" />
        </label>
        {error && <p className="error">{error}</p>}
        <button className="btn-primary" type="submit">
          Sign in
        </button>
        <div className="demo-box">
          <strong>Demo account</strong>
          <div className="mono">{DEMO_EMAIL}</div>
          <div className="mono">{DEMO_PASSWORD}</div>
          <button type="button" className="btn-outline" onClick={useDemo}>
            Continue with the demo account
          </button>
          <p className="muted small">
            Demo only: this gate lives in the browser and the API has no authentication.
          </p>
        </div>
      </form>
    </div>
  );
}
