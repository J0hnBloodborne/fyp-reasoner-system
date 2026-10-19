import { useEffect, useRef } from "react";
import "./KeysDialog.css";

const KEYS: [string[], string][] = [
  [["/"], "Go to the search box"],
  [["↓"], "Open the next event"],
  [["↑"], "Open the previous event"],
  [["→"], "Step one frame forward"],
  [["←"], "Step one frame back"],
  [["Home"], "Go to the in point, the first frame Tier-2 saw"],
  [["End"], "Go to the out point, the last frame Tier-2 saw"],
  [["Space"], "Play or pause"],
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
