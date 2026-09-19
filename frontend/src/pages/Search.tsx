import { useCallback, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import MapView, { type MapMarker } from "../components/LazyMap";
import { Empty, ErrorMessage, Loading, Pagination, Stars } from "../components/ui";
import { api } from "../lib/api";
import {
  PARKING_TYPE_LABEL,
  UNIT_LABEL,
  VEHICLE_LABEL,
  money,
  toLocalInput,
} from "../lib/format";
import { useAsync, useDebounced, useGeolocation } from "../lib/hooks";
import type { PricingUnit, SearchResult, VehicleType } from "../lib/types";

interface GeocodeHit {
  latitude: number;
  longitude: number;
  display_name: string;
}

const LIMIT = 12;

function priceFor(result: SearchResult, unit: PricingUnit): string | null {
  return result.prices.find((price) => price.unit === unit)?.amount ?? result.prices[0]?.amount ?? null;
}

function unitOf(result: SearchResult, unit: PricingUnit): PricingUnit {
  return result.prices.some((price) => price.unit === unit) ? unit : (result.prices[0]?.unit ?? unit);
}

export default function Search() {
  const [params, setParams] = useSearchParams();
  const { position, locate, pending: locating, error: locationError, setPosition } = useGeolocation();

  const [query, setQuery] = useState(params.get("q") ?? "");
  const [unit, setUnit] = useState<PricingUnit>((params.get("unit") as PricingUnit) ?? "HOURLY");
  const [startAt, setStartAt] = useState(params.get("start_at") ?? "");
  const [endAt, setEndAt] = useState(params.get("end_at") ?? "");
  const [vehicleType, setVehicleType] = useState<VehicleType | "">(
    (params.get("vehicle_type") as VehicleType) ?? "",
  );
  const [parkingType, setParkingType] = useState(params.get("parking_type") ?? "");
  const [maxPrice, setMaxPrice] = useState(params.get("max_price") ?? "");
  const [radiusKm, setRadiusKm] = useState(Number(params.get("radius_km") ?? 5));
  const [sort, setSort] = useState(params.get("sort") ?? "distance");
  const [offset, setOffset] = useState(0);
  const [focused, setFocused] = useState<string | null>(null);
  // Principle 6 (mobile first): on a phone the results matter more than the
  // filters, so the secondary row starts collapsed there and open on desktop.
  const [filtersOpen, setFiltersOpen] = useState(
    () => typeof window === "undefined" || window.innerWidth >= 700,
  );

  const debouncedQuery = useDebounced(query);
  const centre = position;

  const searchParams = useMemo(
    () => ({
      q: debouncedQuery || undefined,
      latitude: centre?.latitude,
      longitude: centre?.longitude,
      radius_km: centre ? radiusKm : undefined,
      start_at: startAt ? new Date(startAt).toISOString() : undefined,
      end_at: endAt ? new Date(endAt).toISOString() : undefined,
      unit,
      vehicle_type: vehicleType || undefined,
      parking_type: parkingType || undefined,
      max_price: maxPrice || undefined,
      sort,
      limit: LIMIT,
      offset,
    }),
    [debouncedQuery, centre, radiusKm, startAt, endAt, unit, vehicleType, parkingType, maxPrice, sort, offset],
  );

  const { data, error, loading } = useAsync(
    (signal) =>
      api.get<{ items: SearchResult[]; total: number; limit: number; offset: number }>(
        "/parking",
        searchParams as Record<string, string | number | undefined>,
        signal,
      ),
    [JSON.stringify(searchParams)],
  );

  const applyToUrl = useCallback(() => {
    const next = new URLSearchParams();
    if (query) next.set("q", query);
    if (startAt) next.set("start_at", startAt);
    if (endAt) next.set("end_at", endAt);
    if (unit) next.set("unit", unit);
    if (vehicleType) next.set("vehicle_type", vehicleType);
    if (parkingType) next.set("parking_type", parkingType);
    if (maxPrice) next.set("max_price", maxPrice);
    if (sort) next.set("sort", sort);
    if (centre) next.set("radius_km", String(radiusKm));
    setParams(next, { replace: true });
  }, [query, startAt, endAt, unit, vehicleType, parkingType, maxPrice, sort, centre, radiusKm, setParams]);

  const [geocodeHits, setGeocodeHits] = useState<GeocodeHit[]>([]);
  const lookupArea = async () => {
    if (query.trim().length < 3) return;
    try {
      const hits = await api.get<GeocodeHit[]>("/parking/geocode", { q: query.trim() });
      setGeocodeHits(hits.slice(0, 5));
      if (hits.length === 1) {
        setPosition({ latitude: hits[0].latitude, longitude: hits[0].longitude });
        setGeocodeHits([]);
      }
    } catch {
      setGeocodeHits([]);
    }
  };

  const results = data?.items ?? [];
  const markers: MapMarker[] = results.map((result) => ({
    id: result.id,
    latitude: result.latitude,
    longitude: result.longitude,
    active: focused === result.id,
    label: money(priceFor(result, unit), true),
    popupHtml: `
      <h4>${escapeHtml(result.title)}</h4>
      <p>${PARKING_TYPE_LABEL[result.parking_type]} · ${
        result.distance_km !== null ? `${result.distance_km.toFixed(1)} km away` : result.city
      }</p>
      <a href="/parking/${result.id}">View listing</a>`,
  }));

  return (
    <main className="page page--wide">
      <div className="stack">
        <div className="panel">
          <div className="panel__body stack">
            <div className="row">
              <div className="field" style={{ flex: "2 1 260px" }}>
                <span className="field__label">Where</span>
                <div className="row" style={{ gap: "0.5rem", flexWrap: "nowrap" }}>
                  <input
                    type="search"
                    placeholder="Area, landmark or address"
                    value={query}
                    onChange={(event) => {
                      setQuery(event.target.value);
                      setOffset(0);
                    }}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void lookupArea();
                      }
                    }}
                  />
                  <button type="button" className="btn btn--secondary" onClick={() => void lookupArea()}>
                    Locate
                  </button>
                </div>
              </div>
              <div className="field" style={{ flex: "0 0 auto" }}>
                <span className="field__label">&nbsp;</span>
                <button type="button" className="btn btn--secondary" onClick={locate} disabled={locating}>
                  {locating ? "Locating…" : "Use my location"}
                </button>
              </div>
            </div>

            {geocodeHits.length > 0 ? (
              <div className="stack stack--sm">
                <span className="field__label">Did you mean</span>
                {geocodeHits.map((hit) => (
                  <button
                    key={`${hit.latitude},${hit.longitude}`}
                    type="button"
                    className="btn btn--ghost btn--sm"
                    style={{ justifyContent: "flex-start", textAlign: "left" }}
                    onClick={() => {
                      setPosition({ latitude: hit.latitude, longitude: hit.longitude });
                      setGeocodeHits([]);
                      setOffset(0);
                    }}
                  >
                    {hit.display_name}
                  </button>
                ))}
              </div>
            ) : null}

            {locationError ? <p className="small muted" style={{ margin: 0 }}>{locationError}</p> : null}

            <div className="row">
              <div className="field" style={{ flex: "1 1 180px" }}>
                <span className="field__label">From</span>
                <input
                  type="datetime-local"
                  value={startAt}
                  min={toLocalInput(new Date())}
                  onChange={(event) => {
                    setStartAt(event.target.value);
                    setOffset(0);
                  }}
                />
              </div>
              <div className="field" style={{ flex: "1 1 180px" }}>
                <span className="field__label">Until</span>
                <input
                  type="datetime-local"
                  value={endAt}
                  min={startAt || toLocalInput(new Date())}
                  onChange={(event) => {
                    setEndAt(event.target.value);
                    setOffset(0);
                  }}
                />
              </div>
              <div className="field" style={{ flex: "0 1 140px" }}>
                <span className="field__label">Booking type</span>
                <select
                  value={unit}
                  onChange={(event) => {
                    setUnit(event.target.value as PricingUnit);
                    setOffset(0);
                  }}
                >
                  <option value="HOURLY">Hourly</option>
                  <option value="DAILY">Daily</option>
                  <option value="MONTHLY">Monthly</option>
                </select>
              </div>
            </div>

            <button
              type="button"
              className="btn btn--ghost btn--sm"
              style={{ alignSelf: "flex-start" }}
              aria-expanded={filtersOpen}
              onClick={() => setFiltersOpen((open) => !open)}
            >
              {filtersOpen ? "Hide filters" : "More filters"}
            </button>

            <div className="row" hidden={!filtersOpen}>
              <div className="field" style={{ flex: "1 1 130px" }}>
                <span className="field__label">Vehicle</span>
                <select
                  value={vehicleType}
                  onChange={(event) => {
                    setVehicleType(event.target.value as VehicleType | "");
                    setOffset(0);
                  }}
                >
                  <option value="">Any</option>
                  <option value="BIKE">Bike</option>
                  <option value="CAR">Car</option>
                  <option value="SUV">SUV</option>
                </select>
              </div>
              <div className="field" style={{ flex: "1 1 130px" }}>
                <span className="field__label">Parking type</span>
                <select
                  value={parkingType}
                  onChange={(event) => {
                    setParkingType(event.target.value);
                    setOffset(0);
                  }}
                >
                  <option value="">Any</option>
                  <option value="OPEN">Open</option>
                  <option value="COVERED">Covered</option>
                  <option value="BASEMENT">Basement</option>
                  <option value="GARAGE">Garage</option>
                </select>
              </div>
              <div className="field" style={{ flex: "1 1 120px" }}>
                <span className="field__label">Max price</span>
                <input
                  type="number"
                  min={0}
                  placeholder="Any"
                  value={maxPrice}
                  onChange={(event) => {
                    setMaxPrice(event.target.value);
                    setOffset(0);
                  }}
                />
              </div>
              {centre ? (
                <div className="field" style={{ flex: "1 1 130px" }}>
                  <span className="field__label">Within {radiusKm} km</span>
                  <input
                    type="range"
                    min={1}
                    max={25}
                    value={radiusKm}
                    onChange={(event) => {
                      setRadiusKm(Number(event.target.value));
                      setOffset(0);
                    }}
                  />
                </div>
              ) : null}
              <div className="field" style={{ flex: "1 1 130px" }}>
                <span className="field__label">Sort by</span>
                <select value={sort} onChange={(event) => setSort(event.target.value)}>
                  <option value="distance">Distance</option>
                  <option value="price_asc">Price: low to high</option>
                  <option value="price_desc">Price: high to low</option>
                  <option value="rating">Rating</option>
                  <option value="newest">Newest</option>
                </select>
              </div>
              <div className="field" style={{ flex: "0 0 auto" }}>
                <span className="field__label">&nbsp;</span>
                <button type="button" className="btn btn--secondary" onClick={applyToUrl}>
                  Save search
                </button>
              </div>
            </div>
          </div>
        </div>

        <ErrorMessage error={error} />

        <div className="search-layout">
          <div className="stack">
            <div className="row row--between">
              <h1 style={{ fontSize: "1.25rem", margin: 0 }}>
                {loading ? "Searching…" : `${data?.total ?? 0} space${data?.total === 1 ? "" : "s"} available`}
              </h1>
              {startAt && endAt ? (
                <span className="small muted">Showing only spaces free for your times</span>
              ) : (
                <span className="small muted">Add dates to check availability</span>
              )}
            </div>

            {loading ? (
              <Loading label="Finding parking…" />
            ) : results.length === 0 ? (
              <Empty title="No parking matched your search">
                Try widening the radius, changing the times, or removing a filter.
              </Empty>
            ) : (
              <div className="grid grid--2">
                {results.map((result) => {
                  const shownUnit = unitOf(result, unit);
                  return (
                    <Link
                      key={result.id}
                      to={`/parking/${result.id}`}
                      className="card card--flush card--hover listing-card"
                      onMouseEnter={() => setFocused(result.id)}
                      onMouseLeave={() => setFocused(null)}
                      style={{ color: "inherit" }}
                    >
                      <div className="listing-card__photo">
                        {result.photo_url ? (
                          <img src={result.photo_url} alt="" loading="lazy" />
                        ) : (
                          <span aria-hidden="true">🅿️</span>
                        )}
                      </div>
                      <div className="listing-card__body">
                        <div className="row" style={{ gap: "0.4rem" }}>
                          <span className="badge badge--teal">{PARKING_TYPE_LABEL[result.parking_type]}</span>
                          {result.distance_km !== null ? (
                            <span className="badge">{result.distance_km.toFixed(1)} km away</span>
                          ) : null}
                        </div>
                        <div className="bold truncate">{result.title}</div>
                        <div className="small muted">
                          {result.vehicle_types.map((type) => VEHICLE_LABEL[type]).join(" · ")}
                        </div>
                        <Stars rating={result.rating_average} count={result.rating_count} />
                        <div className="spacer" />
                        <div className="listing-card__price">
                          {money(priceFor(result, shownUnit))}{" "}
                          <span>/ {UNIT_LABEL[shownUnit]}</span>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>
            )}

            <Pagination
              total={data?.total ?? 0}
              limit={LIMIT}
              offset={offset}
              onChange={(next) => {
                setOffset(next);
                window.scrollTo({ top: 0, behavior: "smooth" });
              }}
            />
          </div>

          <div className="search-layout__map">
            <MapView
              markers={markers}
              center={centre ?? undefined}
              className="map map--tall"
              onMarkerClick={setFocused}
            />
            <p className="tiny muted center" style={{ marginTop: "0.5rem" }}>
              Tap a marker to preview a space.
            </p>
          </div>
        </div>
      </div>
    </main>
  );
}

function escapeHtml(value: string): string {
  return value.replace(/[&<>"']/g, (char) => {
    const map: Record<string, string> = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return map[char];
  });
}
