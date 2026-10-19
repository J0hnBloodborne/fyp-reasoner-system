import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { KeysDialog } from "./components/KeysDialog";
import { StatusBar } from "./components/StatusBar";
import { isTyping } from "./hooks";
import { AnalyzePage } from "./pages/AnalyzePage";
import { ImportPage } from "./pages/ImportPage";
import { NotFound } from "./pages/NotFound";
import { PrivacyPage } from "./pages/PrivacyPage";
import { useLocation } from "./router";
import { Workspace } from "./workspace/Workspace";

const INCIDENT = /^\/incident\/([a-f0-9]{32})$/;

export function App() {
  const url = useLocation();
  const path = url.pathname;
  const [keysOpen, setKeysOpen] = useState(false);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "?" && !isTyping(event)) setKeysOpen(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const incident = path.match(INCIDENT);
  let page;
  if (path === "/" || incident) page = <Workspace selectedId={incident?.[1] ?? null} params={url.searchParams} />;
  else if (path === "/import") page = <ImportPage />;
  else if (path === "/analyze") page = <AnalyzePage />;
  else if (path === "/privacy") page = <PrivacyPage />;
  else page = <NotFound path={path} />;

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <Header path={path} />
      {page}
      <StatusBar onShowKeys={() => setKeysOpen(true)} />
      <KeysDialog open={keysOpen} onClose={() => setKeysOpen(false)} />
    </>
  );
}
