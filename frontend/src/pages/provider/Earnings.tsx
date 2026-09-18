import { Empty, ErrorMessage, Loading, Panel, Stat } from "../../components/ui";
import { api } from "../../lib/api";
import { money } from "../../lib/format";
import { useAsync } from "../../lib/hooks";
import type { Earnings } from "../../lib/types";

function monthLabel(value: string): string {
  const [year, month] = value.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString("en-IN", { month: "long", year: "numeric" });
}

export default function ProviderEarnings() {
  const { data, error, loading } = useAsync(
    (signal) => api.get<Earnings>("/providers/earnings", { months: 12 }, signal),
    [],
  );

  return (
    <main className="page">
      <div className="stack">
        <h1>Earnings</h1>
        <ErrorMessage error={error} />

        {loading ? (
          <Loading />
        ) : data ? (
          <>
            <div className="grid grid--4">
              <Stat
                label="Total earnings"
                value={money(data.total_earnings)}
                hint="From completed bookings"
              />
              <Stat label="Pending payout" value={money(data.pending_payout)} hint="Owed to you" />
              <Stat label="Paid out" value={money(data.completed_payout)} />
              <Stat
                label="Upcoming"
                value={money(data.upcoming_earnings)}
                hint="Booked, not yet completed"
              />
            </div>

            <Panel title="Month by month" flush>
              {!data.months.length ? (
                <Empty title="No earnings yet">
                  Once renters book and complete their parking, the breakdown appears here.
                </Empty>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Month</th>
                        <th className="numeric">Bookings</th>
                        <th className="numeric">Gross booking value</th>
                        <th className="numeric">Platform fee</th>
                        <th className="numeric">Your earnings</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.months.map((month) => (
                        <tr key={month.month}>
                          <td>{monthLabel(month.month)}</td>
                          <td className="numeric">{month.booking_count}</td>
                          <td className="numeric">{money(month.gross_booking_value)}</td>
                          <td className="numeric muted">−{money(month.platform_fee)}</td>
                          <td className="numeric bold">{money(month.provider_earnings)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Panel>

            <p className="small muted">
              Gross booking value is what renters paid for the parking itself. The platform fee is
              the commission deducted from it; the remainder is yours. Payouts are settled by the
              ParkSpace team — pending amounts are what you are owed so far.
            </p>
          </>
        ) : null}
      </div>
    </main>
  );
}
