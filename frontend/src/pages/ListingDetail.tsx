import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import BayPicker from "../components/BayPicker";
import MapView from "../components/LazyMap";
import {
  Alert,
  Empty,
  ErrorMessage,
  Field,
  Loading,
  Panel,
  Stars,
} from "../components/ui";
import { api } from "../lib/api";
import {
  PARKING_TYPE_LABEL,
  UNIT_ADJECTIVE,
  UNIT_LABEL,
  UNIT_PLURAL,
  VEHICLE_LABEL,
  minutesToTime,
  money,
  toLocalInput,
} from "../lib/format";
import { useAsync, useSubmit } from "../lib/hooks";
import { useAuth } from "../lib/auth";
import type {
  AvailabilityRule,
  Booking,
  ParkingSpacePublic,
  PricingUnit,
  Quote,
  ReviewSummary,
  Vehicle,
} from "../lib/types";

const DAY_NAMES = [
  "Monday",
  "Tuesday",
  "Wednesday",
  "Thursday",
  "Friday",
  "Saturday",
  "Sunday",
];

/** Collapses a week of rules into readable lines like "Mon–Fri 8:00 am – 8:00 pm". */
function describeSchedule(rules: AvailabilityRule[]): string[] {
  const byDay = new Map<number, string>();
  for (let day = 0; day < 7; day++) {
    const windows = rules
      .filter((rule) => rule.is_active && rule.day_of_week === day)
      .sort((a, b) => a.start_minute - b.start_minute)
      .map((rule) =>
        rule.start_minute === 0 && rule.end_minute === 1440
          ? "All day"
          : `${minutesToTime(rule.start_minute)} – ${minutesToTime(rule.end_minute)}`,
      );
    if (windows.length) byDay.set(day, windows.join(", "));
  }

  const lines: string[] = [];
  let runStart: number | null = null;
  for (let day = 0; day <= 7; day++) {
    const current: string | undefined = byDay.get(day);
    const previous: string | undefined =
      runStart !== null ? byDay.get(runStart) : undefined;
    if (runStart === null) {
      if (current) runStart = day;
      continue;
    }
    if (current !== previous) {
      const label =
        runStart === day - 1
          ? DAY_NAMES[runStart].slice(0, 3)
          : `${DAY_NAMES[runStart].slice(0, 3)}–${DAY_NAMES[day - 1].slice(0, 3)}`;
      lines.push(`${label}: ${previous}`);
      runStart = current ? day : null;
    }
  }
  return lines.length ? lines : ["No availability published yet"];
}

export default function ListingDetail() {
  const { spaceId = "" } = useParams();
  const navigate = useNavigate();
  const { user } = useAuth();

  const space = useAsync(
    (signal) =>
      api.get<ParkingSpacePublic>(`/parking/${spaceId}`, undefined, signal),
    [spaceId],
  );
  const availability = useAsync(
    (signal) =>
      api.get<{ rules: AvailabilityRule[]; blocks: unknown[] }>(
        `/parking/${spaceId}/availability`,
        undefined,
        signal,
      ),
    [spaceId],
  );
  const reviews = useAsync(
    (signal) =>
      api.get<ReviewSummary>(`/reviews/space/${spaceId}`, { limit: 5 }, signal),
    [spaceId],
  );
  const vehicles = useAsync(
    (signal) =>
      user
        ? api.get<Vehicle[]>("/vehicles", undefined, signal)
        : Promise.resolve([]),
    [user?.id],
  );

  const [photoIndex, setPhotoIndex] = useState(0);
  const [unit, setUnit] = useState<PricingUnit>("HOURLY");
  const [startAt, setStartAt] = useState("");
  const [quantity, setQuantity] = useState(2);
  const [vehicleId, setVehicleId] = useState("");
  // null means "any bay" — the server assigns one, as it always did.
  const [slotIndex, setSlotIndex] = useState<number | null>(null);
  const [notes, setNotes] = useState("");
  const [quote, setQuote] = useState<Quote | null>(null);
  const [quoteError, setQuoteError] = useState<string | null>(null);

  const listing = space.data;

  // Default the duration type to something the space actually offers.
  useEffect(() => {
    if (listing && !listing.prices.some((price) => price.unit === unit)) {
      setUnit(listing.prices[0]?.unit ?? "HOURLY");
    }
  }, [listing?.id]);

  useEffect(() => {
    const defaultVehicle =
      vehicles.data?.find((vehicle) => vehicle.is_default) ??
      vehicles.data?.[0];
    if (defaultVehicle && !vehicleId) setVehicleId(defaultVehicle.id);
  }, [vehicles.data, vehicleId]);

  // Ask the server for the price and availability whenever the selection changes.
  useEffect(() => {
    if (!listing || !startAt) {
      setQuote(null);
      return;
    }
    let active = true;
    setQuoteError(null);
    const timer = setTimeout(async () => {
      try {
        const result = await api.post<Quote>("/bookings/quote", {
          parking_space_id: listing.id,
          unit,
          start_at: new Date(startAt).toISOString(),
          quantity,
        });
        if (active) setQuote(result);
      } catch (error) {
        if (active) {
          setQuote(null);
          setQuoteError(
            error instanceof Error ? error.message : "Could not price that",
          );
        }
      }
    }, 300);
    return () => {
      active = false;
      clearTimeout(timer);
    };
  }, [listing?.id, unit, startAt, quantity]);

  const book = useSubmit(async () => {
    if (!listing) return;
    const booking = await api.post<Booking>("/bookings", {
      parking_space_id: listing.id,
      vehicle_id: vehicleId,
      unit,
      start_at: new Date(startAt).toISOString(),
      quantity,
      slot_index: slotIndex ?? undefined,
      renter_notes: notes.trim() || undefined,
    });
    navigate(
      booking.status === "PENDING_PAYMENT"
        ? `/bookings/${booking.id}/pay`
        : `/bookings/${booking.id}`,
    );
  });

  const schedule = useMemo(
    () => describeSchedule(availability.data?.rules ?? []),
    [availability.data],
  );

  if (space.loading) return <Loading label="Loading listing…" />;
  if (space.error || !listing) {
    return (
      <main className="page page--narrow">
        <Empty title="Listing not available">
          This parking space may have been paused or removed.{" "}
          <Link to="/search">Browse other spaces</Link>.
        </Empty>
      </main>
    );
  }

  const photos = listing.photos;
  const canBook = Boolean(user && vehicleId && startAt && quote?.available);

  return (
    <main className="page">
      <div className="stack">
        <div className="row" style={{ gap: "0.5rem" }}>
          <Link to="/search" className="small">
            ← Back to search
          </Link>
        </div>

        <div className="search-layout">
          <div className="stack">
            <div className="gallery">
              <div className="gallery__main">
                {photos.length > 0 ? (
                  <img
                    src={photos[photoIndex]?.url}
                    alt={photos[photoIndex]?.caption ?? listing.title}
                  />
                ) : (
                  <div
                    style={{
                      display: "grid",
                      placeItems: "center",
                      height: "100%",
                      fontSize: "3rem",
                      color: "var(--gray-400)",
                    }}
                  >
                    🅿️
                  </div>
                )}
              </div>
              {photos.length > 1 ? (
                <div className="gallery__thumbs">
                  {photos.map((photo, index) => (
                    <button
                      key={photo.id}
                      type="button"
                      className={`gallery__thumb${index === photoIndex ? " gallery__thumb--on" : ""}`}
                      onClick={() => setPhotoIndex(index)}
                      aria-label={`Photo ${index + 1}`}
                    >
                      <img src={photo.url} alt="" />
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            <div>
              <div
                className="row"
                style={{ gap: "0.4rem", marginBottom: "0.4rem" }}
              >
                <span className="badge badge--teal">
                  {PARKING_TYPE_LABEL[listing.parking_type]}
                </span>
                {listing.vehicle_types.map((type) => (
                  <span className="badge" key={type}>
                    {VEHICLE_LABEL[type]}
                  </span>
                ))}
                {listing.total_slots > 1 ? (
                  <span className="badge">{listing.total_slots} bays</span>
                ) : null}
              </div>
              <h1>{listing.title}</h1>
              <p className="muted" style={{ marginBottom: "0.35rem" }}>
                {[listing.address_line, listing.landmark, listing.city]
                  .filter(Boolean)
                  .join(", ")}
                {listing.distance_km !== null
                  ? ` · ${listing.distance_km.toFixed(1)} km away`
                  : ""}
              </p>
              <Stars
                rating={listing.rating_average}
                count={listing.rating_count}
              />
            </div>

            {listing.description ? (
              <Panel title="About this space">
                <p style={{ margin: 0, whiteSpace: "pre-wrap" }}>
                  {listing.description}
                </p>
              </Panel>
            ) : null}

            <Panel title="When it is available">
              {availability.loading ? (
                <Loading />
              ) : (
                <ul
                  className="stack stack--sm"
                  style={{ margin: 0, paddingLeft: "1.1rem" }}
                >
                  {schedule.map((line) => (
                    <li key={line} className="small">
                      {line}
                    </li>
                  ))}
                </ul>
              )}
              <p
                className="tiny muted"
                style={{ marginTop: "0.75rem", marginBottom: 0 }}
              >
                Times shown are local. Exact availability is confirmed when you
                pick your dates.
              </p>
            </Panel>

            <Panel title="Where it is">
              <MapView
                markers={[
                  {
                    id: listing.id,
                    latitude: listing.latitude,
                    longitude: listing.longitude,
                    active: true,
                    label: listing.title,
                  },
                ]}
                center={{
                  latitude: listing.latitude,
                  longitude: listing.longitude,
                }}
                zoom={16}
              />
              <p
                className="tiny muted"
                style={{ marginTop: "0.6rem", marginBottom: 0 }}
              >
                Exact access instructions are shared once your booking is
                confirmed.
              </p>
            </Panel>

            <Panel title="Provided by">
              <div className="row">
                <div>
                  <div className="bold">{listing.provider.display_name}</div>
                  <div className="small muted">
                    {listing.provider.provider_type === "SOCIETY"
                      ? "Society / organisation"
                      : "Individual host"}
                    {" · "}
                    Member since{" "}
                    {new Date(listing.provider.member_since).getFullYear()}
                  </div>
                </div>
                <div className="spacer" />
                {listing.provider.verification_status === "VERIFIED" ? (
                  <span className="badge badge--green">Verified</span>
                ) : null}
              </div>
            </Panel>

            <Panel
              title={`Reviews${reviews.data?.count ? ` (${reviews.data.count})` : ""}`}
            >
              {reviews.loading ? (
                <Loading />
              ) : !reviews.data?.items.length ? (
                <p className="small muted" style={{ margin: 0 }}>
                  No reviews yet. Ratings appear here once renters complete a
                  booking.
                </p>
              ) : (
                <div className="stack">
                  {reviews.data.items.map((review) => (
                    <div key={review.id} className="stack stack--sm">
                      <div className="row" style={{ gap: "0.5rem" }}>
                        <Stars rating={review.rating} />
                        <span className="small muted">
                          {review.author_name}
                        </span>
                      </div>
                      {review.comment ? (
                        <p className="small" style={{ margin: 0 }}>
                          {review.comment}
                        </p>
                      ) : null}
                    </div>
                  ))}
                </div>
              )}
            </Panel>
          </div>

          {/* --- Booking widget --- */}
          <div className="search-layout__map">
            <Panel
              title={
                <div>
                  <div style={{ fontSize: "1.35rem", fontWeight: 700 }}>
                    {money(
                      listing.prices.find((price) => price.unit === unit)
                        ?.amount,
                    )}{" "}
                    <span className="small muted">/ {UNIT_LABEL[unit]}</span>
                  </div>
                </div>
              }
            >
              <div className="stack">
                <div className="chips">
                  {listing.prices.map((price) => (
                    <button
                      key={price.unit}
                      type="button"
                      className={`chip${unit === price.unit ? " chip--on" : ""}`}
                      onClick={() => setUnit(price.unit)}
                    >
                      {UNIT_ADJECTIVE[price.unit]}
                    </button>
                  ))}
                </div>

                <Field
                  label={unit === "HOURLY" ? "Starts at" : "Starts on"}
                  hint={
                    unit !== "HOURLY"
                      ? "Daily and monthly bookings start at midnight."
                      : undefined
                  }
                >
                  <input
                    type={unit === "HOURLY" ? "datetime-local" : "date"}
                    value={unit === "HOURLY" ? startAt : startAt.slice(0, 10)}
                    min={
                      unit === "HOURLY"
                        ? toLocalInput(new Date())
                        : new Date().toISOString().slice(0, 10)
                    }
                    onChange={(event) => {
                      const value = event.target.value;
                      setStartAt(unit === "HOURLY" ? value : `${value}T00:00`);
                    }}
                  />
                </Field>

                <Field label={`Number of ${UNIT_PLURAL[unit]}`}>
                  <input
                    type="number"
                    min={1}
                    max={unit === "HOURLY" ? 24 : unit === "DAILY" ? 60 : 12}
                    value={quantity}
                    onChange={(event) =>
                      setQuantity(Math.max(1, Number(event.target.value)))
                    }
                  />
                </Field>

                {user ? (
                  vehicles.data && vehicles.data.length > 0 ? (
                    <>
                      <BayPicker
                        spaceId={listing.id}
                        startAt={startAt || null}
                        endAt={quote?.end_at ?? null}
                        value={slotIndex}
                        onChange={setSlotIndex}
                      />

                      <Field
                        label="Vehicle"
                        hint="The registration number appears on your booking."
                      >
                        <select
                          value={vehicleId}
                          onChange={(event) => setVehicleId(event.target.value)}
                        >
                          {vehicles.data
                            .filter((vehicle) =>
                              listing.vehicle_types.includes(
                                vehicle.vehicle_type,
                              ),
                            )
                            .map((vehicle) => (
                              <option key={vehicle.id} value={vehicle.id}>
                                {vehicle.registration_number} ·{" "}
                                {VEHICLE_LABEL[vehicle.vehicle_type]}
                                {vehicle.make_model
                                  ? ` · ${vehicle.make_model}`
                                  : ""}
                              </option>
                            ))}
                        </select>
                      </Field>
                    </>
                  ) : (
                    <Alert kind="info">
                      Add a vehicle before booking.{" "}
                      <Link to="/vehicles">Add a vehicle</Link>
                    </Alert>
                  )
                ) : null}

                <Field label="Note for the provider (optional)">
                  <textarea
                    value={notes}
                    maxLength={1000}
                    rows={2}
                    onChange={(event) => setNotes(event.target.value)}
                    placeholder="Anything they should know, e.g. arrival time"
                  />
                </Field>

                {quoteError ? <Alert kind="error">{quoteError}</Alert> : null}

                {quote ? (
                  <div className="stack stack--sm">
                    {!quote.available ? (
                      <Alert kind="warn">
                        {quote.unavailable_reason ??
                          "Not available for those times"}
                      </Alert>
                    ) : null}
                    <div>
                      <div className="summary__line">
                        <span>
                          {money(quote.unit_price)} × {Number(quote.quantity)}{" "}
                          {UNIT_PLURAL[quote.unit]}
                        </span>
                        <span className="numeric">
                          {money(quote.base_amount)}
                        </span>
                      </div>
                      <div className="summary__line">
                        <span className="muted">Platform fee</span>
                        <span className="numeric muted">
                          {money(quote.platform_fee)}
                        </span>
                      </div>
                      <div className="summary__line">
                        <span className="muted">Taxes</span>
                        <span className="numeric muted">
                          {money(quote.tax_amount)}
                        </span>
                      </div>
                      <div className="summary__total">
                        <span>Total</span>
                        <span className="numeric">
                          {money(quote.total_amount)}
                        </span>
                      </div>
                    </div>
                  </div>
                ) : null}

                <ErrorMessage error={book.error} />

                {user ? (
                  <button
                    type="button"
                    className="btn btn--block btn--lg"
                    disabled={!canBook || book.pending}
                    onClick={() => void book.run()}
                  >
                    {book.pending
                      ? "Booking…"
                      : listing.requires_approval
                        ? "Request booking"
                        : "Book parking"}
                  </button>
                ) : (
                  <Link
                    to="/login"
                    state={{ from: `/parking/${listing.id}` }}
                    className="btn btn--block btn--lg"
                  >
                    Sign in to book
                  </Link>
                )}

                {listing.requires_approval ? (
                  <p className="tiny muted center" style={{ margin: 0 }}>
                    This provider reviews each request before payment.
                  </p>
                ) : null}
              </div>
            </Panel>
          </div>
        </div>
      </div>
    </main>
  );
}
