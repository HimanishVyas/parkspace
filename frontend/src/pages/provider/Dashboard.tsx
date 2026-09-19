import ArrivalQueue from "../../components/ArrivalQueue";
import { Link } from "react-router-dom";
import { Alert, Badge, Empty, ErrorMessage, Loading, Panel, Stat } from "../../components/ui";
import { api } from "../../lib/api";
import { useAuth } from "../../lib/auth";
import { bookingBadge, bookingWindow, listingBadge, money } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import type { Booking, Paginated, ParkingSpace, ProviderDashboard } from "../../lib/types";

export default function Dashboard() {
  const { provider } = useAuth();
  const isSociety = provider?.provider_type === "SOCIETY";

  const stats = useAsync(
    (signal) => api.get<ProviderDashboard>("/providers/dashboard", undefined, signal),
    [],
  );
  const listings = useAsync(
    (signal) => api.get<ParkingSpace[]>("/parking/mine", undefined, signal),
    [],
  );
  const upcoming = useAsync(
    (signal) =>
      api.get<Paginated<Booking>>(
        "/bookings",
        { role: "provider", scope: "upcoming", limit: 5 },
        signal,
      ),
    [],
  );

  const needsVerification =
    provider && ["UNVERIFIED", "REJECTED"].includes(provider.verification_status);
  const awaitingApproval = upcoming.data?.items.filter((b) => b.status === "PENDING_APPROVAL") ?? [];

  return (
    <main className="page">
      <ArrivalQueue />
      <div className="stack">
        <div className="row row--between">
          <div>
            <h1>{isSociety ? "Society dashboard" : "Provider dashboard"}</h1>
            <p className="muted small" style={{ margin: 0 }}>
              {provider?.display_name}
            </p>
          </div>
          <Link to="/provider/listings/new" className="btn">
            Add parking space
          </Link>
        </div>

        <ErrorMessage error={stats.error} />

        {needsVerification ? (
          <Alert kind="warn">
            Your provider account is not verified yet. Verified providers earn more trust from
            renters. <Link to="/provider/society">Complete verification</Link>
          </Alert>
        ) : null}

        {awaitingApproval.length > 0 ? (
          <Alert kind="info">
            {awaitingApproval.length} booking request
            {awaitingApproval.length === 1 ? "" : "s"} waiting for your decision.{" "}
            <Link to="/provider/bookings">Review requests</Link>
          </Alert>
        ) : null}

        {stats.loading ? (
          <Loading />
        ) : stats.data ? (
          <>
            <div className="grid grid--4">
              <Stat label="Total earnings" value={money(stats.data.total_earnings)} hint="From completed bookings" />
              <Stat label="Pending payout" value={money(stats.data.pending_payout)} hint="Awaiting settlement" />
              <Stat label="Upcoming earnings" value={money(stats.data.upcoming_earnings)} hint="Booked, not yet completed" />
              <Stat label="Paid out" value={money(stats.data.completed_payout)} />
            </div>
            <div className="grid grid--4">
              <Stat label="Active listings" value={stats.data.active_listings} hint={`${stats.data.total_listings} total`} />
              <Stat label="Upcoming bookings" value={stats.data.upcoming_bookings} />
              <Stat label="Bookings today" value={stats.data.todays_bookings} />
              <Stat
                label="This month"
                value={money(stats.data.current_month.provider_earnings)}
                hint={`${stats.data.current_month.booking_count} bookings`}
              />
            </div>
          </>
        ) : null}

        <div className="grid grid--2">
          <Panel
            title="Your parking spaces"
            actions={
              <Link to="/provider/listings" className="small">
                Manage all
              </Link>
            }
          >
            {listings.loading ? (
              <Loading />
            ) : !listings.data?.length ? (
              <Empty
                title="No parking spaces yet"
                action={
                  <Link to="/provider/listings/new" className="btn btn--sm">
                    Add your first space
                  </Link>
                }
              >
                Listing takes a few minutes.
              </Empty>
            ) : (
              <div className="stack stack--sm">
                {listings.data.slice(0, 5).map((space) => {
                  const badge = listingBadge(space.status);
                  return (
                    <div className="row row--between" key={space.id}>
                      <div style={{ minWidth: 0 }}>
                        <Link to={`/provider/listings/${space.id}/edit`} className="bold truncate">
                          {space.title}
                        </Link>
                        <div className="tiny muted">{space.city}</div>
                      </div>
                      <Badge tone={badge.tone}>{badge.label}</Badge>
                    </div>
                  );
                })}
              </div>
            )}
          </Panel>

          <Panel
            title="Upcoming bookings"
            actions={
              <Link to="/provider/bookings" className="small">
                View all
              </Link>
            }
          >
            {upcoming.loading ? (
              <Loading />
            ) : !upcoming.data?.items.length ? (
              <Empty title="No upcoming bookings">
                They will show up here as renters book your spaces.
              </Empty>
            ) : (
              <div className="stack stack--sm">
                {upcoming.data.items.map((booking) => {
                  const badge = bookingBadge(booking.status);
                  return (
                    <Link
                      key={booking.id}
                      to="/provider/bookings"
                      className="row row--between"
                      style={{ color: "inherit" }}
                    >
                      <div style={{ minWidth: 0 }}>
                        <div className="bold truncate small">{booking.parking_space.title}</div>
                        <div className="tiny muted">
                          {bookingWindow(booking.start_at, booking.end_at)}
                        </div>
                      </div>
                      <div style={{ textAlign: "right" }}>
                        <Badge tone={badge.tone}>{badge.label}</Badge>
                        <div className="tiny muted numeric">{money(booking.provider_earning)}</div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}
          </Panel>
        </div>

        <div className="row">
          <Link to="/provider/earnings" className="btn btn--secondary btn--sm">
            Earnings
          </Link>
          <Link to="/provider/bookings" className="btn btn--secondary btn--sm">
            Bookings
          </Link>
          <Link to="/provider/listings" className="btn btn--secondary btn--sm">
            Parking spaces
          </Link>
          {isSociety ? (
            <Link to="/provider/society" className="btn btn--secondary btn--sm">
              Society profile
            </Link>
          ) : (
            <Link to="/provider/society" className="btn btn--secondary btn--sm">
              Verification
            </Link>
          )}
        </div>
      </div>
    </main>
  );
}
