import { useCallback, useEffect, useState } from "react";
import type { ProcessInventoryResponse, ScanResult } from "./api";
import { client, parseApiError } from "./api";

/** Loads the process inventory and reloads it whenever a new scan lands. Shared by all process-control surfaces. */
export function useProcessInventory(scan: ScanResult | null) {
  const [inventory, setInventory] = useState<ProcessInventoryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setInventory(await client.getProcesses());
    } catch (e) {
      setError(parseApiError(e));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [scan]);

  const noScan = !loading && !!inventory?.message;

  return { inventory, loading, error, noScan, reload };
}
