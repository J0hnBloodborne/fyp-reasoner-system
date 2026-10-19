import { Link, useTitle } from "../router";
import "./pages.css";

export function NotFound({ path }: { path: string }) {
  useTitle("Page not found");
  return (
    <main className="page page--center" id="main">
      <div className="wrong-way" role="img" aria-label="Wrong way road sign">
        <span>WRONG</span>
        <span>WAY</span>
      </div>
      <h1>No page at {path}</h1>
      <p className="muted">The link may be mistyped, or the record was never imported.</p>
      <Link href="/" className="btn btn--primary">Go to search</Link>
    </main>
  );
}
