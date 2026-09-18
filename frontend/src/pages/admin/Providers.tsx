import { useState } from "react";
import AdminNav from "../../components/AdminNav";
import { Badge, ConfirmButton, Empty, ErrorMessage, Loading, Pagination } from "../../components/ui";
import { api } from "../../lib/api";
import { dateOnly, money } from "../../lib/format";
import { useAsync, useDebounced, useSubmit } from "../../lib/hooks";
import type { AdminProvider, Paginated } from "../../lib/types";

const LIMIT = 20;

export default function Providers() {
  const [query, setQuery] = useState("");
  const [verification, setVerification] = useState("");
  const [offset, setOffset] = useState(0);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const search = useDebounced(query);

  const { data, error, loading, reload } = useAsync(
    (signal) =>
      api.get<Paginated<AdminProvider>>(
        "/admin/providers",
        { q: search || undefined, verification: verification || undefined, limit: LIMIT, offset },
        signal,
      ),
    [search, verification, offset],
  );

  const decide = useSubmit(async (id: string, status: string) => {
    await api.post(`/admin/providers/${id}/verification`, { status, notes: notes[id]?.trim() || undefined });
    reload();
  });

  const setStatus = useSubmit(async (id: string, status: "ACTIVE" | "SUSPENDED") => {
    await api.post(`/admin/providers/${id}/status`, { status, reason: notes[id]?.trim() || undefined });
    reload();
  });

  return (
    <main className="page page--wide">
      <h1>Admin</h1>
      <AdminNav />

      <div className="stack">
        <div className="row">
          <input
            type="search"
            placeholder="Search provider name"
            value={query}
            style={{ flex: "1 1 240px" }}
            onChange={(event) => {
              setQuery(event.target.value);
              setOffset(0);
            }}
          />
          <select
            value={verification}
            style={{ flex: "0 1 220px" }}
            onChange={(event) => {
              setVerification(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All verification states</option>
            <option value="PENDING_VERIFICATION">Pending verification</option>
            <option value="VERIFIED">Verified</option>
            <option value="UNVERIFIED">Unverified</option>
            <option value="REJECTED">Rejected</option>
          </select>
        </div>

        <ErrorMessage error={error} />
        <ErrorMessage error={decide.error} />
        <ErrorMessage error={setStatus.error} />

        {loading ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty title="No providers matched" />
        ) : (
          <>
            <div className="stack">
              {data.items.map((provider) => (
                <div className="panel panel__body" key={provider.id}>
                  <div className="stack">
                    <div className="row row--between" style={{ alignItems: "flex-start" }}>
                      <div>
                        <div className="row" style={{ gap: "0.5rem" }}>
                          <span className="bold">{provider.display_name}</span>
                          <Badge tone={provider.provider_type === "SOCIETY" ? "blue" : ""}>
                            {provider.provider_type}
                          </Badge>
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
                          {provider.status === "SUSPENDED" ? <Badge tone="red">Suspended</Badge> : null}
                        </div>
                        <div className="small muted">
                          {provider.contact_phone ?? "No phone"} · {provider.address ?? "No address"}
                        </div>
                        <div className="tiny muted">
                          Joined {dateOnly(provider.created_at)}
                          {provider.authority_declared_at
                            ? ` · Authority declared ${dateOnly(provider.authority_declared_at)}`
                            : " · No authority declaration"}
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <div className="bold numeric">{money(provider.total_earnings)}</div>
                        <div className="tiny muted">
                          {provider.listing_count} listing{provider.listing_count === 1 ? "" : "s"}
                        </div>
                      </div>
                    </div>

                    {provider.verification_notes ? (
                      <div className="small muted">Note: {provider.verification_notes}</div>
                    ) : null}

                    <input
                      type="text"
                      placeholder="Note or reason (optional)"
                      value={notes[provider.id] ?? ""}
                      onChange={(event) => setNotes({ ...notes, [provider.id]: event.target.value })}
                    />

                    <div className="row" style={{ gap: "0.4rem" }}>
                      {provider.verification_status !== "VERIFIED" ? (
                        <button
                          type="button"
                          className="btn btn--sm"
                          onClick={() => void decide.run(provider.id, "VERIFIED")}
                        >
                          Approve verification
                        </button>
                      ) : null}
                      {provider.verification_status !== "REJECTED" ? (
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => void decide.run(provider.id, "REJECTED")}
                        >
                          Reject verification
                        </button>
                      ) : null}
                      {provider.status === "ACTIVE" ? (
                        <ConfirmButton
                          label="Suspend provider"
                          confirmLabel="Suspend this provider? Their live listings are taken out of search."
                          onConfirm={() => void setStatus.run(provider.id, "SUSPENDED")}
                        />
                      ) : (
                        <button
                          type="button"
                          className="btn btn--secondary btn--sm"
                          onClick={() => void setStatus.run(provider.id, "ACTIVE")}
                        >
                          Reactivate
                        </button>
                      )}
                    </div>
                  </div>
                </div>
              ))}
            </div>
            <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
      </div>
    </main>
  );
}
