"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, postJSON, type ServiceStatus } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Play, Square, RefreshCw, FileText } from "lucide-react";

const LOG_FILES = [
  { value: "webhook", label: "Webhook Server" },
  { value: "autonomous", label: "Autonomous Loop" },
  { value: "webhook_server", label: "Webhook (legacy)" },
  { value: "streamlit", label: "Streamlit" },
  { value: "pipeline_scraper.py", label: "Scraper" },
  { value: "pipeline_enricher.py", label: "Enricher" },
  { value: "pipeline_generator.py", label: "Generator" },
];

export default function ServicesPage() {
  const { data: svcData, mutate: mutateSvc } = useSWR<{ services: ServiceStatus[] }>("/api/services", fetcher, { refreshInterval: 3000 });
  const [selectedLog, setSelectedLog] = useState("webhook");
  const [mode, setMode] = useState<"normal" | "dry_run" | "run_once">("dry_run");

  const { data: logData } = useSWR<{ lines: string[] }>(
    selectedLog ? `/api/logs/${selectedLog}?lines=80` : null, fetcher, { refreshInterval: 5000 }
  );

  const services = svcData?.services ?? [];
  const autonomous = services.find((s) => s.key === "autonomous");

  async function startLoop() {
    await postJSON("/api/services/autonomous/start", { dry_run: mode === "dry_run", run_once: mode === "run_once" });
    setTimeout(() => mutateSvc(), 1000);
  }

  async function stopLoop() {
    await postJSON("/api/services/autonomous/stop", {});
    setTimeout(() => mutateSvc(), 1000);
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Services</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {services.map((s) => (
          <Card key={s.key} className="bg-neutral-900 border-neutral-800">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`h-3 w-3 rounded-full ${s.running ? "bg-green-500 animate-pulse" : "bg-neutral-600"}`} />
                  <div>
                    <h3 className="font-semibold">{s.label}</h3>
                    <p className="text-xs text-neutral-500">
                      {s.pid ? `PID ${s.pid}` : "Not running"}{s.port ? ` — port ${s.port}` : ""}
                    </p>
                  </div>
                </div>
                <Badge variant={s.running ? "default" : "secondary"} className={s.running ? "bg-green-600" : "bg-neutral-700"}>
                  {s.running ? "Running" : "Stopped"}
                </Badge>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader>
          <CardTitle>Autonomous Loop Control</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="flex items-center gap-4">
            <Select value={mode} onValueChange={(v) => v && setMode(v as typeof mode)}>
              <SelectTrigger className="w-40 bg-neutral-800 border-neutral-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="normal">Normal</SelectItem>
                <SelectItem value="dry_run">Dry Run</SelectItem>
                <SelectItem value="run_once">Run Once</SelectItem>
              </SelectContent>
            </Select>
            {autonomous?.running ? (
              <Button onClick={stopLoop} variant="destructive"><Square className="h-4 w-4 mr-2" />Stop Loop</Button>
            ) : (
              <Button onClick={startLoop} className="bg-orange-600 hover:bg-orange-700"><Play className="h-4 w-4 mr-2" />Start Loop</Button>
            )}
            <Button variant="outline" onClick={() => mutateSvc()} className="border-neutral-700"><RefreshCw className="h-4 w-4 mr-2" />Refresh</Button>
          </div>
          {autonomous?.running && (
            <p className="mt-3 text-sm text-green-400">Loop is active in {mode === "dry_run" ? "dry-run" : mode === "run_once" ? "single-run" : "normal"} mode.</p>
          )}
        </CardContent>
      </Card>

      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle className="flex items-center gap-2"><FileText className="h-4 w-4" />Logs</CardTitle>
            <Select value={selectedLog} onValueChange={(v) => v && setSelectedLog(v)}>
              <SelectTrigger className="w-48 bg-neutral-800 border-neutral-700">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {LOG_FILES.map((lf) => (
                  <SelectItem key={lf.value} value={lf.value}>{lf.label}</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          <ScrollArea className="h-96 bg-neutral-950 rounded-md p-3">
            <pre className="text-xs font-mono text-neutral-300 whitespace-pre-wrap">
              {logData?.lines?.join("\n") || "(no logs)"}
            </pre>
          </ScrollArea>
        </CardContent>
      </Card>
    </div>
  );
}
