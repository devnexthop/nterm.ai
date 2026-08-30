import { useEffect, useRef } from "react";
import type { MenuItem } from "../types";

export default function ContextMenu({
  x,
  y,
  items,
  onClose,
}: {
  x: number;
  y: number;
  items: MenuItem[];
  onClose: () => void;
}) {
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    // Bind on the next tick so the right-click that opened us does not
    // immediately close the menu, and so a click on Edit is not swallowed.
    const id = window.setTimeout(() => {
      const onPtr = (e: Event) => {
        if (root.current?.contains(e.target as Node)) return;
        onClose();
      };
      window.addEventListener("pointerdown", onPtr, true);
      window.addEventListener("contextmenu", onPtr, true);
      window.addEventListener("keydown", onKey);
      (root.current as HTMLDivElement & { _off?: () => void })._off = () => {
        window.removeEventListener("pointerdown", onPtr, true);
        window.removeEventListener("contextmenu", onPtr, true);
        window.removeEventListener("keydown", onKey);
      };
    }, 0);
    return () => {
      window.clearTimeout(id);
      const el = root.current as (HTMLDivElement & { _off?: () => void }) | null;
      el?._off?.();
      window.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  const left = Math.min(x, window.innerWidth - 240);
  const top = Math.min(y, window.innerHeight - items.length * 34 - 16);

  return (
    <div ref={root} className="ctx-menu" style={{ left, top }} onPointerDown={(e) => e.stopPropagation()}>
      {items.map((item, idx) => (
        item.label === "—" ? (
          <div key={`sep-${idx}`} className="ctx-sep" />
        ) : (
          <button
            key={`${item.label}-${idx}`}
            type="button"
            className={`ctx-item ${item.danger ? "danger" : ""}`}
            disabled={item.disabled}
            onClick={() => { item.run?.(); onClose(); }}
          >
            {item.label}
          </button>
        )
      ))}
    </div>
  );
}
