import { useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { ErrorMessage, Field } from "../components/ui";
import { useAuth } from "../lib/auth";
import { useSubmit } from "../lib/hooks";

export default function Register() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const [params] = useSearchParams();

  // The landing page links here with the intent pre-selected.
  const [role, setRole] = useState<"RENTER" | "PROVIDER">(
    params.get("role") === "provider" ? "PROVIDER" : "RENTER",
  );
  const [providerType, setProviderType] = useState<"INDIVIDUAL" | "SOCIETY">(
    params.get("type") === "society" ? "SOCIETY" : "INDIVIDUAL",
  );
  const [form, setForm] = useState({
    full_name: "",
    email: "",
    phone: "",
    password: "",
    organization_name: "",
  });

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((current) => ({ ...current, [key]: event.target.value }));

  const { run, pending, error } = useSubmit(async () => {
    const user = await register({
      full_name: form.full_name.trim(),
      email: form.email.trim(),
      password: form.password,
      phone: form.phone.trim() || undefined,
      role,
      provider_type: role === "PROVIDER" ? providerType : undefined,
      organization_name:
        role === "PROVIDER" && providerType === "SOCIETY" ? form.organization_name.trim() : undefined,
    });
    navigate(user.role === "PROVIDER" ? "/provider" : "/search", { replace: true });
  });

  const fieldErrors = error?.fieldErrors ?? {};

  return (
    <main className="page page--narrow">
      <div className="card stack">
        <div>
          <h1>Create your account</h1>
          <p className="muted small">One account covers both renting and listing parking.</p>
        </div>

        <div className="stack stack--sm">
          <span className="field__label">I want to</span>
          <div className="chips">
            <button
              type="button"
              className={`chip${role === "RENTER" ? " chip--on" : ""}`}
              onClick={() => setRole("RENTER")}
            >
              Find parking
            </button>
            <button
              type="button"
              className={`chip${role === "PROVIDER" ? " chip--on" : ""}`}
              onClick={() => setRole("PROVIDER")}
            >
              List my parking
            </button>
          </div>
        </div>

        {role === "PROVIDER" ? (
          <div className="stack stack--sm">
            <span className="field__label">I am listing as</span>
            <div className="chips">
              <button
                type="button"
                className={`chip${providerType === "INDIVIDUAL" ? " chip--on" : ""}`}
                onClick={() => setProviderType("INDIVIDUAL")}
              >
                An individual
              </button>
              <button
                type="button"
                className={`chip${providerType === "SOCIETY" ? " chip--on" : ""}`}
                onClick={() => setProviderType("SOCIETY")}
              >
                A society or organisation
              </button>
            </div>
          </div>
        ) : null}

        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            void run();
          }}
        >
          <ErrorMessage error={error} />

          {role === "PROVIDER" && providerType === "SOCIETY" ? (
            <Field label="Society / organisation name" required error={fieldErrors.organization_name}>
              <input
                type="text"
                value={form.organization_name}
                required
                onChange={set("organization_name")}
                placeholder="Green Acres Co-operative Housing Society"
              />
            </Field>
          ) : null}

          <Field label="Full name" required error={fieldErrors.full_name}>
            <input type="text" value={form.full_name} required autoComplete="name" onChange={set("full_name")} />
          </Field>
          <Field label="Email" required error={fieldErrors.email}>
            <input type="email" value={form.email} required autoComplete="email" onChange={set("email")} />
          </Field>
          <Field
            label="Phone"
            hint="Optional, but it helps providers reach you about a booking."
            error={fieldErrors.phone}
          >
            <input
              type="tel"
              value={form.phone}
              autoComplete="tel"
              onChange={set("phone")}
              placeholder="98765 43210"
            />
          </Field>
          <Field label="Password" required hint="At least 8 characters." error={fieldErrors.password}>
            <input
              type="password"
              value={form.password}
              required
              minLength={8}
              autoComplete="new-password"
              onChange={set("password")}
            />
          </Field>

          <button type="submit" className="btn btn--block" disabled={pending}>
            {pending ? "Creating account…" : "Create account"}
          </button>
        </form>

        <p className="small muted center" style={{ margin: 0 }}>
          Already have an account? <Link to="/login">Sign in</Link>
        </p>
      </div>
    </main>
  );
}
