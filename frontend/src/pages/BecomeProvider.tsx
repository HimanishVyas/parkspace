import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Alert, ErrorMessage, Field } from "../components/ui";
import { useAuth } from "../lib/auth";
import { useSubmit } from "../lib/hooks";

/** Turns an existing account into a provider, or points a visitor at signup. */
export default function BecomeProvider() {
  const { user, provider, becomeProvider } = useAuth();
  const navigate = useNavigate();
  const [providerType, setProviderType] = useState<"INDIVIDUAL" | "SOCIETY">("INDIVIDUAL");
  const [organizationName, setOrganizationName] = useState("");

  const { run, pending, error } = useSubmit(async () => {
    await becomeProvider({
      provider_type: providerType,
      organization_name: providerType === "SOCIETY" ? organizationName.trim() : undefined,
    });
    navigate("/provider/listings/new");
  });

  if (provider) {
    return (
      <main className="page page--narrow">
        <div className="card stack">
          <h1>You are already set up</h1>
          <p className="muted">Your provider account is ready. Add a parking space to start earning.</p>
          <Link to="/provider/listings/new" className="btn">
            Add a parking space
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="page page--narrow">
      <div className="card stack">
        <div>
          <h1>List your parking</h1>
          <p className="muted small">
            It takes a few minutes: describe the space, set a price and your hours, and publish.
          </p>
        </div>

        <ul className="small muted stack stack--sm" style={{ paddingLeft: "1.1rem", margin: 0 }}>
          <li>You set the price per hour, day or month.</li>
          <li>You decide the hours it is available and can block dates any time.</li>
          <li>Existing bookings automatically stop anyone else booking that slot.</li>
        </ul>

        {!user ? (
          <>
            <Alert kind="info">Create an account to list a parking space.</Alert>
            <div className="row">
              <Link to="/register?role=provider" className="btn">
                Create a provider account
              </Link>
              <Link to="/login" className="btn btn--secondary">
                I already have an account
              </Link>
            </div>
          </>
        ) : (
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              void run();
            }}
          >
            <ErrorMessage error={error} />
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
            {providerType === "SOCIETY" ? (
              <Field label="Society / organisation name" required>
                <input
                  type="text"
                  value={organizationName}
                  required
                  onChange={(event) => setOrganizationName(event.target.value)}
                />
              </Field>
            ) : null}
            <button type="submit" className="btn btn--block" disabled={pending}>
              {pending ? "Setting up…" : "Continue"}
            </button>
          </form>
        )}
      </div>
    </main>
  );
}
