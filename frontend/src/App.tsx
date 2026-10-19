import { useEffect, useState } from "react";
import { Header } from "./components/Header";
import { KeysDialog } from "./components/KeysDialog";
import { StatusBar } from "./components/StatusBar";
import { isTyping } from "./hooks";
import { useLocation } from "./router";

export function App() {
  const url = useLocation();
  const [keysOpen, setKeysOpen] = useState(false);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key === "?" && !isTyping(event)) setKeysOpen(true);
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return (
    <>
      <a className="skip-link" href="#main">Skip to content</a>
      <Header path={url.pathname} />
      <main id="main" />
      <StatusBar onShowKeys={() => setKeysOpen(true)} />
      <KeysDialog open={keysOpen} onClose={() => setKeysOpen(false)} />
    </>
  );
}
