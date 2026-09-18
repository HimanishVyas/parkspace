/**
 * Leaflet map wrapper (PRD §21).
 *
 * Leaflet is driven imperatively, so this component owns the map instance and
 * syncs markers when the props change. OpenStreetMap tiles need no API key,
 * which keeps the pilot free of another vendor dependency.
 */
import { useEffect, useRef } from "react";
import L from "leaflet";

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
  /** Lets the renter drop a pin — used by the listing form. */
  onPick?: (latitude: number, longitude: number) => void;
  onMarkerClick?: (id: string) => void;
  fitToMarkers?: boolean;
}

const DEFAULT_CENTER = { latitude: 23.0225, longitude: 72.5714 }; // Ahmedabad

function pinIcon(active: boolean, label?: string): L.DivIcon {
  const background = active ? "#0f766e" : "#ffffff";
  const color = active ? "#ffffff" : "#0f766e";
  // A price label has no fixed width, so a numeric iconAnchor would clip it off
  // centre. Anchoring at the point and centring with a transform always fits.
  return L.divIcon({
    className: "",
    html: `<div style="
      position:absolute;transform:translate(-50%,-50%);
      background:${background};color:${color};border:2px solid #0f766e;
      border-radius:999px;padding:3px 9px;font:600 12px/1.4 system-ui,sans-serif;
      white-space:nowrap;box-shadow:0 1px 4px rgba(15,23,42,.35);
    ">${label ?? "\u2022"}</div>`,
    iconSize: [0, 0],
    iconAnchor: [0, 0],
  });
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
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const onPickRef = useRef(onPick);
  const onMarkerClickRef = useRef(onMarkerClick);
  onPickRef.current = onPick;
  onMarkerClickRef.current = onMarkerClick;

  // Create the map once.
  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const start = center ?? DEFAULT_CENTER;
    const map = L.map(containerRef.current, { scrollWheelZoom: false }).setView(
      [start.latitude, start.longitude],
      zoom,
    );
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
      maxZoom: 19,
    }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    map.on("click", (event: L.LeafletMouseEvent) => {
      onPickRef.current?.(event.latlng.lat, event.latlng.lng);
    });
    mapRef.current = map;
    // Leaflet mis-measures inside a container that was still laying out.
    setTimeout(() => map.invalidateSize(), 120);
    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-draw markers whenever they change.
  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    for (const marker of markers) {
      const pin = L.marker([marker.latitude, marker.longitude], {
        icon: pinIcon(Boolean(marker.active), marker.label),
      });
      if (marker.popupHtml) pin.bindPopup(`<div class="map-popup">${marker.popupHtml}</div>`);
      pin.on("click", () => onMarkerClickRef.current?.(marker.id));
      pin.addTo(layer);
    }
    if (fitToMarkers && markers.length > 1) {
      map.fitBounds(L.latLngBounds(markers.map((m) => [m.latitude, m.longitude] as [number, number])), {
        padding: [40, 40],
        maxZoom: 16,
      });
    } else if (markers.length === 1) {
      map.setView([markers[0].latitude, markers[0].longitude], Math.max(map.getZoom(), 15));
    }
  }, [markers, fitToMarkers]);

  // Follow an externally controlled centre (e.g. "use my location").
  useEffect(() => {
    if (mapRef.current && center) {
      mapRef.current.setView([center.latitude, center.longitude], mapRef.current.getZoom());
    }
  }, [center?.latitude, center?.longitude]);

  return <div ref={containerRef} className={className} />;
}
