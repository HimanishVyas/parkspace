import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Empty, ErrorMessage, Loading, Pagination, Tabs } from "../../components/ui";
import { api } from "../../lib/api";
import { bookingBadge, bookingWindow, money } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import type { Booking, Paginated } from "../../lib/types";

type Scope = "upcoming" | "active" | "past" | "all";
const LIMIT = 10;

export default function Bookings() {
  const [scope, setScope] = useState<Scope>("upcoming");
  const [offset, setOffset] = useState(0);

  const { data, error, loading } = useAsync(
    (signal) =>
      api.get<Paginated<Booking>>("/bookings", { scope, limit: LIMIT, offset, role: "renter" }, signal),
    [scope, offset],
  );

  return (
    <main className="page">
      <div className="stack">
        <div className="row row--between">
          <h1>My bookings</h1>
          <Link to="/search" className="btn btn--secondary btn--sm">
            Find parking
          </Link>
        </div>

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

        {loading ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty
            title="Nothing here yet"
            action={
              <Link to="/search" className="btn">
                Find parking
              </Link>
            }
          >
            Your bookings will appear here once you book a space.
          </Empty>
        ) : (
          <div className="stack">
            {data.items.map((booking) => {
              const badge = bookingBadge(booking.status);
              return (
                <Link
                  key={booking.id}
                  to={`/bookings/${booking.id}`}
                  className="card card--hover"
                  style={{ color: "inherit" }}
                >
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
                      <div className="small muted">
                        {booking.parking_space.city} · Vehicle {booking.vehicle_number}
                      </div>
                    </div>
                    <div className="stack stack--sm" style={{ alignItems: "flex-end", flexShrink: 0 }}>
                      <div className="bold numeric">{money(booking.total_amount)}</div>
                      {booking.status === "PENDING_PAYMENT" ? (
                        <span className="badge badge--amber">Payment due</span>
                      ) : null}
                    </div>
                  </div>
                </Link>
              );
            })}
            <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </div>
        )}
      </div>
    </main>
  );
}
