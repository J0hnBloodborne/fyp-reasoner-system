import { Link, useTitle } from "../router";
import "./pages.css";

export function PrivacyPage() {
  useTitle("Privacy and terms");
  return (
    <main className="page page--prose" id="main">
      <h1>Privacy and terms</h1>
      <p className="page__lead">TrafficSeek is a research prototype for Senior Design Project 50. It runs on this computer and sends footage nowhere.</p>

      <h2>Where processing happens</h2>
      <p>The server listens on this computer only (127.0.0.1) and refuses requests from other sites. The Tier-1 detector and the vision model run locally. The only network use is the first download of model weights, and offline mode turns that off.</p>

      <h2>What is stored</h2>
      <p>Records, evidence frames and review decisions are saved in the project's <code>data</code> folder. Reviews are added, never overwritten, and the original model output is kept next to any correction. Deleting the folder deletes everything.</p>

      <h2>Cookies and tracking</h2>
      <p>The app sets no cookies and has no analytics. Your browser keeps four preferences in local storage: the theme, the results view, the open inspector tab, and the reviewer name you last typed.</p>

      <h2>Footage of people</h2>
      <p>Traffic footage shows people, faces and number plates. Import only footage you are allowed to process. The TU-DAT dataset is licensed for research use and must not be redistributed, so its frames stay out of Git and out of shared reports.</p>

      <h2>Terms of use</h2>
      <ul>
        <li>Tier-1 triggers are heuristics, and Tier-2 verdicts are a model's reading of a few frames. Neither is a calibrated probability.</li>
        <li>A human decision is advice recorded by a named reviewer. The app issues no notices, fines or legal findings.</li>
        <li>The software is provided as is, without warranty, for research and teaching.</li>
      </ul>

      <h2>Contact</h2>
      <p>Senior Design Project 50: Ahmad Saeed Zaidi, Riyan Javed Shah, Rohaan Mirza and Nishat Ahmad. Supervisor Dr. Ali Imran Sandhu, co-supervisor Dr. Khurram Jadoon.</p>

      <p><Link href="/" className="btn">Back to search</Link></p>
    </main>
  );
}
