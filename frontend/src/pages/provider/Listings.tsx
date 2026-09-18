import { Link } from "react-router-dom";
import { Badge, ConfirmButton, Empty, ErrorMessage, Loading, Stars } from "../../components/ui";
import { api } from "../../lib/api";
import { PARKING_TYPE_LABEL, UNIT_LABEL, listingBadge, money } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { ParkingSpace } from "../../lib/types";

export default function Listings() {
  const { data, error, loading, reload } = useAsync(
    (signal) => api.get<ParkingSpace[]>("/parking/mine", undefined, signal),
    [],
  );

  const publish = useSubmit(async (id: string) => {
    await api.post(`/parking/${id}/publish`);
    reload();
  });
  const pause = useSubmit(async (id: string) => {
    await api.post(`/parking/${id}/pause`);
    reload();
  });
  const remove = useSubmit(async (id: string) => {
    await api.del(`/parking/${id}`);
    reload();
  });

  return (
    <main className="page">
      <div className="stack">
        <div className="row row--between">
          <h1>My parking spaces</h1>
          <Link to="/provider/listings/new" className="btn">
            Add parking space
          </Link>
        </div>

        <ErrorMessage error={error} />
        <ErrorMessage error={publish.error} />
        <ErrorMessage error={pause.error} />
        <ErrorMessage error={remove.error} />

        {loading ? (
          <Loading />
        ) : !data?.length ? (
          <Empty
            title="You have not listed a space yet"
            action={
              <Link to="/provider/listings/new" className="btn">
                Add your first space
              </Link>
            }
          >
            Add a space, set your hours and price, then publish it.
          </Empty>
        ) : (
          <div className="grid grid--2">
            {data.map((space) => {
              const badge = listingBadge(space.status);
              return (
                <div className="card stack" key={space.id}>
                  <div className="row row--between" style={{ alignItems: "flex-start" }}>
                    <div style={{ minWidth: 0 }}>
                      <div className="bold">{space.title}</div>
                      <div className="small muted truncate">
                        {space.address_line}, {space.city}
                      </div>
                    </div>
                    <Badge tone={badge.tone}>{badge.label}</Badge>
                  </div>

                  {space.rejection_reason ? (
                    <div className="alert alert--error small">{space.rejection_reason}</div>
                  ) : null}

                  <div className="row" style={{ gap: "0.4rem" }}>
                    <span className="badge badge--teal">{PARKING_TYPE_LABEL[space.parking_type]}</span>
                    {space.total_slots > 1 ? <span className="badge">{space.total_slots} bays</span> : null}
                    {space.requires_approval ? <span className="badge badge--amber">Manual approval</span> : null}
                  </div>

                  <div className="small">
                    {space.prices.map((price) => (
                      <span key={price.unit} style={{ marginRight: "0.85rem" }}>
                        <strong className="numeric">{money(price.amount)}</strong>
                        <span className="muted"> / {UNIT_LABEL[price.unit]}</span>
                      </span>
                    ))}
                  </div>

                  <Stars rating={space.rating_average} count={space.rating_count} />

                  <div className="row" style={{ gap: "0.4rem" }}>
                    <Link to={`/provider/listings/${space.id}/edit`} className="btn btn--secondary btn--sm">
                      Edit
                    </Link>
                    <Link
                      to={`/provider/listings/${space.id}/availability`}
                      className="btn btn--secondary btn--sm"
                    >
                      Availability
                    </Link>
                    {space.status === "PUBLISHED" ? (
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => void pause.run(space.id)}
                      >
                        Pause
                      </button>
                    ) : ["DRAFT", "PAUSED"].includes(space.status) ? (
                      <button
                        type="button"
                        className="btn btn--sm"
                        onClick={() => void publish.run(space.id)}
                        disabled={publish.pending}
                      >
                        Publish
                      </button>
                    ) : null}
                    {space.status === "DRAFT" ? (
                      <ConfirmButton
                        label="Delete"
                        confirmLabel={`Delete "${space.title}"? This cannot be undone.`}
                        className="btn btn--ghost btn--sm"
                        onConfirm={() => void remove.run(space.id)}
                      />
                    ) : null}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>
    </main>
  );
}
