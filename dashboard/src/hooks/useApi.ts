import useSWR from "swr";
import { fetcher, type FunnelData, type WANumber, type ServiceStatus, type PipelineScript } from "@/lib/api";

export function useFunnel(refreshInterval = 5000) {
  return useSWR<FunnelData>("/api/v1/agents/funnel", fetcher, { refreshInterval });
}

export function useWANumbers() {
  return useSWR<{ numbers: WANumber[]; count: number }>("/api/wa-numbers", fetcher);
}

export function useServices(refreshInterval = 3000) {
  return useSWR<{ services: ServiceStatus[] }>("/api/v1/admin/status", fetcher, { refreshInterval });
}

export function usePipelineScripts() {
  return useSWR<{ scripts: PipelineScript[] }>("/api/pipeline/scripts", fetcher);
}

export function useLogs(name: string, lines = 50, refreshInterval = 5000) {
  return useSWR<{ lines: string[]; count: number }>(
    name ? `/api/logs/${name}?lines=${lines}` : null,
    fetcher,
    { refreshInterval }
  );
}
