"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, postJSON, type ServiceStatus } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Play, Square, RefreshCw, FileText, Loader2 } from "lucide-react";

interface LogSource {
  value: string;
  label: string;
  source: string;
}

export default function ServicesPage() {
  const { data: svcData, mutate: mutateSvc, isLoading } = useSWR<{ services: ServiceStatus[] }>("/api/v1/admin/status", fetcher, { refreshInterval: 3000, dedupingInterval: 2000 });
  const { data: logSources } = useSWR<{ sources: LogSource[] }>("/api/v1/admin/logs", fetcher, { refreshInterval: 30000 });
  const [selectedLog, setSelectedLog] = useState<string>("");
  const [mode, setMode] = useState<"normal" | "dry_run" | "run_once">("dry_run");
  const [acting, setActing] = useState<string | null>(null);

  const availableSources = logSources?.sources ?? [];
  const effectiveSelected = availableSources.find(s => s.value === selectedLog) ? selectedLog : (availableSources[0]?.value ?? "");

  const { data: logData } = useSWR<{ lines: string[] }>(
    effectiveSelected ? `/api/v1/admin/logs/${effectiveSelected}?lines=80` : null, fetcher, { refreshInterval: 5000 }
  );

  if (isLoading) {
    return <div className="p-6 flex items-center justify-center h-[50vh]"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  const services = svcData?.services ?? [];
  const autonomous = services.find((s) => s.key === "autonomous");

  async function startLoop() {
    setActing("autonomous-start");
    await postJSON("/api/v1/agents/autonomous/start", { dry_run: mode === "dry_run", run_once: mode === "run_once" });
    setTimeout(() => { mutateSvc(); setActing(null); }, 1500);
  }

  async function stopLoop() {
    setActing("autonomous-stop");
    await postJSON("/api/v1/agents/autonomous/stop", {});
    setTimeout(() => { mutateSvc(); setActing(null); }, 1500);
  }

  async function restartService(key: string) {
    setActing(`${key}-restart`);
    await postJSON(`/api/v1/agents/services/${key}/restart`, {});
    setTimeout(() => { mutateSvc(); setActing(null); }, 2000);
  }

  async function stopService(key: string) {
    setActing(`${key}-stop`);
    await postJSON(`/api/v1/agents/services/${key}/stop`, {});
    setTimeout(() => { mutateSvc(); setActing(null); }, 1500);
  }

  async function startService(key: string) {
    setActing(`${key}-start`);
    await postJSON(`/api/v1/agents/services/${key}/start`, {});
    setTimeout(() => { mutateSvc(); setActing(null); }, 2000);
  }

  const serviceActions: Record<string, { canStart?: boolean; canStop?: boolean; canRestart?: boolean }> = {
    webhook: { canStart: true, canStop: true, canRestart: true },
    autonomous: { canStart: true, canStop: true },
    dashboard: { canStart: true, canStop: true, canRestart: true },
    "gmaps-scraper": { canRestart: true },
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Services</h1>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {services.map((s) => {
          const actions = serviceActions[s.key] || {};
          return (
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
                  <div className="flex items-center gap-2">
                    <Badge variant={s.running ? "default" : "secondary"} className={s.running ? "bg-green-600" : "bg-neutral-700"}>
                      {s.running ? "Running" : "Stopped"}
                    </Badge>
                    {actions.canRestart && (
                      <Button size="sm" variant="outline" className="h-7 text-xs border-neutral-700" onClick={() => restartService(s.key)} disabled={acting === `${s.key}-restart`}>
                        {acting === `${s.key}-restart` ? <Loader2 className="h-3 w-3 animate-spin" /> : <RefreshCw className="h-3 w-3" />}
                      </Button>
                    )}
                    {actions.canStart && !s.running && (
                      <Button size="sm" variant="outline" className="h-7 text-xs border-green-700 text-green-400 hover:bg-green-950" onClick={() => startService(s.key)} disabled={acting === `${s.key}-start`}>
                        {acting === `${s.key}-start` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                      </Button>
                    )}
                    {actions.canStop && s.running && (
                      <Button size="sm" variant="destructive" className="h-7 text-xs" onClick={() => stopService(s.key)} disabled={acting === `${s.key}-stop`}>
                        {acting === `${s.key}-stop` ? <Loader2 className="h-3 w-3 animate-spin" /> : <Square className="h-3 w-3" />}
                      </Button>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          );
        })}
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
            <Select value={effectiveSelected} onValueChange={(v) => v && setSelectedLog(v)}>
              <SelectTrigger className="w-48 bg-neutral-800 border-neutral-700">
                <SelectValue placeholder="Select log source..." />
              </SelectTrigger>
              <SelectContent>
                {availableSources.map((lf) => (
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
