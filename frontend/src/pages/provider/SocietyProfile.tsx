import { useEffect, useState } from "react";
import { Alert, Badge, ErrorMessage, Field, Loading, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { dateOnly } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { Society } from "../../lib/types";

interface Agreement {
  id: string;
  start_date: string;
  end_date: string | null;
  revenue_share_percent: string;
  parking_space_count: number | null;
  status: string;
  notes: string | null;
}

export default function SocietyProfile() {
  const { provider, refreshUser } = useAuth();
  const isSociety = provider?.provider_type === "SOCIETY";

  const society = useAsync(
    (signal) => (isSociety ? api.get<Society>("/providers/me/society", undefined, signal) : Promise.resolve(null)),
    [isSociety],
  );
  const agreements = useAsync(
    (signal) =>
      isSociety
        ? api.get<Agreement[]>("/providers/me/society/agreements", undefined, signal)
        : Promise.resolve([]),
    [isSociety],
  );

  const [form, setForm] = useState({
    name: "",
    registration_number: "",
    address: "",
    city: "",
    contact_name: "",
    contact_phone: "",
    contact_email: "",
    description: "",
  });
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    const data = society.data;
    if (!data) return;
    setForm({
      name: data.name,
      registration_number: data.registration_number ?? "",
      address: data.address ?? "",
      city: data.city ?? "",
      contact_name: data.contact_name ?? "",
      contact_phone: data.contact_phone ?? "",
      contact_email: data.contact_email ?? "",
      description: data.description ?? "",
    });
  }, [society.data]);

  const save = useSubmit(async () => {
    await api.patch("/providers/me/society", {
      name: form.name.trim(),
      registration_number: form.registration_number.trim() || null,
      address: form.address.trim() || null,
      city: form.city.trim() || null,
      contact_name: form.contact_name.trim() || null,
      contact_phone: form.contact_phone.trim() || null,
      contact_email: form.contact_email.trim() || null,
      description: form.description.trim() || null,
    });
    await refreshUser();
    setSaved(true);
  });

  // Verification is common to every provider, society or not.
  const [verification, setVerification] = useState({ phone: "", address: "", declared: false });
  const submitVerification = useSubmit(async () => {
    await api.post("/providers/me/verification", {
      contact_phone: verification.phone.trim(),
      address: verification.address.trim(),
      authority_declaration: verification.declared,
    });
    await refreshUser();
  });

  if (!provider) return <Loading />;

  return (
    <main className="page page--narrow">
      <div className="stack">
        <h1>{isSociety ? "Society profile" : "Provider profile"}</h1>

        <Panel title="Verification">
          <div className="stack">
            <div className="row">
              <span className="small muted" style={{ minWidth: 100 }}>
                Status
              </span>
              <Badge
                tone={
                  provider.verification_status === "VERIFIED"
                    ? "green"
                    : provider.verification_status === "REJECTED"
                      ? "red"
                      : "amber"
                }
              >
                {provider.verification_status.replace(/_/g, " ")}
              </Badge>
            </div>

            {provider.verification_status === "VERIFIED" ? (
              <Alert kind="success">
                Your account is verified. Renters see a verified badge on your listings.
              </Alert>
            ) : provider.verification_status === "PENDING_VERIFICATION" ? (
              <Alert kind="info">
                We have your details and are reviewing them. You can keep listing in the meantime.
              </Alert>
            ) : (
              <form
                className="stack"
                onSubmit={(event) => {
                  event.preventDefault();
                  void submitVerification.run();
                }}
              >
                <ErrorMessage error={submitVerification.error} />
                <p className="small muted" style={{ margin: 0 }}>
                  Verification builds trust with renters. It takes a minute.
                </p>
                <Field label="Contact phone" required>
                  <input
                    type="tel"
                    required
                    value={verification.phone}
                    onChange={(event) => setVerification({ ...verification, phone: event.target.value })}
                  />
                </Field>
                <Field label="Address" required>
                  <input
                    type="text"
                    required
                    minLength={5}
                    value={verification.address}
                    onChange={(event) => setVerification({ ...verification, address: event.target.value })}
                  />
                </Field>
                <label className="checkbox">
                  <input
                    type="checkbox"
                    checked={verification.declared}
                    onChange={(event) =>
                      setVerification({ ...verification, declared: event.target.checked })
                    }
                  />
                  <span>
                    I confirm that I have the necessary rights or authorization to offer these
                    parking spaces for rent.
                  </span>
                </label>
                <button
                  type="submit"
                  className="btn"
                  disabled={submitVerification.pending || !verification.declared}
                >
                  {submitVerification.pending ? "Submitting…" : "Submit for verification"}
                </button>
              </form>
            )}
          </div>
        </Panel>

        {isSociety ? (
          <>
            <Panel title="Society details">
              {society.loading ? (
                <Loading />
              ) : (
                <form
                  className="stack"
                  onSubmit={(event) => {
                    event.preventDefault();
                    setSaved(false);
                    void save.run();
                  }}
                >
                  <ErrorMessage error={save.error} />
                  {saved ? <Alert kind="success">Society details saved.</Alert> : null}
                  <Field label="Society name" required>
                    <input
                      type="text"
                      required
                      value={form.name}
                      onChange={(event) => setForm({ ...form, name: event.target.value })}
                    />
                  </Field>
                  <Field label="Registration number">
                    <input
                      type="text"
                      value={form.registration_number}
                      onChange={(event) => setForm({ ...form, registration_number: event.target.value })}
                    />
                  </Field>
                  <Field label="Address">
                    <input
                      type="text"
                      value={form.address}
                      onChange={(event) => setForm({ ...form, address: event.target.value })}
                    />
                  </Field>
                  <Field label="City">
                    <input
                      type="text"
                      value={form.city}
                      onChange={(event) => setForm({ ...form, city: event.target.value })}
                    />
                  </Field>
                  <div className="row" style={{ gap: "0.75rem" }}>
                    <div style={{ flex: 1 }}>
                      <Field label="Contact person">
                        <input
                          type="text"
                          value={form.contact_name}
                          onChange={(event) => setForm({ ...form, contact_name: event.target.value })}
                        />
                      </Field>
                    </div>
                    <div style={{ flex: 1 }}>
                      <Field label="Contact phone">
                        <input
                          type="tel"
                          value={form.contact_phone}
                          onChange={(event) => setForm({ ...form, contact_phone: event.target.value })}
                        />
                      </Field>
                    </div>
                  </div>
                  <Field label="Contact email">
                    <input
                      type="email"
                      value={form.contact_email}
                      onChange={(event) => setForm({ ...form, contact_email: event.target.value })}
                    />
                  </Field>
                  <Field label="About the society">
                    <textarea
                      rows={3}
                      value={form.description}
                      onChange={(event) => setForm({ ...form, description: event.target.value })}
                    />
                  </Field>
                  <button type="submit" className="btn" disabled={save.pending}>
                    {save.pending ? "Saving…" : "Save details"}
                  </button>
                </form>
              )}
            </Panel>

            <Panel title="Commercial agreement">
              {agreements.loading ? (
                <Loading />
              ) : !agreements.data?.length ? (
                <p className="small muted" style={{ margin: 0 }}>
                  No agreement is on record yet. The ParkSpace team records the agreed revenue share
                  here once it is signed; until then the standard commission applies.
                </p>
              ) : (
                <div className="stack">
                  {agreements.data.map((agreement) => (
                    <div className="stack stack--sm" key={agreement.id}>
                      <div className="row">
                        <Badge tone={agreement.status === "ACTIVE" ? "green" : ""}>
                          {agreement.status}
                        </Badge>
                        <span className="small">
                          Your share: <strong>{Number(agreement.revenue_share_percent)}%</strong>
                        </span>
                      </div>
                      <div className="small muted">
                        {dateOnly(agreement.start_date)} →{" "}
                        {agreement.end_date ? dateOnly(agreement.end_date) : "ongoing"}
                        {agreement.parking_space_count
                          ? ` · ${agreement.parking_space_count} spaces`
                          : ""}
                      </div>
                      {agreement.notes ? <div className="small">{agreement.notes}</div> : null}
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </>
        ) : null}
      </div>
    </main>
  );
}
