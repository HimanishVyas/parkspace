/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Shared secret used only by the sandbox gateway; never a real credential. */
  readonly VITE_MOCK_GATEWAY_SECRET?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
