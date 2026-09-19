/**
 * Check-in at an unattended space.
 *
 * The renter says they have arrived, the provider is sent a code, they pass it
 * on by phone, and the renter types it in. Two things shape the UI:
 *
 *  - The renter must never see the code. The API withholds it from their view,
 *    and nothing here asks for it.
 *  - The provider might not answer. The waiting state says how long it has been
 *    and offers a way out instead of an indefinite spinner.
 */
import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { Alert, ErrorMessage, Field, Panel } from "./ui";
import { api, ApiError } from "../lib/api";
import { useSubmit } from "../lib/hooks";
import type { ArrivalState, Booking } from "../lib/types";

interface Props {
  booking: Booking;
  onCheckedIn: () => void;
}

/** Ask the browser where we are, but never block on it. */
function currentPosition(): Promise<{ latitude: number; longitude: number } | null> {
  return new Promise((resolve) => {
    // Geolocation needs a secure context, so on a plain-http LAN address it is
    // simply absent. The server treats a missing position as "not checked".
    if (!navigator.geolocation || !window.isSecureContext) return resolve(null);
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
      () => resolve(null),
      { timeout: 8000, maximumAge: 60000 },
    );
  });
}

export default function ArrivalPanel({ booking, onCheckedIn }: Props) {
  const [state, setState] = useState<ArrivalState | null>(null);
  const [code, setCode] = useState("");

  const load = useCallback(async () => {
    try {
      setState(await api.get<ArrivalState>(`/bookings/${booking.id}/arrival`));
    } catch {
      /* nothing announced yet is a perfectly normal state */
    }
  }, [booking.id]);

  useEffect(() => {
    void load();
  }, [load]);

  // While waiting on the provider, keep the elapsed time honest.
  useEffect(() => {
    if (!state?.announced || state.verified) return;
    const timer = setInterval(() => void load(), 15000);
    return () => clearInterval(timer);
  }, [state?.announced, state?.verified, load]);

  const announce = useSubmit(async () => {
    const position = await currentPosition();
    setState(await api.post<ArrivalState>(`/bookings/${booking.id}/arrival`, position ?? {}));
  });

  const verify = useSubmit(async () => {
    await api.post<Booking>(`/bookings/${booking.id}/arrival/verify`, { code: code.trim() });
    setCode("");
    onCheckedIn();
  });

  const attemptsLeft =
    verify.error instanceof ApiError
      ? (verify.error.details as { attempts_left?: number }[] | undefined)?.[0]?.attempts_left
      : undefined;

  if (booking.status === "ACTIVE") {
    return (
      <Panel title="You're parked">
        <Alert kind="success">
          Checked in. Your parking is running — the instructions are above.
        </Alert>
      </Panel>
    );
  }

  if (booking.status !== "CONFIRMED") return null;

  return (
    <Panel title="Checking in">
      {!state?.announced ? (
        <div className="stack">
          <p className="small muted" style={{ margin: 0 }}>
            This space has nobody at the gate. Tell the provider you have arrived and they will send
            you a code to let you in.
          </p>
          <ErrorMessage error={announce.error} />
          <button
            type="button"
            className="btn btn--lg btn--block"
            disabled={announce.pending}
            onClick={() => void announce.run()}
          >
            {announce.pending ? "Telling them…" : "I've reached"}
          </button>
        </div>
      ) : (
        <div className="stack">
          {state.escalate ? (
            <Alert kind="warn">
              The provider hasn't sent your code yet. You've been waiting{" "}
              {Math.round(state.waiting_minutes ?? 0)} minutes — report this and we'll step in.
            </Alert>
          ) : (
            <Alert kind="info">
              We've told the provider you're here. Ask them for your 6-digit code
              {state.waiting_minutes != null && state.waiting_minutes >= 1
                ? ` — waiting ${Math.round(state.waiting_minutes)} min`
                : ""}
              .
            </Alert>
          )}

          <Field label="Enter the code they gave you" required>
            <input
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]*"
              maxLength={6}
              value={code}
              placeholder="······"
              onChange={(event) => setCode(event.target.value.replace(/\D/g, ""))}
              style={{
                fontSize: "1.6rem",
                letterSpacing: "0.5em",
                textAlign: "center",
                fontVariantNumeric: "tabular-nums",
              }}
            />
          </Field>

          <ErrorMessage error={verify.error} />
          {attemptsLeft != null ? (
            <p className="small muted" style={{ margin: 0 }}>
              {attemptsLeft} {attemptsLeft === 1 ? "try" : "tries"} left before you need a new code.
            </p>
          ) : null}

          <button
            type="button"
            className="btn btn--lg btn--block"
            disabled={code.length < 4 || verify.pending}
            onClick={() => void verify.run()}
          >
            {verify.pending ? "Checking…" : "Verify and park"}
          </button>

          <div className="row">
            <button
              type="button"
              className="btn btn--ghost btn--sm"
              disabled={announce.pending}
              onClick={() => void announce.run()}
            >
              {state.expired ? "Get a new code" : "Nudge the provider"}
            </button>
            {state.escalate ? (
              <Link to={`/bookings/${booking.id}/report`} className="btn btn--secondary btn--sm">
                Report a problem
              </Link>
            ) : null}
          </div>
        </div>
      )}
    </Panel>
  );
}
