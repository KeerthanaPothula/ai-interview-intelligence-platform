import { useEffect, useState } from 'react';

// True once `active` has stayed true for `delayMs`. Used to tell the user the
// backend is cold-starting (Render free plan: ~30–40 s after 15 min idle)
// instead of leaving a spinner that looks frozen.
export function useSlowFlag(active: boolean, delayMs = 5000): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!active) {
      // eslint-disable-next-line react-hooks/set-state-in-effect -- reset when the wait ends
      setSlow(false);
      return;
    }
    const id = setTimeout(() => setSlow(true), delayMs);
    return () => clearTimeout(id);
  }, [active, delayMs]);
  return slow;
}
