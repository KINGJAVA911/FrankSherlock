import { useEffect } from "react";

export function useAppInit(onInit: () => Promise<void>) {
  useEffect(() => {
    let mounted = true;
    (async () => {
      if (!mounted) return;
      await onInit();
    })();
    return () => { mounted = false; };
  }, []);
}
