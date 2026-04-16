"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, postJSON, type PipelineScript } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { Play, Loader2 } from "lucide-react";

export default function PipelineControlPage() {
  const { data: scriptsData, isLoading } = useSWR<{ scripts: PipelineScript[] }>("/api/pipeline/scripts", fetcher);
  const [query, setQuery] = useState("Digital Agency in Jakarta");
  const [running, setRunning] = useState<string | null>(null);
  const [results, setResults] = useState<Record<string, string>>({});

  if (isLoading) {
    return <div className="p-6 flex items-center justify-center h-[50vh]"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  const scripts = scriptsData?.scripts ?? [];

  async function runScript(script: string) {
    setRunning(script);
    setResults((prev) => ({ ...prev, [script]: "Running..." }));
    try {
      const res = await postJSON<{ ok: boolean; pid?: number; error?: string }>("/api/pipeline/run", { script, query });
      setResults((prev) => ({ ...prev, [script]: res.ok ? `Started (PID ${res.pid})` : `Error: ${res.error}` }));
    } catch (e) {
      setResults((prev) => ({ ...prev, [script]: `Failed: ${e}` }));
    }
    setRunning(null);
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Run Pipeline</h1>

      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader><CardTitle>Search Query</CardTitle></CardHeader>
        <CardContent>
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. Coffee Shop in Jakarta"
            className="bg-neutral-800 border-neutral-700"
          />
        </CardContent>
      </Card>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
        {scripts.map((s) => (
          <Card key={s.key} className="bg-neutral-900 border-neutral-800">
            <CardContent className="pt-6">
              <div className="flex items-center justify-between mb-3">
                <h3 className="font-semibold capitalize">{s.key}</h3>
                <Badge variant="secondary" className="bg-neutral-800 text-xs">{s.script}</Badge>
              </div>
              {results[s.key] && (
                <p className={`text-xs mb-2 ${results[s.key].startsWith("Error") || results[s.key].startsWith("Failed") ? "text-red-400" : "text-green-400"}`}>
                  {results[s.key]}
                </p>
              )}
              <Button
                onClick={() => runScript(s.script)}
                disabled={running !== null}
                className="w-full bg-orange-600 hover:bg-orange-700"
              >
                {running === s.script ? <Loader2 className="h-4 w-4 mr-2 animate-spin" /> : <Play className="h-4 w-4 mr-2" />}
                Run
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
