import { useEffect, useState } from "react";

export type PopoverPos = { top: number; left: number; width: number };

export function useAnchoredPopover(
  open: boolean,
  anchor: HTMLElement | null,
  width: number,
): PopoverPos | null {
  const [pos, setPos] = useState<PopoverPos | null>(null);

  useEffect(() => {
    if (!open || !anchor) {
      setPos(null);
      return undefined;
    }
    const place = () => {
      const rect = anchor.getBoundingClientRect();
      const gap = 6;
      let left = rect.left;
      if (left + width > window.innerWidth - 8) left = Math.max(8, window.innerWidth - width - 8);
      let top = rect.bottom + gap;
      const estimatedHeight = 280;
      if (top + estimatedHeight > window.innerHeight && rect.top > estimatedHeight) {
        top = rect.top - estimatedHeight - gap;
      }
      setPos({ top, left, width });
    };
    place();
    window.addEventListener("resize", place);
    window.addEventListener("scroll", place, true);
    return () => {
      window.removeEventListener("resize", place);
      window.removeEventListener("scroll", place, true);
    };
  }, [open, anchor, width]);

  return pos;
}
