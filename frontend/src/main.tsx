import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";
import ErrorBoundary from "./components/ErrorBoundary";
import { AuthProvider } from "./lib/auth";
import { ThemeProvider, applyStoredThemeEarly } from "./lib/theme";
// MapLibre ships its own stylesheet for controls, popups and the canvas; it must
// load before ours so `styles.css` can restyle the popup and control chrome.
import "maplibre-gl/dist/maplibre-gl.css";
import "./styles.css";

// Stamp the theme before React mounts so the first paint is not a flash of
// the wrong one.
applyStoredThemeEarly();

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <BrowserRouter>
      <ThemeProvider>
        <AuthProvider>
          <ErrorBoundary>
            <App />
          </ErrorBoundary>
        </AuthProvider>
      </ThemeProvider>
    </BrowserRouter>
  </React.StrictMode>,
);
