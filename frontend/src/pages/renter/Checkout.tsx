/**
 * Payment step.
 *
 * With the mock gateway the browser signs the order itself, standing in for a
 * hosted checkout so the whole flow can be exercised without leaving the
 * machine. With a real gateway this is where its SDK would open; the
 * `confirm` call the server verifies is identical either way.
 */
import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { Alert, ErrorMessage, Loading, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { bookingWindow, dateTime, money } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { Booking, PaymentSession } from "../../lib/types";

declare global {
  interface Window {
    Razorpay?: new (options: Record<string, unknown>) => { open: () => void };
  }
}

export default function Checkout() {
  const { bookingId = "" } = useParams();
  const navigate = useNavigate();
  const [session, setSession] = useState<PaymentSession | null>(null);

  const booking = useAsync(
    (signal) => api.get<Booking>(`/bookings/${bookingId}`, undefined, signal),
    [bookingId],
  );

  const start = useSubmit(async () => {
    const created = await api.post<PaymentSession>("/payments/create", { booking_id: bookingId });
    setSession(created);
    return created;
  });

  // Open the gateway order as soon as the booking is known to be payable.
  useEffect(() => {
    if (booking.data?.status === "PENDING_PAYMENT" && !session && !start.pending) {
      void start.run();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [booking.data?.status]);

  const pay = useSubmit(async () => {
    if (!session) return;
    if (session.gateway === "mock") {
      // The sandbox signs client-side with the shared test secret; the server
      // still verifies the signature exactly as it would a real gateway's.
      const paymentId = String(session.client_payload.mock_payment_id ?? "");
      const signature = await mockSignature(session.order_id, paymentId);
      await api.post<Booking>("/payments/confirm", {
        order_id: session.order_id,
        payment_id: paymentId,
        signature,
      });
      navigate(`/bookings/${bookingId}`, { replace: true });
      return;
    }
    await openRazorpay(session, bookingId, navigate);
  });

  if (booking.loading) return <Loading />;
  if (!booking.data) {
    return (
      <main className="page page--narrow">
        <Alert kind="error">{booking.error?.message ?? "Booking not found"}</Alert>
      </main>
    );
  }

  const data = booking.data;

  if (data.status !== "PENDING_PAYMENT") {
    return (
      <main className="page page--narrow">
        <div className="card stack">
          <h1>Nothing to pay</h1>
          <p className="muted">
            This booking is {data.status.toLowerCase().replace("_", " ")}.
          </p>
          <Link to={`/bookings/${data.id}`} className="btn">
            View booking
          </Link>
        </div>
      </main>
    );
  }

  return (
    <main className="page page--narrow">
      <div className="stack">
        <h1>Confirm and pay</h1>

        {data.hold_expires_at ? (
          <Alert kind="warn">
            Your space is held until {dateTime(data.hold_expires_at)}.
          </Alert>
        ) : null}

        <Panel title={data.parking_space.title}>
          <div className="stack stack--sm">
            <p className="small muted" style={{ margin: 0 }}>
              {[data.parking_space.address_line, data.parking_space.city].filter(Boolean).join(", ")}
            </p>
            <p className="small" style={{ margin: 0 }}>
              {bookingWindow(data.start_at, data.end_at)}
            </p>
            <p className="small" style={{ margin: 0 }}>
              Vehicle {data.vehicle_number}
            </p>
          </div>
        </Panel>

        <Panel title="What you pay">
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
        </Panel>

        <ErrorMessage error={start.error} />
        <ErrorMessage error={pay.error} />

        {session?.gateway === "mock" ? (
          <Alert kind="info">
            Sandbox mode: no real money moves. Paying here simulates a successful gateway payment.
          </Alert>
        ) : null}

        <button
          type="button"
          className="btn btn--lg btn--block"
          disabled={!session || pay.pending}
          onClick={() => void pay.run()}
        >
          {pay.pending ? "Processing…" : `Pay ${money(data.total_amount)}`}
        </button>

        <Link to={`/bookings/${data.id}`} className="btn btn--ghost btn--block">
          Pay later
        </Link>

        <p className="tiny muted center">
          Card details are handled by the payment gateway. ParkSpace never sees or stores them.
        </p>
      </div>
    </main>
  );
}

/** HMAC-SHA256 of "order|payment" with the sandbox secret, via SubtleCrypto. */
async function mockSignature(orderId: string, paymentId: string): Promise<string> {
  const secret = import.meta.env.VITE_MOCK_GATEWAY_SECRET ?? "mock-gateway-secret";
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  );
  const signature = await crypto.subtle.sign(
    "HMAC",
    key,
    new TextEncoder().encode(`${orderId}|${paymentId}`),
  );
  return Array.from(new Uint8Array(signature))
    .map((byte) => byte.toString(16).padStart(2, "0"))
    .join("");
}

async function openRazorpay(
  session: PaymentSession,
  bookingId: string,
  navigate: (path: string, options?: { replace: boolean }) => void,
) {
  await loadScript("https://checkout.razorpay.com/v1/checkout.js");
  const payload = session.client_payload as Record<string, unknown>;
  const checkout = new window.Razorpay!({
    key: payload.key_id,
    order_id: session.order_id,
    amount: payload.amount_paise,
    currency: session.currency,
    name: "ParkSpace",
    description: payload.description,
    prefill: payload.prefill,
    handler: async (response: Record<string, string>) => {
      await api.post("/payments/confirm", {
        order_id: response.razorpay_order_id,
        payment_id: response.razorpay_payment_id,
        signature: response.razorpay_signature,
      });
      navigate(`/bookings/${bookingId}`, { replace: true });
    },
  });
  checkout.open();
}

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    if (document.querySelector(`script[src="${src}"]`)) return resolve();
    const script = document.createElement("script");
    script.src = src;
    script.onload = () => resolve();
    script.onerror = () => reject(new Error("Could not load the payment gateway"));
    document.body.appendChild(script);
  });
}
