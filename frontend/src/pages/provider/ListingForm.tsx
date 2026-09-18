import { useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import MapView from "../../components/Map";
import { Alert, ErrorMessage, Field, Loading, Panel } from "../../components/ui";
import { api } from "../../lib/api";
import { PARKING_TYPE_LABEL, UNIT_LABEL, VEHICLE_LABEL } from "../../lib/format";
import { useAsync, useSubmit } from "../../lib/hooks";
import type { ParkingSpace, ParkingType, PricingUnit, VehicleType } from "../../lib/types";

const PARKING_TYPES: ParkingType[] = ["OPEN", "COVERED", "BASEMENT", "GARAGE"];
const VEHICLE_TYPES: VehicleType[] = ["BIKE", "CAR", "SUV"];
const UNITS: PricingUnit[] = ["HOURLY", "DAILY", "MONTHLY"];

interface GeocodeHit {
  latitude: number;
  longitude: number;
  display_name: string;
}

export default function ListingForm() {
  const { spaceId } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(spaceId);

  const existing = useAsync(
    (signal) =>
      spaceId
        ? api.get<ParkingSpace>(`/parking/mine/${spaceId}`, undefined, signal)
        : Promise.resolve(null),
    [spaceId],
  );

  const [form, setForm] = useState({
    title: "",
    description: "",
    parking_type: "COVERED" as ParkingType,
    vehicle_types: ["CAR"] as VehicleType[],
    address_line: "",
    landmark: "",
    city: "",
    state: "",
    pincode: "",
    latitude: 23.0225,
    longitude: 72.5714,
    access_instructions: "",
    total_slots: 1,
    requires_approval: false,
  });
  const [prices, setPrices] = useState<Record<PricingUnit, string>>({
    HOURLY: "50",
    DAILY: "",
    MONTHLY: "",
  });
  const [authorityConfirmed, setAuthorityConfirmed] = useState(false);
  const [geocodeHits, setGeocodeHits] = useState<GeocodeHit[]>([]);

  useEffect(() => {
    const space = existing.data;
    if (!space) return;
    setForm({
      title: space.title,
      description: space.description ?? "",
      parking_type: space.parking_type,
      vehicle_types: space.vehicle_types,
      address_line: space.address_line,
      landmark: space.landmark ?? "",
      city: space.city,
      state: space.state ?? "",
      pincode: space.pincode ?? "",
      latitude: Number(space.latitude),
      longitude: Number(space.longitude),
      access_instructions: space.access_instructions ?? "",
      total_slots: space.total_slots,
      requires_approval: space.requires_approval,
    });
    setPrices({
      HOURLY: space.prices.find((p) => p.unit === "HOURLY")?.amount ?? "",
      DAILY: space.prices.find((p) => p.unit === "DAILY")?.amount ?? "",
      MONTHLY: space.prices.find((p) => p.unit === "MONTHLY")?.amount ?? "",
    });
    setAuthorityConfirmed(space.authority_confirmed);
  }, [existing.data]);

  const lookupAddress = async () => {
    const query = [form.address_line, form.landmark, form.city].filter(Boolean).join(", ");
    if (query.trim().length < 4) return;
    try {
      const hits = await api.get<GeocodeHit[]>("/parking/geocode", { q: query });
      setGeocodeHits(hits.slice(0, 5));
      if (hits.length >= 1) {
        setForm((current) => ({
          ...current,
          latitude: hits[0].latitude,
          longitude: hits[0].longitude,
        }));
      }
    } catch {
      setGeocodeHits([]);
    }
  };

  const priceList = () =>
    UNITS.filter((unit) => prices[unit] && Number(prices[unit]) > 0).map((unit) => ({
      unit,
      amount: prices[unit],
    }));

  const save = useSubmit(async (publishAfter: boolean) => {
    const payload = {
      ...form,
      description: form.description.trim() || null,
      landmark: form.landmark.trim() || null,
      state: form.state.trim() || null,
      pincode: form.pincode.trim() || null,
      access_instructions: form.access_instructions.trim() || null,
      prices: priceList(),
    };

    let space: ParkingSpace;
    if (editing && spaceId) {
      space = await api.patch<ParkingSpace>(`/parking/${spaceId}`, payload);
    } else {
      space = await api.post<ParkingSpace>("/parking", {
        ...payload,
        authority_confirmed: authorityConfirmed,
      });
    }

    if (publishAfter) {
      await api.post(`/parking/${space.id}/publish`);
      navigate("/provider/listings");
    } else {
      navigate(`/provider/listings/${space.id}/availability`);
    }
  });

  if (editing && existing.loading) return <Loading />;

  const fieldErrors = save.error?.fieldErrors ?? {};
  const canSubmit =
    form.title.trim().length >= 4 &&
    form.address_line.trim().length >= 5 &&
    form.city.trim().length >= 2 &&
    form.vehicle_types.length > 0 &&
    priceList().length > 0 &&
    (editing || authorityConfirmed);

  return (
    <main className="page">
      <div className="stack">
        <Link to="/provider/listings" className="small">
          ← My parking spaces
        </Link>
        <h1>{editing ? "Edit parking space" : "Add a parking space"}</h1>

        <ErrorMessage error={save.error} />

        <form
          className="stack"
          onSubmit={(event) => {
            event.preventDefault();
            void save.run(false);
          }}
        >
          <Panel title="The basics">
            <div className="stack">
              <Field label="Listing title" required hint="What a renter sees first." error={fieldErrors.title}>
                <input
                  type="text"
                  required
                  minLength={4}
                  maxLength={150}
                  value={form.title}
                  placeholder="Covered parking near Ashram Road metro"
                  onChange={(event) => setForm({ ...form, title: event.target.value })}
                />
              </Field>
              <Field label="Description" error={fieldErrors.description}>
                <textarea
                  rows={4}
                  maxLength={4000}
                  value={form.description}
                  placeholder="Gated compound, well lit, easy turning space. Two minutes from the main road."
                  onChange={(event) => setForm({ ...form, description: event.target.value })}
                />
              </Field>
              <Field label="Parking type" required>
                <div className="chips">
                  {PARKING_TYPES.map((type) => (
                    <button
                      key={type}
                      type="button"
                      className={`chip${form.parking_type === type ? " chip--on" : ""}`}
                      onClick={() => setForm({ ...form, parking_type: type })}
                    >
                      {PARKING_TYPE_LABEL[type]}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label="Vehicles this space fits" required>
                <div className="chips">
                  {VEHICLE_TYPES.map((type) => {
                    const on = form.vehicle_types.includes(type);
                    return (
                      <button
                        key={type}
                        type="button"
                        className={`chip${on ? " chip--on" : ""}`}
                        onClick={() =>
                          setForm({
                            ...form,
                            vehicle_types: on
                              ? form.vehicle_types.filter((value) => value !== type)
                              : [...form.vehicle_types, type],
                          })
                        }
                      >
                        {VEHICLE_LABEL[type]}
                      </button>
                    );
                  })}
                </div>
              </Field>
              <div className="row" style={{ gap: "0.75rem", alignItems: "flex-start" }}>
                <div style={{ flex: "0 1 160px" }}>
                  <Field label="Number of bays" hint="How many vehicles fit at once.">
                    <input
                      type="number"
                      min={1}
                      max={500}
                      value={form.total_slots}
                      onChange={(event) =>
                        setForm({ ...form, total_slots: Math.max(1, Number(event.target.value)) })
                      }
                    />
                  </Field>
                </div>
              </div>
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={form.requires_approval}
                  onChange={(event) => setForm({ ...form, requires_approval: event.target.checked })}
                />
                <span>
                  Review each booking before it is paid for
                  <span className="field__hint" style={{ display: "block" }}>
                    Slower for renters, but you approve who parks.
                  </span>
                </span>
              </label>
            </div>
          </Panel>

          <Panel title="Where it is">
            <div className="stack">
              <Field label="Address" required error={fieldErrors.address_line}>
                <input
                  type="text"
                  required
                  minLength={5}
                  value={form.address_line}
                  placeholder="12 Ashram Road"
                  onChange={(event) => setForm({ ...form, address_line: event.target.value })}
                />
              </Field>
              <div className="row" style={{ gap: "0.75rem" }}>
                <div style={{ flex: 1 }}>
                  <Field label="Landmark">
                    <input
                      type="text"
                      value={form.landmark}
                      placeholder="Opposite the metro station"
                      onChange={(event) => setForm({ ...form, landmark: event.target.value })}
                    />
                  </Field>
                </div>
                <div style={{ flex: 1 }}>
                  <Field label="City" required error={fieldErrors.city}>
                    <input
                      type="text"
                      required
                      value={form.city}
                      placeholder="Ahmedabad"
                      onChange={(event) => setForm({ ...form, city: event.target.value })}
                    />
                  </Field>
                </div>
              </div>
              <div className="row" style={{ gap: "0.75rem" }}>
                <div style={{ flex: 1 }}>
                  <Field label="State">
                    <input
                      type="text"
                      value={form.state}
                      onChange={(event) => setForm({ ...form, state: event.target.value })}
                    />
                  </Field>
                </div>
                <div style={{ flex: 1 }}>
                  <Field label="PIN code">
                    <input
                      type="text"
                      maxLength={12}
                      value={form.pincode}
                      onChange={(event) => setForm({ ...form, pincode: event.target.value })}
                    />
                  </Field>
                </div>
                <div style={{ flex: "0 0 auto", alignSelf: "flex-end" }}>
                  <button type="button" className="btn btn--secondary" onClick={() => void lookupAddress()}>
                    Find on map
                  </button>
                </div>
              </div>

              {geocodeHits.length > 1 ? (
                <div className="stack stack--sm">
                  <span className="field__label">Pick the closest match</span>
                  {geocodeHits.map((hit) => (
                    <button
                      key={`${hit.latitude},${hit.longitude}`}
                      type="button"
                      className="btn btn--ghost btn--sm"
                      style={{ justifyContent: "flex-start", textAlign: "left" }}
                      onClick={() => {
                        setForm({ ...form, latitude: hit.latitude, longitude: hit.longitude });
                        setGeocodeHits([]);
                      }}
                    >
                      {hit.display_name}
                    </button>
                  ))}
                </div>
              ) : null}

              <Alert kind="info">
                Drag or tap the map to place the pin exactly where a renter should drive to.
              </Alert>
              <MapView
                markers={[
                  {
                    id: "pin",
                    latitude: form.latitude,
                    longitude: form.longitude,
                    active: true,
                    label: "Your space",
                  },
                ]}
                center={{ latitude: form.latitude, longitude: form.longitude }}
                zoom={16}
                onPick={(latitude, longitude) => setForm({ ...form, latitude, longitude })}
                fitToMarkers={false}
              />
              <p className="tiny muted numeric" style={{ margin: 0 }}>
                {form.latitude.toFixed(5)}, {form.longitude.toFixed(5)}
              </p>
            </div>
          </Panel>

          <Panel title="Pricing">
            <div className="stack">
              <p className="small muted" style={{ margin: 0 }}>
                Set a price for each way you want to rent the space. Leave one blank to not offer it.
              </p>
              {UNITS.map((unit) => (
                <Field key={unit} label={`Price per ${UNIT_LABEL[unit]}`}>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={prices[unit]}
                    placeholder="Not offered"
                    onChange={(event) => setPrices({ ...prices, [unit]: event.target.value })}
                  />
                </Field>
              ))}
              <p className="tiny muted" style={{ margin: 0 }}>
                Renters pay this plus the platform fee. Your earnings are this price minus the
                platform commission — you can see the exact split on your earnings page.
              </p>
            </div>
          </Panel>

          <Panel title="Arrival instructions">
            <Field
              label="What should the renter do on arrival?"
              hint="Shared only after a booking is confirmed."
            >
              <textarea
                rows={4}
                maxLength={2000}
                value={form.access_instructions}
                placeholder={"Enter through the left gate.\nParking space is number A-12.\nShow your booking reference to security."}
                onChange={(event) => setForm({ ...form, access_instructions: event.target.value })}
              />
            </Field>
          </Panel>

          {!editing ? (
            <Panel title="Your authority to rent this space">
              <label className="checkbox">
                <input
                  type="checkbox"
                  checked={authorityConfirmed}
                  onChange={(event) => setAuthorityConfirmed(event.target.checked)}
                />
                <span>
                  I confirm that I have the necessary rights or authorization to offer this parking
                  space for rent.
                  <span className="field__hint" style={{ display: "block" }}>
                    For a society or organisation, confirm that it is permitted to offer the space.
                  </span>
                </span>
              </label>
            </Panel>
          ) : null}

          <div className="row">
            <button type="submit" className="btn" disabled={!canSubmit || save.pending}>
              {save.pending ? "Saving…" : editing ? "Save changes" : "Save and set availability"}
            </button>
            {editing ? (
              <>
                <Link to={`/provider/listings/${spaceId}/availability`} className="btn btn--secondary">
                  Availability
                </Link>
                <button
                  type="button"
                  className="btn btn--secondary"
                  disabled={!canSubmit || save.pending}
                  onClick={() => void save.run(true)}
                >
                  Save and publish
                </button>
              </>
            ) : null}
          </div>
        </form>
      </div>
    </main>
  );
}
