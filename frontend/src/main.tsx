import "@fontsource/overpass/latin-400.css";
import "@fontsource/overpass/latin-600.css";
import "@fontsource/overpass/latin-700.css";
import "@fontsource/overpass/latin-800.css";
import "@fontsource/overpass-mono/latin-400.css";
import "@fontsource/overpass-mono/latin-600.css";
import "./styles/tokens.css";
import "./styles/base.css";

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
