import { useState } from "react";
import AdminNav from "../../components/AdminNav";
import { Badge, ConfirmButton, Empty, ErrorMessage, Loading, Pagination } from "../../components/ui";
import { api } from "../../lib/api";
import { bookingBadge, bookingWindow, money } from "../../lib/format";
import { useAsync, useDebounced, useSubmit } from "../../lib/hooks";
import type { AdminBooking, Paginated } from "../../lib/types";

const LIMIT = 20;
const CANCELLABLE = ["PENDING_PAYMENT", "PENDING_APPROVAL", "CONFIRMED", "ACTIVE"];

export default function Bookings() {
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("");
  const [offset, setOffset] = useState(0);
  const search = useDebounced(query);

  const { data, error, loading, reload } = useAsync(
    (signal) =>
      api.get<Paginated<AdminBooking>>(
        "/admin/bookings",
        { q: search || undefined, booking_status: status || undefined, limit: LIMIT, offset },
        signal,
      ),
    [search, status, offset],
  );

  const cancel = useSubmit(async (id: string) => {
    await api.post(`/admin/bookings/${id}/cancel`, { reason: "Cancelled by support" });
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
            placeholder="Search reference or vehicle number"
            value={query}
            style={{ flex: "1 1 260px" }}
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
            {[
              "PENDING_PAYMENT",
              "PENDING_APPROVAL",
              "CONFIRMED",
              "ACTIVE",
              "COMPLETED",
              "CANCELLED",
              "EXPIRED",
              "DISPUTED",
              "REJECTED",
            ].map((value) => (
              <option key={value} value={value}>
                {value.replace(/_/g, " ")}
              </option>
            ))}
          </select>
        </div>

        <ErrorMessage error={error} />
        <ErrorMessage error={cancel.error} />

        {loading ? (
          <Loading />
        ) : !data?.items.length ? (
          <Empty title="No bookings matched" />
        ) : (
          <>
            <div className="panel table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Reference</th>
                    <th>Parking</th>
                    <th>Renter</th>
                    <th>When</th>
                    <th className="numeric">Total</th>
                    <th className="numeric">Commission</th>
                    <th>Status</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((booking) => {
                    const badge = bookingBadge(booking.status);
                    return (
                      <tr key={booking.id}>
                        <td className="numeric small bold">{booking.reference}</td>
                        <td>
                          <div className="small">{booking.parking_title}</div>
                          <div className="tiny muted">{booking.provider_name}</div>
                        </td>
                        <td>
                          <div className="small">{booking.renter_name}</div>
                          <div className="tiny muted numeric">{booking.vehicle_number}</div>
                        </td>
                        <td className="small">{bookingWindow(booking.start_at, booking.end_at)}</td>
                        <td className="numeric">{money(booking.total_amount)}</td>
                        <td className="numeric muted">{money(booking.commission_amount)}</td>
                        <td>
                          <Badge tone={badge.tone}>{badge.label}</Badge>
                          {Number(booking.refund_amount) > 0 ? (
                            <div className="tiny muted numeric">
                              refunded {money(booking.refund_amount)}
                            </div>
                          ) : null}
                        </td>
                        <td>
                          {CANCELLABLE.includes(booking.status) ? (
                            <ConfirmButton
                              label="Cancel"
                              confirmLabel="Cancel this booking and refund the renter in full?"
                              onConfirm={() => void cancel.run(booking.id)}
                            />
                          ) : null}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <Pagination total={data.total} limit={LIMIT} offset={offset} onChange={setOffset} />
          </>
        )}
      </div>
    </main>
  );
}
