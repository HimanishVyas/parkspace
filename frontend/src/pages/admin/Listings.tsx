import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Badge, Empty, ErrorMessage, Loading, Pagination, Stars } from "../../components/ui";
import { api } from "../../lib/api";
import { dateOnly, listingBadge } from "../../lib/format";
import { useAsync, useDebounced, useSubmit } from "../../lib/hooks";
import type { AdminListing, Paginated } from "../../lib/types";

const LIMIT = 20;

export default function Listings() {
  const [params] = useSearchParams();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState(params.get("status") ?? "");
  const [offset, setOffset] = useState(0);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const search = useDebounced(query);

  const { data, error, loading, reload } = useAsync(
    (signal) =>
      api.get<Paginated<AdminListing>>(
        "/admin/listings",
        { q: search || undefined, listing_status: status || undefined, limit: LIMIT, offset },
        signal,
      ),
    [search, status, offset],
  );

  const decide = useSubmit(async (id: string, action: "approve" | "reject" | "suspend") => {
    await api.post(`/admin/listings/${id}/${action}`, { reason: reasons[id]?.trim() || undefined });
    reload();
  });

  return (
    <main className="page page--wide">
      <h1>Listings</h1>

      <div className="stack">
        <div className="row">
          <input
            type="search"
            placeholder="Search title or address"
            value={query}
            style={{ flex: "1 1 240px" }}
            onChange={(event) => {
              setQuery(event.target.value);
              setOffset(0);
            }}
          />
          <select
            value={status}
            style={{ flex: "0 1 200px" }}
            onChange={(event) => {
              setStatus(event.target.value);
              setOffset(0);
            }}
          >
            <option value="">All statuses</option>
            <option value="PENDING_APPROVAL">Awaiting approval</option>
            <option value="PUBLISHED">Live</option>
            <option value="DRAFT">Draft</option>
            <option value="PAUSED">Paused</option>
            <option value="REJECTED">Rejected</option>
            <option value="SUSPENDED">Suspended</option>
          </select>
        </div>

        <ErrorMessage error={error} />
        <ErrorMessage error={decide.error} />

        {loading ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty title="No listings matched" />
        ) : (
          <>
            <div className="stack">
              {data.items.map((listing) => {
                const badge = listingBadge(listing.status);
                return (
                  <div className="panel panel__body" key={listing.id}>
                    <div className="stack">
                      <div className="row row--between" style={{ alignItems: "flex-start" }}>
                        <div>
                          <div className="row" style={{ gap: "0.5rem" }}>
                            <span className="bold">{listing.title}</span>
                            <Badge tone={badge.tone}>{badge.label}</Badge>
                            {!listing.authority_confirmed ? (
                              <Badge tone="red">No authority declaration</Badge>
                            ) : null}
                          </div>
                          <div className="small muted">
                            {listing.city} · {listing.provider_name} · {listing.total_slots} bay
                            {listing.total_slots === 1 ? "" : "s"}
                          </div>
                          <div className="tiny muted">Created {dateOnly(listing.created_at)}</div>
                        </div>
                        <Stars rating={listing.rating_average} count={listing.rating_count} />
                      </div>

                      {listing.rejection_reason ? (
                        <div className="small" style={{ color: "var(--red-700)" }}>
                          Rejected: {listing.rejection_reason}
                        </div>
                      ) : null}

                      <input
                        type="text"
                        placeholder="Reason (shown to the provider on rejection)"
                        value={reasons[listing.id] ?? ""}
                        onChange={(event) => setReasons({ ...reasons, [listing.id]: event.target.value })}
                      />

                      <div className="row" style={{ gap: "0.4rem" }}>
                        {listing.status !== "PUBLISHED" ? (
                          <button
                            type="button"
                            className="btn btn--sm"
                            onClick={() => void decide.run(listing.id, "approve")}
                          >
                            Approve and publish
                          </button>
                        ) : null}
                        {listing.status !== "REJECTED" ? (
                          <button
                            type="button"
                            className="btn btn--secondary btn--sm"
                            onClick={() => void decide.run(listing.id, "reject")}
                          >
                            Reject
                          </button>
                        ) : null}
                        {listing.status !== "SUSPENDED" ? (
                          <button
                            type="button"
                            className="btn btn--ghost btn--sm"
                            onClick={() => void decide.run(listing.id, "suspend")}
                          >
                            Suspend
                          </button>
                        ) : null}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
            <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
      </div>
    </main>
  );
}
