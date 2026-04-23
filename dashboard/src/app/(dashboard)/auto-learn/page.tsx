"use client";

import { useState } from "react";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Badge } from "@/components/ui/badge";
import { Brain, TrendingUp, AlertCircle, Lightbulb } from "lucide-react";
import { fetcher as apiFetcher, type WANumber } from "@/lib/api";
import useSWR from "swr";

interface ReportData {
  funnel_summary?: Record<string, number>;
  winning_patterns?: Array<{ pattern: string; text?: string; score?: number; uses: number }>;
  low_performers?: Array<{ question?: string; suggestion: string; score?: number; uses: number }>;
  suggested_entries?: Array<{ question: string; frequency: number }>;
  feedback_stats?: { good: number; bad: number };
}

interface ImproveData {
  patterns_added?: number;
  suggestions_created?: number;
  errors?: string[];
}

export default function AutoLearnPage() {
  const [selectedSession, setSelectedSession] = useState<string>("");
  const [applyChanges, setApplyChanges] = useState(false);
  const [reportData, setReportData] = useState<ReportData | null>(null);
  const [improveData, setImproveData] = useState<ImproveData | null>(null);
  const [loading, setLoading] = useState(false);

  const { data: waData } = useSWR<{ numbers: WANumber[] }>("/api/v1/agents/wa/sessions", apiFetcher);
  const csSessions = (waData?.numbers || []).filter((s) => s.mode === "cs");

  const generateReport = async () => {
    if (!selectedSession) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/legacy/auto-learn/report?session=${selectedSession}`);
      const json = await res.json();
      setReportData(json.data || json);
    } catch (error) {
      console.error("Report generation failed:", error);
    } finally {
      setLoading(false);
    }
  };

  const runImprovement = async () => {
    if (!selectedSession) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/v1/legacy/auto-learn/improve`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session: selectedSession, apply: applyChanges }),
      });
      const json = await res.json();
      setImproveData(json.data || json);
    } catch (error) {
      console.error("Auto-improvement failed:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold flex items-center gap-2">
          <Brain className="h-8 w-8" />
          Auto-Learn & Self-Improvement
        </h1>
        <p className="text-muted-foreground mt-2">
          Analyze conversation outcomes to identify winning patterns and improve responses
        </p>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Configuration</CardTitle>
          <CardDescription>Select a WA session to analyze</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <label className="text-sm font-medium mb-2 block">WA Session</label>
            <Select value={selectedSession} onValueChange={(v) => v && setSelectedSession(v)}>
              <SelectTrigger>
                <SelectValue placeholder="Select a CS session" />
              </SelectTrigger>
              <SelectContent>
                {csSessions.map((s) => (
                  <SelectItem key={s.id} value={s.session_name}>
                    {s.label || s.session_name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center space-x-2">
            <input 
              type="checkbox" 
              id="apply" 
              checked={applyChanges} 
              onChange={(e) => setApplyChanges(e.target.checked)}
              className="h-4 w-4 rounded border-gray-300"
            />
            <label htmlFor="apply" className="text-sm font-medium cursor-pointer">
              Apply changes (not dry-run)
            </label>
          </div>

          <div className="flex gap-3">
            <Button onClick={generateReport} disabled={!selectedSession || loading} className="flex-1">
              <TrendingUp className="mr-2 h-4 w-4" />
              Generate Learning Report
            </Button>
            <Button onClick={runImprovement} disabled={!selectedSession || loading} variant="secondary" className="flex-1">
              <Lightbulb className="mr-2 h-4 w-4" />
              Run Auto-Improvement
            </Button>
          </div>
        </CardContent>
      </Card>

      {reportData && (
        <Card>
          <CardHeader>
            <CardTitle>Learning Report</CardTitle>
            <CardDescription>Analysis from {Object.values(reportData.funnel_summary || {}).reduce((a: number, b) => a + (b as number), 0)} conversations</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div>
              <h3 className="font-semibold mb-2">Funnel Summary</h3>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
                {Object.entries(reportData.funnel_summary || {}).map(([status, count]) => (
                  <div key={status} className="p-3 bg-muted rounded-lg">
                    <div className="text-sm text-muted-foreground">{status}</div>
                    <div className="text-2xl font-bold">{count as number}</div>
                  </div>
                ))}
                {((reportData.feedback_stats?.good ?? 0) > 0 || (reportData.feedback_stats?.bad ?? 0) > 0) && (
                  <>
                    <div className="p-3 bg-green-900/30 rounded-lg">
                      <div className="text-sm text-green-400">Good Feedback</div>
                      <div className="text-2xl font-bold text-green-300">{reportData.feedback_stats?.good ?? 0}</div>
                    </div>
                    <div className="p-3 bg-red-900/30 rounded-lg">
                      <div className="text-sm text-red-400">Bad Feedback</div>
                      <div className="text-2xl font-bold text-red-300">{reportData.feedback_stats?.bad || 0}</div>
                    </div>
                  </>
                )}
              </div>
            </div>

            {reportData.winning_patterns && reportData.winning_patterns.length > 0 && (
              <div>
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <TrendingUp className="h-4 w-4 text-green-600" />
                  Winning Patterns
                </h3>
                <div className="space-y-2">
                  {reportData.winning_patterns.slice(0, 5).map((p, i) => (
                    <div key={i} className="p-3 bg-green-50 border border-green-200 rounded-lg">
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <Badge variant="outline" className="mb-1">{p.pattern}</Badge>
                          <p className="text-sm text-muted-foreground">{p.text?.substring(0, 100)}...</p>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-semibold text-green-700">Score: {p.score?.toFixed(2)}</div>
                          <div className="text-xs text-muted-foreground">{p.uses} uses</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {reportData.low_performers && reportData.low_performers.length > 0 && (
              <div>
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <AlertCircle className="h-4 w-4 text-orange-600" />
                  Low Performers
                </h3>
                <div className="space-y-2">
                  {reportData.low_performers.slice(0, 5).map((p, i) => (
                    <div key={i} className="p-3 bg-orange-50 border border-orange-200 rounded-lg">
                      <div className="flex justify-between items-start">
                        <div className="flex-1">
                          <p className="text-sm font-medium">{p.question?.substring(0, 80)}...</p>
                          <p className="text-xs text-muted-foreground mt-1">{p.suggestion}</p>
                        </div>
                        <div className="text-right">
                          <div className="text-sm font-semibold text-orange-700">Score: {p.score?.toFixed(2)}</div>
                          <div className="text-xs text-muted-foreground">{p.uses} uses</div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {reportData.suggested_entries && reportData.suggested_entries.length > 0 && (
              <div>
                <h3 className="font-semibold mb-2 flex items-center gap-2">
                  <Lightbulb className="h-4 w-4 text-blue-600" />
                  Suggested New KB Entries
                </h3>
                <div className="space-y-2">
                  {reportData.suggested_entries.slice(0, 5).map((s, i) => (
                    <div key={i} className="p-3 bg-blue-50 border border-blue-200 rounded-lg">
                      <p className="text-sm font-medium">{s.question}</p>
                      <p className="text-xs text-muted-foreground mt-1">Asked {s.frequency} times</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {improveData && (
        <Card>
          <CardHeader>
            <CardTitle>Auto-Improvement Results</CardTitle>
            <CardDescription>{applyChanges ? "Changes applied" : "Dry-run preview"}</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-2">
              <div className="flex justify-between p-3 bg-muted rounded-lg">
                <span>Patterns Added</span>
                <Badge>{improveData.patterns_added || 0}</Badge>
              </div>
              <div className="flex justify-between p-3 bg-muted rounded-lg">
                <span>Suggestions Created</span>
                <Badge>{improveData.suggestions_created || 0}</Badge>
              </div>
              {improveData.errors && improveData.errors.length > 0 && (
                <div className="p-3 bg-red-50 border border-red-200 rounded-lg">
                  <p className="text-sm font-semibold text-red-700 mb-1">Errors:</p>
                  {improveData.errors.map((e, i) => (
                    <p key={i} className="text-xs text-red-600">{e}</p>
                  ))}
                </div>
              )}
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
