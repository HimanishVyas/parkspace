import { useState } from "react";
import ArrivalQueue from "../../components/ArrivalQueue";
import { Badge, Empty, ErrorMessage, Field, Loading, Pagination, Panel, Tabs } from "../../components/ui";
import { api } from "../../lib/api";
import { bookingBadge, bookingWindow, money } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { Booking, Paginated } from "../../lib/types";

type Scope = "upcoming" | "active" | "past" | "all";
const LIMIT = 10;

export default function ProviderBookings() {
  const [scope, setScope] = useState<Scope>("upcoming");
  const [offset, setOffset] = useState(0);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [rejectReason, setRejectReason] = useState("");

  const { data, error, loading, reload } = useAsync(
    (signal) =>
      api.get<Paginated<Booking>>(
        "/bookings",
        { role: "provider", scope, limit: LIMIT, offset },
        signal,
      ),
    [scope, offset],
  );

  const approve = useSubmit(async (id: string) => {
    await api.post(`/bookings/${id}/approve`);
    reload();
  });
  const reject = useSubmit(async (id: string) => {
    await api.post(`/bookings/${id}/reject`, { reason: rejectReason.trim() });
    setRejecting(null);
    setRejectReason("");
    reload();
  });
  const cancel = useSubmit(async (id: string) => {
    await api.post(`/bookings/${id}/cancel`, { reason: "Cancelled by the provider" });
    reload();
  });

  return (
    <main className="page">
      <ArrivalQueue />
      <div className="stack">
        <h1>Bookings</h1>

        <Tabs
          value={scope}
          onChange={(next) => {
            setScope(next);
            setOffset(0);
          }}
          options={[
            { value: "upcoming", label: "Upcoming" },
            { value: "active", label: "In progress" },
            { value: "past", label: "Past" },
            { value: "all", label: "All" },
          ]}
        />

        <ErrorMessage error={error} />
        <ErrorMessage error={approve.error} />
        <ErrorMessage error={reject.error} />
        <ErrorMessage error={cancel.error} />

        {loading ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty title="No bookings in this view">
            Bookings appear here as renters book your spaces.
          </Empty>
        ) : (
          <div className="stack">
            {data.items.map((booking) => {
              const badge = bookingBadge(booking.status);
              return (
                <Panel key={booking.id}>
                  <div className="stack">
                    <div className="row row--between" style={{ alignItems: "flex-start" }}>
                      <div className="stack stack--sm" style={{ minWidth: 0 }}>
                        <div className="row" style={{ gap: "0.5rem" }}>
                          <Badge tone={badge.tone}>{badge.label}</Badge>
                          <span className="tiny muted numeric">{booking.reference}</span>
                        </div>
                        <div className="bold">{booking.parking_space.title}</div>
                        <div className="small muted">
                          {bookingWindow(booking.start_at, booking.end_at)}
                        </div>
                      </div>
                      <div style={{ textAlign: "right", flexShrink: 0 }}>
                        <div className="bold numeric">{money(booking.provider_earning)}</div>
                        <div className="tiny muted">your earning</div>
                      </div>
                    </div>

                    {booking.renter ? (
                      <div className="row small" style={{ gap: "1.25rem" }}>
                        <span>
                          <span className="muted">Renter: </span>
                          {booking.renter.full_name}
                        </span>
                        {booking.renter.phone ? (
                          <span>
                            <span className="muted">Phone: </span>
                            <a href={`tel:${booking.renter.phone}`}>{booking.renter.phone}</a>
                          </span>
                        ) : null}
                        <span>
                          <span className="muted">Vehicle: </span>
                          <span className="numeric">{booking.vehicle_number}</span> ({booking.vehicle_type})
                        </span>
                        {booking.bay_label ? (
                          <span>
                            <span className="muted">Bay: </span>
                            <span className="bold">{booking.bay_label}</span>
                          </span>
                        ) : null}
                      </div>
                    ) : (
                      <div className="small muted">
                        Vehicle <span className="numeric">{booking.vehicle_number}</span>
                      </div>
                    )}

                    {booking.renter_notes ? (
                      <div className="small">
                        <span className="muted">Note: </span>
                        {booking.renter_notes}
                      </div>
                    ) : null}

                    {booking.status === "PENDING_APPROVAL" ? (
                      rejecting === booking.id ? (
                        <form
                          className="stack stack--sm"
                          onSubmit={(event) => {
                            event.preventDefault();
                            void reject.run(booking.id);
                          }}
                        >
                          <Field label="Why can you not take this booking?" required>
                            <input
                              type="text"
                              required
                              minLength={3}
                              maxLength={500}
                              value={rejectReason}
                              onChange={(event) => setRejectReason(event.target.value)}
                              placeholder="The bay is being resurfaced that week"
                            />
                          </Field>
                          <div className="row">
                            <button type="submit" className="btn btn--danger btn--sm" disabled={reject.pending}>
                              Decline booking
                            </button>
                            <button
                              type="button"
                              className="btn btn--ghost btn--sm"
                              onClick={() => setRejecting(null)}
                            >
                              Cancel
                            </button>
                          </div>
                        </form>
                      ) : (
                        <div className="row">
                          <button
                            type="button"
                            className="btn btn--sm"
                            onClick={() => void approve.run(booking.id)}
                            disabled={approve.pending}
                          >
                            Accept
                          </button>
                          <button
                            type="button"
                            className="btn btn--secondary btn--sm"
                            onClick={() => setRejecting(booking.id)}
                          >
                            Decline
                          </button>
                        </div>
                      )
                    ) : booking.can_cancel ? (
                      <div className="row">
                        <button
                          type="button"
                          className="btn btn--ghost btn--sm"
                          onClick={() => {
                            if (
                              window.confirm(
                                "Cancel this booking? The renter is refunded in full and will be told.",
                              )
                            ) {
                              void cancel.run(booking.id);
                            }
                          }}
                        >
                          Cancel booking
                        </button>
                      </div>
                    ) : null}
                  </div>
                </Panel>
              );
            })}
            <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </div>
        )}
      </div>
    </main>
  );
}
