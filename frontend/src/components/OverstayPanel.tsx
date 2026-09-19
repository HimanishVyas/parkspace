/**
 * The meter, and the way to stop it.
 *
 * Shown while a booking is running or has run over. Inside the grace period it
 * offers a plain "I'm leaving"; past it, the amount owed is stated before the
 * button that charges it — nobody should discover a charge by pressing a button
 * that did not name it.
 *
 * The amount is recomputed on the server, so the figure here is a display of
 * what will be charged rather than the basis for it.
 */
import { useCallback, useEffect, useState } from "react";
import { Alert, ErrorMessage, Panel } from "./ui";
import { api } from "../lib/api";
import { money } from "../lib/format";
import { useSubmit } from "../lib/hooks";
import type { Booking, OverstayQuote, PaymentSession } from "../lib/types";

const POLL_MS = 30000;

function minutesLabel(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  return rest ? `${hours} hr ${rest} min` : `${hours} hr`;
}

export default function OverstayPanel({
  booking,
  onFinished,
}: {
  booking: Booking;
  onFinished: () => void;
}) {
  const [quote, setQuote] = useState<OverstayQuote | null>(null);

  const load = useCallback(async () => {
    try {
      setQuote(await api.get<OverstayQuote>(`/bookings/${booking.id}/overstay`));
    } catch {
      /* a failed poll should not disturb someone trying to leave */
    }
  }, [booking.id]);

  const running = booking.status === "ACTIVE" || booking.status === "OVERSTAYING";

  useEffect(() => {
    if (!running) return;
    void load();
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [running, load]);

  const payAndFinish = useSubmit(async () => {
    const session = await api.post<PaymentSession>("/payments/overstay", { booking_id: booking.id });
    if (session.gateway === "mock") {
      // The server signs and verifies the sandbox payment; see Checkout.tsx.
      await api.post("/payments/sandbox/complete", { booking_id: booking.id });
    }
    await api.post(`/bookings/${booking.id}/end`);
    onFinished();
  });

  const finish = useSubmit(async () => {
    await api.post(`/bookings/${booking.id}/end`);
    onFinished();
  });

  if (!running || !quote) return null;

  const owed = Number(quote.amount_due);
  const settled = quote.paid || owed <= 0;

  return (
    <Panel title={quote.overstaying ? "Running over" : "Finishing up"}>
      <div className="stack">
        {quote.overstaying ? (
          <>
            <div className="overstay">
              <div className="overstay__label">
                {minutesLabel(quote.overstay_minutes)} over · {money(quote.hourly_rate)}/hr
              </div>
              <div className="overstay__amount">{money(quote.overstay_amount)}</div>
              {quote.meter_capped ? (
                <div className="overstay__note">
                  This is the maximum — the charge has stopped growing.
                </div>
              ) : null}
            </div>
            {quote.paid ? (
              <Alert kind="success">Extra time paid. You're clear to go.</Alert>
            ) : null}
          </>
        ) : (
          <p className="small muted" style={{ margin: 0 }}>
            You're within your booked time. Leaving now costs nothing extra — after a short grace
            period the extra time is charged at {money(quote.hourly_rate)} an hour.
          </p>
        )}

        <ErrorMessage error={payAndFinish.error ?? finish.error} />

        {settled ? (
          <button
            type="button"
            className="btn btn--lg btn--block"
            disabled={finish.pending}
            onClick={() => void finish.run()}
          >
            {finish.pending ? "Finishing…" : "I'm leaving — finish parking"}
          </button>
        ) : (
          <button
            type="button"
            className="btn btn--lg btn--block"
            disabled={payAndFinish.pending}
            onClick={() => void payAndFinish.run()}
          >
            {payAndFinish.pending
              ? "Paying…"
              : `Pay ${money(quote.amount_due)} and finish`}
          </button>
        )}
      </div>
    </Panel>
  );
}
