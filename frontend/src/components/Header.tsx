import { useStoredString } from "../hooks";
import { Link } from "../router";
import "./Header.css";

function ThemeToggle() {
  const [theme, setTheme] = useStoredString("traffic-theme", "light");
  const dark = theme === "dark";
  function toggle() {
    const next = dark ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    setTheme(next);
  }
  return (
    <button type="button" className="topbar__theme" aria-pressed={dark} onClick={toggle}>
      {dark ? "Light theme" : "Dark theme"}
    </button>
  );
}

export function Header({ path }: { path: string }) {
  const searchActive = path === "/" || path.startsWith("/incident/");
  return (
    <header className="topbar">
      <Link href="/" className="topbar__brand">TrafficSeek</Link>
      <nav className="topbar__nav" aria-label="Main">
        <Link href="/" aria-current={searchActive ? "page" : undefined}>Search</Link>
        <Link href="/import" aria-current={path === "/import" ? "page" : undefined}>Import</Link>
      </nav>
      <div className="topbar__end">
        <Link href="/analyze" className="topbar__secondary" aria-current={path === "/analyze" ? "page" : undefined}>
          Analyze an image
        </Link>
        <ThemeToggle />
      </div>
    </header>
  );
}
