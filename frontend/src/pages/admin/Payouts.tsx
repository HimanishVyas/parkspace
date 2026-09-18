import { useState } from "react";
import AdminNav from "../../components/AdminNav";
import { Badge, Empty, ErrorMessage, Field, Loading, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { dateOnly, money } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { AdminProvider, Paginated, Payout } from "../../lib/types";

export default function Payouts() {
  const [providerId, setProviderId] = useState("");
  const [reference, setReference] = useState<Record<string, string>>({});

  const providers = useAsync(
    (signal) =>
      api.get<Paginated<AdminProvider>>("/admin/providers", { limit: 100 }, signal),
    [],
  );
  const payouts = useAsync(
    (signal) => api.get<Payout[]>("/admin/payouts", { limit: 50 }, signal),
    [],
  );

  const create = useSubmit(async () => {
    await api.post("/admin/payouts", { provider_id: providerId });
    payouts.reload();
  });

  const markPaid = useSubmit(async (id: string) => {
    await api.post(`/admin/payouts/${id}/paid`, { reference: reference[id]?.trim() || undefined });
    payouts.reload();
  });

  const providerName = (id: string) =>
    providers.data?.items.find((provider) => provider.id === id)?.display_name ?? id.slice(0, 8);

  return (
    <main className="page page--wide">
      <h1>Admin</h1>
      <AdminNav />

      <div className="stack">
        <Panel title="Create a payout">
          <p className="small muted">
            Bundles every completed booking not yet settled for that provider into one payout.
            Record the bank reference once you have actually sent the money.
          </p>
          <ErrorMessage error={create.error} />
          <form
            className="row"
            style={{ alignItems: "flex-end", gap: "0.6rem" }}
            onSubmit={(event) => {
              event.preventDefault();
              void create.run();
            }}
          >
            <div style={{ flex: "1 1 300px" }}>
              <Field label="Provider" required>
                <select
                  value={providerId}
                  required
                  onChange={(event) => setProviderId(event.target.value)}
                >
                  <option value="">Choose a provider…</option>
                  {providers.data?.items.map((provider) => (
                    <option key={provider.id} value={provider.id}>
                      {provider.display_name} · {money(provider.total_earnings)} earned
                    </option>
                  ))}
                </select>
              </Field>
            </div>
            <button type="submit" className="btn" disabled={!providerId || create.pending}>
              {create.pending ? "Creating…" : "Create payout"}
            </button>
          </form>
        </Panel>

        <ErrorMessage error={payouts.error} />
        <ErrorMessage error={markPaid.error} />

        <Panel title="Payouts" flush>
          {payouts.loading ? (
            <Loading />
          ) : !payouts.data?.length ? (
            <Empty title="No payouts yet">
              Create one once providers have completed bookings.
            </Empty>
          ) : (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Provider</th>
                    <th className="numeric">Amount</th>
                    <th className="numeric">Bookings</th>
                    <th>Period</th>
                    <th>Status</th>
                    <th>Reference</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {payouts.data.map((payout) => (
                    <tr key={payout.id}>
                      <td className="small">{providerName(payout.provider_id)}</td>
                      <td className="numeric bold">{money(payout.amount)}</td>
                      <td className="numeric">{payout.booking_count}</td>
                      <td className="small muted">
                        {payout.period_start ? dateOnly(payout.period_start) : "—"} →{" "}
                        {payout.period_end ? dateOnly(payout.period_end) : "—"}
                      </td>
                      <td>
                        <Badge tone={payout.status === "PAID" ? "green" : "amber"}>
                          {payout.status}
                        </Badge>
                      </td>
                      <td>
                        {payout.status === "PAID" ? (
                          <span className="small numeric">{payout.reference ?? "—"}</span>
                        ) : (
                          <input
                            type="text"
                            placeholder="UTR / reference"
                            value={reference[payout.id] ?? ""}
                            style={{ minHeight: 34, fontSize: "0.85rem" }}
                            onChange={(event) =>
                              setReference({ ...reference, [payout.id]: event.target.value })
                            }
                          />
                        )}
                      </td>
                      <td>
                        {payout.status !== "PAID" ? (
                          <button
                            type="button"
                            className="btn btn--sm"
                            onClick={() => void markPaid.run(payout.id)}
                            disabled={markPaid.pending}
                          >
                            Mark paid
                          </button>
                        ) : (
                          <span className="tiny muted">{dateOnly(payout.paid_at)}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Panel>
      </div>
    </main>
  );
}
