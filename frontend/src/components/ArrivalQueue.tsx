/**
 * "Someone is at your gate right now."
 *
 * This is the provider's alarm bell, so it sits at the top of the page and is
 * the loudest thing on it. Anything less and a waiting renter ends up below
 * four other bookings — which is exactly what happened when the code lived on
 * the individual booking card.
 *
 * Renders nothing when nobody is waiting, so it costs a quiet page nothing.
 */
import { useCallback, useEffect, useState } from "react";
import { api } from "../lib/api";
import type { WaitingArrival } from "../lib/types";

const POLL_MS = 15000;

export default function ArrivalQueue() {
  const [waiting, setWaiting] = useState<WaitingArrival[]>([]);

  const load = useCallback(async () => {
    try {
      setWaiting(await api.get<WaitingArrival[]>("/bookings/arrivals/waiting"));
    } catch {
      /* a failed poll is not worth interrupting the page for */
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), POLL_MS);
    return () => clearInterval(timer);
  }, [load]);

  if (waiting.length === 0) return null;

  return (
    <div className="stack stack--sm" style={{ marginBottom: "1.25rem" }}>
      {waiting.map((entry) => (
        <div className="arrival-alert" key={entry.booking_id}>
          <div className="arrival-alert__head">
            <span className="arrival-alert__who">
              {entry.renter_name} is at {entry.space_title}
            </span>
            <span className="arrival-alert__wait">
              waiting {Math.max(Math.round(entry.waiting_minutes), 0)} min
            </span>
          </div>

          <div className="arrival-alert__code">{entry.code}</div>
          <div className="arrival-alert__say">Read this code out to let them in</div>

          <div className="arrival-alert__meta">
            <span>
              {entry.vehicle_number} · {entry.reference}
            </span>
            {entry.renter_phone ? (
              <a className="arrival-alert__call" href={`tel:${entry.renter_phone}`}>
                Call {entry.renter_phone}
              </a>
            ) : null}
          </div>
        </div>
      ))}
    </div>
  );
}
