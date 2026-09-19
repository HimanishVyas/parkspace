import { useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import ArrivalPanel from "../../components/ArrivalPanel";
import OverstayPanel from "../../components/OverstayPanel";
import MapView from "../../components/LazyMap";
import QRCode from "../../components/QRCode";
import { Alert, Badge, ErrorMessage, Field, Loading, Panel, Stars } from "../../components/ui";
import { api } from "../../lib/api";
import { bookingBadge, bookingWindow, dateTime, money, UNIT_PLURAL } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { Booking, BookingConfirmation } from "../../lib/types";

export default function BookingDetail() {
  const { bookingId = "" } = useParams();
  const navigate = useNavigate();
  const [cancelReason, setCancelReason] = useState("");
  const [showCancel, setShowCancel] = useState(false);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");
  const [reviewDone, setReviewDone] = useState(false);

  const booking = useAsync(
    (signal) => api.get<Booking>(`/bookings/${bookingId}`, undefined, signal),
    [bookingId],
  );
  const confirmation = useAsync(
    (signal) => api.get<BookingConfirmation>(`/bookings/${bookingId}/confirmation`, undefined, signal),
    [bookingId],
  );

  const cancel = useSubmit(async () => {
    await api.post(`/bookings/${bookingId}/cancel`, { reason: cancelReason.trim() || undefined });
    setShowCancel(false);
    booking.reload();
  });

  const review = useSubmit(async () => {
    await api.post("/reviews", { booking_id: bookingId, rating, comment: comment.trim() || undefined });
    setReviewDone(true);
  });

  if (booking.loading) return <Loading />;
  if (booking.error || !booking.data) {
    return (
      <main className="page page--narrow">
        <Alert kind="error">{booking.error?.message ?? "Booking not found"}</Alert>
      </main>
    );
  }

  const data = booking.data;
  const badge = bookingBadge(data.status);
  const canReview = data.status === "COMPLETED" && !reviewDone;

  return (
    <main className="page">
      <div className="stack">
        <Link to="/bookings" className="small">
          ← All bookings
        </Link>

        <div className="row row--between">
          <div>
            <div className="row" style={{ gap: "0.5rem", marginBottom: "0.25rem" }}>
              <Badge tone={badge.tone}>{badge.label}</Badge>
              <span className="small muted numeric">{data.reference}</span>
            </div>
            <h1 style={{ marginBottom: 0 }}>{data.parking_space.title}</h1>
          </div>
          {data.status === "PENDING_PAYMENT" ? (
            <Link to={`/bookings/${data.id}/pay`} className="btn">
              Pay now
            </Link>
          ) : null}
        </div>

        {data.status === "PENDING_PAYMENT" && data.hold_expires_at ? (
          <Alert kind="warn">
            This space is held for you until {dateTime(data.hold_expires_at)}. Complete payment before
            then or the slot is released.
          </Alert>
        ) : null}
        {data.status === "PENDING_APPROVAL" ? (
          <Alert kind="info">
            The provider is reviewing your request. You will be asked to pay once they accept.
          </Alert>
        ) : null}
        {data.status === "CANCELLED" ? (
          <Alert kind="info">
            Cancelled{data.cancellation_reason ? `: ${data.cancellation_reason}` : "."}{" "}
            {Number(data.refund_amount) > 0
              ? `A refund of ${money(data.refund_amount)} has been issued.`
              : "No refund was due under the cancellation policy."}
          </Alert>
        ) : null}

        <div className="search-layout">
          <div className="stack">
            <Panel title="Booking details">
              <div className="stack stack--sm">
                <Row label="When" value={bookingWindow(data.start_at, data.end_at)} />
                <Row
                  label="Duration"
                  value={`${Number(data.quantity)} ${UNIT_PLURAL[data.unit]}`}
                />
                <Row label="Vehicle" value={`${data.vehicle_number} (${data.vehicle_type})`} />
                {data.bay_label ? <Row label="Bay" value={data.bay_label} /> : null}
                <Row
                  label="Location"
                  value={[data.parking_space.address_line, data.parking_space.landmark, data.parking_space.city]
                    .filter(Boolean)
                    .join(", ")}
                />
                <Row label="Provider" value={data.provider_name} />
                {data.renter ? <Row label="Renter" value={`${data.renter.full_name}${data.renter.phone ? ` · ${data.renter.phone}` : ""}`} /> : null}
                {data.renter_notes ? <Row label="Your note" value={data.renter_notes} /> : null}
              </div>
            </Panel>

            {data.access_instructions ? (
              <Panel title="Parking instructions">
                <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>{data.access_instructions}</p>
              </Panel>
            ) : null}

            <Panel title="Getting there">
              <MapView
                markers={[
                  {
                    id: data.parking_space.id,
                    latitude: data.parking_space.latitude,
                    longitude: data.parking_space.longitude,
                    active: true,
                    label: data.parking_space.title,
                  },
                ]}
                center={{
                  latitude: data.parking_space.latitude,
                  longitude: data.parking_space.longitude,
                }}
                zoom={16}
              />
              <a
                className="btn btn--secondary btn--sm"
                style={{ marginTop: "0.75rem" }}
                href={`https://www.openstreetmap.org/directions?to=${data.parking_space.latitude},${data.parking_space.longitude}`}
                target="_blank"
                rel="noreferrer"
              >
                Open directions
              </a>
            </Panel>

            {canReview ? (
              <Panel title="Rate this parking">
                <form
                  className="stack"
                  onSubmit={(event) => {
                    event.preventDefault();
                    void review.run();
                  }}
                >
                  <ErrorMessage error={review.error} />
                  <Field label="Rating">
                    <div className="chips">
                      {[1, 2, 3, 4, 5].map((value) => (
                        <button
                          key={value}
                          type="button"
                          className={`chip${rating === value ? " chip--on" : ""}`}
                          onClick={() => setRating(value)}
                        >
                          {"★".repeat(value)}
                        </button>
                      ))}
                    </div>
                  </Field>
                  <Field label="Comment (optional)">
                    <textarea
                      rows={3}
                      value={comment}
                      maxLength={2000}
                      onChange={(event) => setComment(event.target.value)}
                      placeholder="Was it easy to find? Was the space as described?"
                    />
                  </Field>
                  <button type="submit" className="btn" disabled={review.pending}>
                    {review.pending ? "Sending…" : "Submit rating"}
                  </button>
                </form>
              </Panel>
            ) : null}
            {reviewDone ? (
              <Alert kind="success">
                Thank you — your rating helps other renters. <Stars rating={rating} />
              </Alert>
            ) : null}
          </div>

          <div className="stack search-layout__map">
            <OverstayPanel booking={data} onFinished={() => booking.reload()} />

            {data.parking_space.requires_arrival_code ? (
              <ArrivalPanel booking={data} onCheckedIn={() => booking.reload()} />
            ) : null}

            {confirmation.data && ["CONFIRMED", "ACTIVE", "COMPLETED"].includes(data.status) ? (
              <Panel title="Show on arrival">
                <div className="stack" style={{ alignItems: "center" }}>
                  <div className="qr">
                    <QRCode value={confirmation.data.qr_payload} />
                  </div>
                  <div className="center">
                    <div className="bold numeric" style={{ fontSize: "1.2rem" }}>
                      {data.reference}
                    </div>
                    <div className="small muted">{data.vehicle_number}</div>
                  </div>
                  <button type="button" className="btn btn--secondary btn--sm" onClick={() => window.print()}>
                    Print confirmation
                  </button>
                  <p className="tiny muted center" style={{ margin: 0 }}>
                    This code identifies your booking. It does not open any barrier.
                  </p>
                </div>
              </Panel>
            ) : null}

            <Panel title="Payment">
              <div>
                <div className="summary__line">
                  <span>Parking</span>
                  <span className="numeric">{money(data.base_amount)}</span>
                </div>
                <div className="summary__line">
                  <span className="muted">Platform fee</span>
                  <span className="numeric muted">{money(data.platform_fee)}</span>
                </div>
                <div className="summary__line">
                  <span className="muted">Taxes</span>
                  <span className="numeric muted">{money(data.tax_amount)}</span>
                </div>
                <div className="summary__total">
                  <span>Total</span>
                  <span className="numeric">{money(data.total_amount)}</span>
                </div>
                {Number(data.refund_amount) > 0 ? (
                  <div className="summary__line" style={{ color: "var(--green-700)" }}>
                    <span>Refunded</span>
                    <span className="numeric">{money(data.refund_amount)}</span>
                  </div>
                ) : null}
              </div>
            </Panel>

            {data.can_cancel ? (
              <Panel title="Need to cancel?">
                {!showCancel ? (
                  <div className="stack stack--sm">
                    {data.refund_if_cancelled_now !== null ? (
                      <p className="small muted" style={{ margin: 0 }}>
                        Cancelling now would refund{" "}
                        <strong>{money(data.refund_if_cancelled_now)}</strong> under the cancellation
                        policy.
                      </p>
                    ) : null}
                    <button
                      type="button"
                      className="btn btn--secondary btn--sm"
                      onClick={() => setShowCancel(true)}
                    >
                      Cancel booking
                    </button>
                  </div>
                ) : (
                  <form
                    className="stack"
                    onSubmit={(event) => {
                      event.preventDefault();
                      void cancel.run();
                    }}
                  >
                    <ErrorMessage error={cancel.error} />
                    <Field label="Reason (optional)">
                      <textarea
                        rows={2}
                        value={cancelReason}
                        maxLength={500}
                        onChange={(event) => setCancelReason(event.target.value)}
                      />
                    </Field>
                    <div className="row">
                      <button type="submit" className="btn btn--danger btn--sm" disabled={cancel.pending}>
                        {cancel.pending ? "Cancelling…" : "Confirm cancellation"}
                      </button>
                      <button
                        type="button"
                        className="btn btn--ghost btn--sm"
                        onClick={() => setShowCancel(false)}
                      >
                        Keep booking
                      </button>
                    </div>
                  </form>
                )}
              </Panel>
            ) : null}

            {["CONFIRMED", "ACTIVE", "COMPLETED", "DISPUTED"].includes(data.status) ? (
              <button
                type="button"
                className="btn btn--ghost btn--sm"
                onClick={() => navigate(`/bookings/${data.id}/report`)}
              >
                Report an issue
              </button>
            ) : null}
          </div>
        </div>
      </div>
    </main>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="row" style={{ gap: "0.75rem", alignItems: "flex-start" }}>
      <span className="small muted" style={{ minWidth: 92 }}>
        {label}
      </span>
      <span className="small" style={{ flex: 1 }}>
        {value}
      </span>
    </div>
  );
}
