import { Link } from "react-router-dom";
import { Alert, ErrorMessage, Loading, Panel, Stat } from "../../components/ui";
import { api } from "../../lib/api";
import { money } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import type { AdminDashboard } from "../../lib/types";

export default function Dashboard() {
  const { data, error, loading } = useAsync(
    (signal) => api.get<AdminDashboard>("/admin/dashboard", undefined, signal),
    [],
  );

  return (
    <main className="page page--wide">
      <h1>Overview</h1>
      <ErrorMessage error={error} />

      {loading ? (
        <Loading />
      ) : data ? (
        <div className="stack stack--lg">
          {data.pending_listings > 0 ? (
            <Alert kind="warn">
              {data.pending_listings} listing{data.pending_listings === 1 ? "" : "s"} waiting for
              approval. <Link to="/admin/listings?status=PENDING_APPROVAL">Review them</Link>
            </Alert>
          ) : null}
          {data.open_reports > 0 ? (
            <Alert kind="warn">
              {data.open_reports} open issue report{data.open_reports === 1 ? "" : "s"}.{" "}
              <Link to="/admin/reports">Review reports</Link>
            </Alert>
          ) : null}

          <Panel title="Marketplace">
            <div className="grid grid--4">
              <Stat label="Total users" value={data.total_users} hint={`${data.total_renters} renters`} />
              <Stat
                label="Providers"
                value={data.total_providers}
                hint={`${data.verified_providers} verified`}
              />
              <Stat
                label="Listings"
                value={data.total_listings}
                hint={`${data.active_listings} live`}
              />
              <Stat
                label="Bookings"
                value={data.total_bookings}
                hint={`${data.todays_bookings} today · ${data.active_bookings} in progress`}
              />
            </div>
          </Panel>

          <Panel title="Revenue">
            <div className="grid grid--4">
              <Stat
                label="Booking value this month"
                value={money(data.monthly_booking_value)}
                hint="What renters paid"
              />
              <Stat
                label="Platform revenue this month"
                value={money(data.monthly_platform_revenue)}
                hint="Commission + fees"
              />
              <Stat label="Lifetime booking value" value={money(data.lifetime_booking_value)} />
              <Stat label="Lifetime platform revenue" value={money(data.lifetime_platform_revenue)} />
            </div>
          </Panel>

          <Panel title="Supply and demand">
            <p className="small muted" style={{ margin: 0 }}>
              The pilot is working when both sides grow together: enough live listings for renters
              to find something nearby, and enough repeat bookings for providers to keep their
              spaces listed.
            </p>
            <div className="grid grid--3" style={{ marginTop: "1rem" }}>
              <Stat
                label="Listings per provider"
                value={
                  data.total_providers
                    ? (data.total_listings / data.total_providers).toFixed(1)
                    : "—"
                }
              />
              <Stat
                label="Bookings per live listing"
                value={
                  data.active_listings ? (data.total_bookings / data.active_listings).toFixed(1) : "—"
                }
              />
              <Stat
                label="Average booking value"
                value={
                  data.total_bookings
                    ? money(Number(data.lifetime_booking_value) / data.total_bookings)
                    : "—"
                }
              />
            </div>
          </Panel>
        </div>
      ) : null}
    </main>
  );
}
