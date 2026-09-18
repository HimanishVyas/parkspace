import { useState } from "react";
import { Link } from "react-router-dom";
import { Alert, Badge, ErrorMessage, Field, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateOnly } from "../../lib/format";
import { useSubmit } from "../../lib/hooks";
import type { User } from "../../lib/types";

export default function Profile() {
  const { user, provider, refreshUser } = useAuth();
  const [fullName, setFullName] = useState(user?.full_name ?? "");
  const [phone, setPhone] = useState(user?.phone ?? "");
  const [saved, setSaved] = useState(false);
  const [passwords, setPasswords] = useState({ current: "", next: "" });
  const [passwordSaved, setPasswordSaved] = useState(false);

  const save = useSubmit(async () => {
    await api.patch<User>("/me", { full_name: fullName.trim(), phone: phone.trim() || null });
    await refreshUser();
    setSaved(true);
  });

  const changePassword = useSubmit(async () => {
    await api.post("/me/password", {
      current_password: passwords.current,
      new_password: passwords.next,
    });
    setPasswords({ current: "", next: "" });
    setPasswordSaved(true);
  });

  const uploadPhoto = useSubmit(async (file: File) => {
    await api.upload<User>("/me/photo", file);
    await refreshUser();
  });

  if (!user) return null;

  return (
    <main className="page page--narrow">
      <div className="stack">
        <h1>Profile</h1>

        <Panel title="Your details">
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              setSaved(false);
              void save.run();
            }}
          >
            <ErrorMessage error={save.error} />
            {saved ? <Alert kind="success">Profile updated.</Alert> : null}

            <div className="row">
              <div
                style={{
                  width: 64,
                  height: 64,
                  borderRadius: "50%",
                  overflow: "hidden",
                  background: "var(--gray-100)",
                  display: "grid",
                  placeItems: "center",
                  flexShrink: 0,
                }}
              >
                {user.profile_photo_url ? (
                  <img
                    src={user.profile_photo_url}
                    alt=""
                    style={{ width: "100%", height: "100%", objectFit: "cover" }}
                  />
                ) : (
                  <span style={{ fontSize: "1.5rem" }}>{user.full_name.charAt(0).toUpperCase()}</span>
                )}
              </div>
              <label className="btn btn--secondary btn--sm" style={{ cursor: "pointer" }}>
                {uploadPhoto.pending ? "Uploading…" : "Change photo"}
                <input
                  type="file"
                  accept="image/jpeg,image/png,image/webp"
                  className="sr-only"
                  onChange={(event) => {
                    const file = event.target.files?.[0];
                    if (file) void uploadPhoto.run(file);
                  }}
                />
              </label>
            </div>
            <ErrorMessage error={uploadPhoto.error} />

            <Field label="Full name" required>
              <input
                type="text"
                value={fullName}
                required
                onChange={(event) => setFullName(event.target.value)}
              />
            </Field>
            <Field label="Email" hint="Contact support to change your email address.">
              <input type="email" value={user.email} disabled />
            </Field>
            <Field label="Phone">
              <input type="tel" value={phone} onChange={(event) => setPhone(event.target.value)} />
            </Field>
            <button type="submit" className="btn" disabled={save.pending}>
              {save.pending ? "Saving…" : "Save changes"}
            </button>
          </form>
        </Panel>

        <Panel title="Account">
          <div className="stack stack--sm">
            <div className="row">
              <span className="small muted" style={{ minWidth: 120 }}>
                Role
              </span>
              <Badge tone="teal">{user.role}</Badge>
              {provider ? (
                <Badge tone={provider.verification_status === "VERIFIED" ? "green" : "amber"}>
                  {provider.verification_status.replace("_", " ")}
                </Badge>
              ) : null}
            </div>
            <div className="row">
              <span className="small muted" style={{ minWidth: 120 }}>
                Member since
              </span>
              <span className="small">{dateOnly(user.created_at)}</span>
            </div>
          </div>
          <div className="row" style={{ marginTop: "1rem" }}>
            <Link to="/vehicles" className="btn btn--secondary btn--sm">
              My vehicles
            </Link>
            {provider ? (
              <Link to="/provider" className="btn btn--secondary btn--sm">
                Provider dashboard
              </Link>
            ) : (
              <Link to="/list-your-space" className="btn btn--secondary btn--sm">
                List your parking
              </Link>
            )}
          </div>
        </Panel>

        <Panel title="Change password">
          <form
            className="stack"
            onSubmit={(event) => {
              event.preventDefault();
              setPasswordSaved(false);
              void changePassword.run();
            }}
          >
            <ErrorMessage error={changePassword.error} />
            {passwordSaved ? (
              <Alert kind="success">
                Password changed. You have been signed out of other devices.
              </Alert>
            ) : null}
            <Field label="Current password" required>
              <input
                type="password"
                required
                autoComplete="current-password"
                value={passwords.current}
                onChange={(event) => setPasswords({ ...passwords, current: event.target.value })}
              />
            </Field>
            <Field label="New password" required hint="At least 8 characters.">
              <input
                type="password"
                required
                minLength={8}
                autoComplete="new-password"
                value={passwords.next}
                onChange={(event) => setPasswords({ ...passwords, next: event.target.value })}
              />
            </Field>
            <button type="submit" className="btn btn--secondary" disabled={changePassword.pending}>
              {changePassword.pending ? "Updating…" : "Update password"}
            </button>
          </form>
        </Panel>
      </div>
    </main>
  );
}
