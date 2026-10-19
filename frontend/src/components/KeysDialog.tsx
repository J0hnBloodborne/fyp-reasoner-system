import { useEffect, useRef } from "react";
import "./KeysDialog.css";

const KEYS: [string[], string][] = [
  [["/"], "Go to the search box"],
  [["↓"], "Open the next event"],
  [["↑"], "Open the previous event"],
  [["→"], "Step one evidence frame forward"],
  [["←"], "Step one evidence frame back"],
  [["Home"], "First evidence frame"],
  [["End"], "Last evidence frame"],
  [["Space"], "Play or pause the evidence frames"],
  [["T"], "Jump to the trigger frame"],
  [["?"], "Show this list"],
];

export function KeysDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);
  return (
    <dialog ref={ref} className="keys" aria-labelledby="keys-title" onClose={onClose}>
      <h2 id="keys-title">Keyboard shortcuts</h2>
      <p className="muted">Keys work on the Search screen while you are not typing in a field.</p>
      <dl>
        {KEYS.map(([keys, action]) => (
          <div key={action}>
            <dt>{keys.map((key) => <kbd key={key}>{key}</kbd>)}</dt>
            <dd>{action}</dd>
          </div>
        ))}
      </dl>
      <form method="dialog"><button className="btn">Close</button></form>
    </dialog>
  );
}
