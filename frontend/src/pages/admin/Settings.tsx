/**
 * Platform business rules (PRD §10, §15, §33).
 *
 * Every number here is stored in the database, not hard-coded, so commission,
 * fees and the cancellation policy can change without a deploy.
 */
import { useEffect, useState } from "react";
import AdminNav from "../../components/AdminNav";
import { Alert, ErrorMessage, Field, Loading, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { PlatformConfig } from "../../lib/types";

export default function Settings() {
  const { data, error, loading, reload } = useAsync(
    (signal) => api.get<PlatformConfig>("/admin/settings", undefined, signal),
    [],
  );
  const [config, setConfig] = useState<PlatformConfig | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (data) setConfig(data);
  }, [data]);

  const save = useSubmit(async () => {
    if (!config) return;
    await api.patch("/admin/settings", config);
    setSaved(true);
    reload();
  });

  if (loading || !config) return <Loading />;

  const set = <K extends keyof PlatformConfig>(key: K, value: PlatformConfig[K]) =>
    setConfig({ ...config, [key]: value });

  const setTier = (index: number, patch: { min_hours_before?: number; refund_percent?: number }) => {
    const tiers = config.cancellation_policy.tiers.map((tier, i) =>
      i === index ? { ...tier, ...patch } : tier,
    );
    set("cancellation_policy", { ...config.cancellation_policy, tiers });
  };

  return (
    <main className="page page--wide">
      <h1>Admin</h1>
      <AdminNav />

      <div className="stack">
        <ErrorMessage error={error} />
        <ErrorMessage error={save.error} />
        {saved ? <Alert kind="success">Settings saved. They apply to new bookings.</Alert> : null}

        <Alert kind="info">
          Changing these affects future bookings only. Money already quoted on an existing booking
          is frozen at the rates that applied when it was made.
        </Alert>

        <div className="grid grid--2">
          <Panel title="Fees and commission">
            <div className="stack">
              <Field
                label="Platform fee charged to the renter (%)"
                hint="Added on top of the parking price."
              >
                <input
                  type="number"
                  min={0}
                  max={100}
                  step="0.1"
                  value={config.renter_fee_percent}
                  onChange={(event) => set("renter_fee_percent", Number(event.target.value))}
                />
              </Field>
              <Field label="Tax on that fee (%)" hint="For example GST at 18%.">
                <input
                  type="number"
                  min={0}
                  max={100}
                  step="0.1"
                  value={config.tax_percent}
                  onChange={(event) => set("tax_percent", Number(event.target.value))}
                />
              </Field>
              <Field
                label="Commission taken from the provider (%)"
                hint="Deducted from the parking price. Societies with an active agreement use their own share instead."
              >
                <input
                  type="number"
                  min={0}
                  max={100}
                  step="0.1"
                  value={config.commission_percent}
                  onChange={(event) => set("commission_percent", Number(event.target.value))}
                />
              </Field>

              <div className="card" style={{ background: "var(--bg-subtle)" }}>
                <div className="small bold" style={{ marginBottom: "0.4rem" }}>
                  On a ₹1,000 booking
                </div>
                <div className="summary__line small">
                  <span>Renter pays</span>
                  <span className="numeric">
                    ₹
                    {(
                      1000 +
                      (1000 * config.renter_fee_percent) / 100 +
                      ((1000 * config.renter_fee_percent) / 100) * (config.tax_percent / 100)
                    ).toFixed(2)}
                  </span>
                </div>
                <div className="summary__line small">
                  <span>Provider receives</span>
                  <span className="numeric">
                    ₹{(1000 - (1000 * config.commission_percent) / 100).toFixed(2)}
                  </span>
                </div>
                <div className="summary__line small bold">
                  <span>Platform keeps</span>
                  <span className="numeric">
                    ₹
                    {(
                      (1000 * config.commission_percent) / 100 +
                      (1000 * config.renter_fee_percent) / 100
                    ).toFixed(2)}
                  </span>
                </div>
              </div>
            </div>
          </Panel>

          <Panel title="Booking rules">
            <div className="stack">
              <Field
                label="Payment hold (minutes)"
                hint="How long an unpaid booking holds the slot before it is released."
              >
                <input
                  type="number"
                  min={1}
                  max={240}
                  value={config.payment_hold_minutes}
                  onChange={(event) => set("payment_hold_minutes", Number(event.target.value))}
                />
              </Field>
              <Field
                label="Provider approval window (hours)"
                hint="How long a provider has to accept a request on a manual-approval listing."
              >
                <input
                  type="number"
                  min={1}
                  max={168}
                  value={config.approval_window_hours}
                  onChange={(event) => set("approval_window_hours", Number(event.target.value))}
                />
              </Field>
              <Field label="Booking slot size (minutes)" hint="Hourly bookings must align to this. Must divide 60.">
                <select
                  value={config.booking_slot_minutes}
                  onChange={(event) => set("booking_slot_minutes", Number(event.target.value))}
                >
                  {[5, 10, 15, 20, 30, 60].map((value) => (
                    <option key={value} value={value}>
                      {value} minutes
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Maximum days in advance">
                <input
                  type="number"
                  min={1}
                  max={730}
                  value={config.booking_max_advance_days}
                  onChange={(event) => set("booking_max_advance_days", Number(event.target.value))}
                />
              </Field>
              <Field label="Minimum lead time (minutes)">
                <input
                  type="number"
                  min={0}
                  max={10080}
                  value={config.booking_min_lead_minutes}
                  onChange={(event) => set("booking_min_lead_minutes", Number(event.target.value))}
                />
              </Field>
              <Field label="Reminder sent this many hours before start">
                <input
                  type="number"
                  min={0}
                  max={72}
                  step="0.5"
                  value={config.reminder_hours_before}
                  onChange={(event) => set("reminder_hours_before", Number(event.target.value))}
                />
              </Field>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={config.listing_requires_approval}
                  onChange={(event) => set("listing_requires_approval", event.target.checked)}
                />
                <span>
                  New listings need admin approval before going live
                  <span className="field__hint" style={{ display: "block" }}>
                    Safer during the pilot; slower for providers.
                  </span>
                </span>
              </label>
            </div>
          </Panel>
        </div>

        <Panel title="Cancellation policy">
          <div className="stack">
            <p className="small muted" style={{ margin: 0 }}>
              A renter cancelling at least this many hours before the start gets this share back.
              Tiers are applied from the most generous downwards.
            </p>
            {config.cancellation_policy.tiers.map((tier, index) => (
              <div className="row" key={index} style={{ gap: "0.6rem" }}>
                <span className="small muted">Cancelling at least</span>
                <input
                  type="number"
                  min={0}
                  step="0.5"
                  value={tier.min_hours_before}
                  style={{ flex: "0 1 110px" }}
                  onChange={(event) => setTier(index, { min_hours_before: Number(event.target.value) })}
                />
                <span className="small muted">hours before refunds</span>
                <input
                  type="number"
                  min={0}
                  max={100}
                  value={tier.refund_percent}
                  style={{ flex: "0 1 110px" }}
                  onChange={(event) => setTier(index, { refund_percent: Number(event.target.value) })}
                />
                <span className="small muted">%</span>
              </div>
            ))}
            <Field label="Refund when no tier applies (%)">
              <input
                type="number"
                min={0}
                max={100}
                style={{ maxWidth: 140 }}
                value={config.cancellation_policy.default_refund_percent}
                onChange={(event) =>
                  set("cancellation_policy", {
                    ...config.cancellation_policy,
                    default_refund_percent: Number(event.target.value),
                  })
                }
              />
            </Field>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={config.cancellation_policy.allow_after_start}
                onChange={(event) =>
                  set("cancellation_policy", {
                    ...config.cancellation_policy,
                    allow_after_start: event.target.checked,
                  })
                }
              />
              <span>Allow renters to cancel after the booking has started</span>
            </label>
          </div>
        </Panel>

        <div className="row">
          <button
            type="button"
            className="btn"
            onClick={() => {
              setSaved(false);
              void save.run();
            }}
            disabled={save.pending}
          >
            {save.pending ? "Saving…" : "Save settings"}
          </button>
          <button type="button" className="btn btn--ghost" onClick={() => setConfig(data)}>
            Reset
          </button>
        </div>
      </div>
    </main>
  );
}
