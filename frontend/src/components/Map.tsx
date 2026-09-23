/**
 * MapLibre GL map wrapper (PRD §21).
 *
 * The map is driven imperatively, so this component owns the map instance and
 * syncs markers when the props change. Its props are deliberately identical to
 * the Leaflet version this replaced, so callers did not have to change.
 *
 * Basemap selection, in order:
 *   1. MapTiler vector tiles when VITE_MAPTILER_KEY is set — smooth zoom, a
 *      light and a dark style, and labels that suit an Indian city.
 *   2. OpenStreetMap raster tiles otherwise, so the app still renders a map with
 *      no account and no key. CARTO was tried first and is NOT usable here: it
 *      answers 200 but stamps "API KEY REQUIRED" across every tile.
 * Both are wrapped in a MapLibre style object, so the rest of the component
 * never learns which one it got.
 */
import { useEffect, useRef, useState } from "react";
// maplibre-gl v6 dropped its default export, so the whole module is imported
// as a namespace. Every `maplibregl.X` call site below is unchanged.
import * as maplibregl from "maplibre-gl";
import type { StyleSpecification } from "maplibre-gl";

export interface MapMarker {
  id: string;
  latitude: number;
  longitude: number;
  /** HTML shown in the popup. Built by the caller from its own data. */
  popupHtml?: string;
  label?: string;
  active?: boolean;
}

interface MapProps {
  markers?: MapMarker[];
  center?: { latitude: number; longitude: number };
  zoom?: number;
  className?: string;
  /** Lets the provider drop a pin — used by the listing form. */
  onPick?: (latitude: number, longitude: number) => void;
  onMarkerClick?: (id: string) => void;
  fitToMarkers?: boolean;
}

const DEFAULT_CENTER = { latitude: 23.0225, longitude: 72.5714 }; // Ahmedabad
const MAPTILER_KEY = import.meta.env.VITE_MAPTILER_KEY ?? "";

const OSM_ATTRIBUTION =
  '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors';

/**
 * Keyless fallback. OSM publishes no dark tiles, so dark mode is handled by
 * filtering the canvas in CSS — see [data-basemap="raster"] in styles.css.
 */
function rasterStyle(): StyleSpecification {
  return {
    version: 8,
    sources: {
      basemap: {
        type: "raster",
        tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
        tileSize: 256,
        maxzoom: 19,
        attribution: OSM_ATTRIBUTION,
      },
    },
    layers: [{ id: "basemap", type: "raster", source: "basemap" }],
  };
}

function styleFor(dark: boolean): string | StyleSpecification {
  if (!MAPTILER_KEY) return rasterStyle();
  const name = dark ? "streets-v2-dark" : "streets-v2";
  return `https://api.maptiler.com/maps/${name}/style.json?key=${MAPTILER_KEY}`;
}

/**
 * MapLibre is WebGL-only and throws when a context cannot be created. That is
 * not rare in this market — budget Android devices, GPU blocklists and locked
 * down browsers all hit it — and an unhandled throw here blanks the whole page.
 * Probe once so we can degrade to a useful panel instead.
 */
let webglOk: boolean | null = null;
function hasWebGL(): boolean {
  if (webglOk !== null) return webglOk;
  try {
    const canvas = document.createElement("canvas");
    webglOk = Boolean(
      canvas.getContext("webgl2") ||
        canvas.getContext("webgl") ||
        canvas.getContext("experimental-webgl"),
    );
  } catch {
    webglOk = false;
  }
  return webglOk;
}

function prefersDark(): boolean {
  const explicit = document.documentElement.getAttribute("data-theme");
  if (explicit === "dark") return true;
  if (explicit === "light") return false;
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ?? false;
}

/** A price pill, or a plain pin when the caller gave no label. */
function pinElement(marker: MapMarker): HTMLElement {
  const el = document.createElement("button");
  el.type = "button";
  el.className = `map-pin${marker.active ? " map-pin--on" : ""}${
    marker.label ? "" : " map-pin--dot"
  }`;
  if (marker.label) el.textContent = marker.label;
  el.setAttribute("aria-label", marker.label ?? "Parking space");
  return el;
}

export default function MapView({
  markers = [],
  center,
  zoom = 13,
  className = "map",
  onPick,
  onMarkerClick,
  fitToMarkers = true,
}: MapProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const mapRef = useRef<maplibregl.Map | null>(null);
  const markersRef = useRef<maplibregl.Marker[]>([]);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const supported = hasWebGL();

  // Callbacks live in refs so the map is built once and never torn down when a
  // parent re-renders with a new closure.
  const onPickRef = useRef(onPick);
  const onMarkerClickRef = useRef(onMarkerClick);
  onPickRef.current = onPick;
  onMarkerClickRef.current = onMarkerClick;

  // --- Create the map once. ------------------------------------------------ #
  useEffect(() => {
    if (!containerRef.current || mapRef.current || !supported) return;
    const start = center ?? DEFAULT_CENTER;
    let map: maplibregl.Map;
    try {
      map = new maplibregl.Map({
        container: containerRef.current,
        style: styleFor(prefersDark()),
        center: [start.longitude, start.latitude],
        zoom,
        attributionControl: { compact: true },
        // Scroll should scroll the page; the user zooms with the controls or a
        // pinch, which is what the Leaflet version did too.
        scrollZoom: false,
      });
    } catch (error) {
      // A context that fails at construction time is not recoverable.
      console.warn("Map unavailable", error);
      setFailed(true);
      return;
    }
    map.on("error", (event: maplibregl.ErrorEvent) => console.warn("Map error", event?.error ?? event));
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    map.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), "top-right");
    map.on("click", (event: maplibregl.MapMouseEvent) => {
      onPickRef.current?.(event.lngLat.lat, event.lngLat.lng);
    });
    map.on("load", () => setReady(true));
    mapRef.current = map;

    return () => {
      map.remove();
      mapRef.current = null;
      markersRef.current = [];
      setReady(false);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Follow the viewer's theme. ------------------------------------------ #
  useEffect(() => {
    const media = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!media) return;
    const apply = () => mapRef.current?.setStyle(styleFor(prefersDark()));
    media.addEventListener("change", apply);
    const observer = new MutationObserver(apply);
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme"] });
    return () => {
      media.removeEventListener("change", apply);
      observer.disconnect();
    };
  }, []);

  // --- Re-draw markers whenever they change. ------------------------------- #
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;

    for (const existing of markersRef.current) existing.remove();
    markersRef.current = [];

    for (const marker of markers) {
      const element = pinElement(marker);
      element.addEventListener("click", (event) => {
        event.stopPropagation();
        onMarkerClickRef.current?.(marker.id);
      });
      const pin = new maplibregl.Marker({ element, anchor: "center" }).setLngLat([
        marker.longitude,
        marker.latitude,
      ]);
      if (marker.popupHtml) {
        pin.setPopup(
          new maplibregl.Popup({ offset: 18, closeButton: false, maxWidth: "260px" }).setHTML(
            `<div class="map-popup">${marker.popupHtml}</div>`,
          ),
        );
      }
      pin.addTo(map);
      markersRef.current.push(pin);
    }

    if (fitToMarkers && markers.length > 1) {
      const bounds = new maplibregl.LngLatBounds();
      for (const marker of markers) bounds.extend([marker.longitude, marker.latitude]);
      map.fitBounds(bounds, { padding: 56, maxZoom: 16, duration: 400 });
    } else if (markers.length === 1) {
      map.easeTo({
        center: [markers[0].longitude, markers[0].latitude],
        zoom: Math.max(map.getZoom(), 15),
        duration: 400,
      });
    }
  }, [markers, fitToMarkers, ready]);

  // --- Follow an externally controlled centre (e.g. "use my location"). ---- #
  useEffect(() => {
    if (mapRef.current && center) {
      mapRef.current.easeTo({ center: [center.longitude, center.latitude], duration: 400 });
    }
  }, [center?.latitude, center?.longitude]);

  if (!supported || failed) {
    return (
      <div className={`${className} map--fallback`} role="note">
        <p className="bold">Map unavailable</p>
        <p className="small muted">
          This browser cannot display the map, but everything else works — the list below has the
          same {markers.length === 1 ? "place" : "places"}.
        </p>
      </div>
    );
  }

  return <div ref={containerRef} className={className} data-basemap={MAPTILER_KEY ? "vector" : "raster"} />;
}
