import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { ErrorMessage, Field } from "../components/ui";
import { useAuth } from "../lib/auth";
import { homeFor, portalFor } from "../lib/portal";
import { useSubmit } from "../lib/hooks";

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");

  const from = (location.state as { from?: string } | null)?.from ?? "/";
  const { run, pending, error } = useSubmit(async () => {
    const user = await login(identifier.trim(), password);
    // Honour where they were headed; otherwise send them to their own portal
    // rather than the marketing page. `login` resolves the provider profile
    // before returning, so the role is already accurate here.
    const home = homeFor(portalFor(user, null));
    navigate(from !== "/" ? from : home, { replace: true });
  });

  return (
    <main className="page page--narrow">
      <div className="card stack">
        <div>
          <h1>Sign in</h1>
          <p className="muted small">Use the email address or phone number you registered with.</p>
        </div>
        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            void run();
          }}
        >
          <ErrorMessage error={error} />
          <Field label="Email or phone" required>
            <input
              type="text"
              value={identifier}
              autoComplete="username"
              autoFocus
              required
              onChange={(event) => setIdentifier(event.target.value)}
            />
          </Field>
          <Field label="Password" required>
            <input
              type="password"
              value={password}
              autoComplete="current-password"
              required
              onChange={(event) => setPassword(event.target.value)}
            />
          </Field>
          <button type="submit" className="btn btn--block" disabled={pending}>
            {pending ? "Signing in…" : "Sign in"}
          </button>
        </form>
        <p className="small muted center" style={{ margin: 0 }}>
          New here? <Link to="/register">Create an account</Link>
        </p>
      </div>
    </main>
  );
}
