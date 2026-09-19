/**
 * Code-split wrapper around the MapLibre map.
 *
 * MapLibre is ~800 kB — more than the rest of the app put together. Most routes
 * never show a map, and this is a mobile-first product in a market where data
 * costs, so the library is fetched only when a map is actually rendered.
 *
 * The props are the map's own, so callers swap the import and change nothing else.
 */
import { Suspense, lazy, type ComponentProps } from "react";
import type MapView from "./Map";

const Map = lazy(() => import("./Map"));

export type { MapMarker } from "./Map";

export default function LazyMap(props: ComponentProps<typeof MapView>) {
  return (
    <Suspense fallback={<div className={props.className ?? "map"} aria-busy="true" />}>
      <Map {...props} />
    </Suspense>
  );
}
