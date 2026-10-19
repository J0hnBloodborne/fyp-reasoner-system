import { Link, useTitle } from "../router";
import "./pages.css";

export function NotFound({ path }: { path: string }) {
  useTitle("Page not found");
  return (
    <main className="page page--center" id="main">
      <div className="no-signal" role="img" aria-label="Empty monitor showing no signal">
        <span className="no-signal__text">NO SIGNAL</span>
        <span className="burn">00:00:00:00</span>
      </div>
      <h1>No page at {path}</h1>
      <p className="muted">The link may be mistyped, or the record was never imported.</p>
      <Link href="/" className="btn btn--primary">Go to search</Link>
    </main>
  );
}
