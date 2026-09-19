/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Shared secret used only by the sandbox gateway; never a real credential. */
  readonly VITE_MOCK_GATEWAY_SECRET?: string;
  /**
   * MapTiler API key for vector basemaps. Optional: without it the map falls
   * back to keyless CARTO raster tiles, which is enough to run the pilot.
   */
  readonly VITE_MAPTILER_KEY?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
