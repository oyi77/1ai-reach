"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Zap, TrendingUp, Users, Building, Briefcase, AlertCircle, RefreshCw } from "lucide-react";

interface IntentSignal {
  lead_id: string;
  signal_type: string;
  description: string;
  source_url: string;
  detected_at: string;
  confidence: number;
  acted_on: boolean;
  company_name?: string;
}

interface IntentOverview {
  total_signals: number;
  unacted_signals: number;
  by_type: Record<string, number>;
  recent_signals: IntentSignal[];
}

const SIGNAL_ICONS: Record<string, any> = {
  funding: TrendingUp,
  hiring: Users,
  tech_change: Building,
  leadership: Briefcase,
  expansion: Zap,
};

const SIGNAL_COLORS: Record<string, string> = {
  funding: "bg-green-500/20 text-green-400 border-green-500/40",
  hiring: "bg-blue-500/20 text-blue-400 border-blue-500/40",
  tech_change: "bg-purple-500/20 text-purple-400 border-purple-500/40",
  leadership: "bg-amber-500/20 text-amber-400 border-amber-500/40",
  expansion: "bg-orange-500/20 text-orange-400 border-orange-500/40",
};

function SignalIcon({ type }: { type: string }) {
  const Icon = SIGNAL_ICONS[type] || AlertCircle;
  return <Icon className="h-4 w-4" />;
}

export function IntentSignalsPanel() {
  const { data, isLoading, error, mutate } = useSWR<{ data: IntentOverview }>(
    "/api/v1/intent/overview",
    fetcher,
    { refreshInterval: 300000 }
  );

  if (isLoading) {
    return (
      <Card className="bg-neutral-900 border-neutral-800">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-neutral-500">
            <Zap className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading intent signals...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card className="bg-neutral-900 border-neutral-800">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-neutral-500">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">Intent data unavailable</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const { total_signals, unacted_signals, by_type, recent_signals } = data.data;

  return (
    <Card className="bg-neutral-900 border-neutral-800">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Zap className="h-4 w-4 text-yellow-400" />
            Intent Signals
          </span>
          <div className="flex gap-2">
            {unacted_signals > 0 && (
              <Badge variant="destructive" className="text-xs">
                {unacted_signals} New
              </Badge>
            )}
            <Button variant="outline" size="sm" className="h-6 text-xs bg-neutral-800 border-neutral-700" onClick={() => mutate()}>
              <RefreshCw className="h-3 w-3 mr-1" />
              Refresh
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary Stats */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-neutral-800 rounded-lg p-3">
            <p className="text-xs text-neutral-500">Total Signals</p>
            <p className="text-lg font-bold">{total_signals}</p>
          </div>
          <div className="bg-neutral-800 rounded-lg p-3">
            <p className="text-xs text-neutral-500">Unacted</p>
            <p className="text-lg font-bold text-yellow-400">{unacted_signals}</p>
          </div>
        </div>

        {/* By Type */}
        <div>
          <p className="text-xs text-neutral-500 mb-2">Signals by Type</p>
          <div className="grid grid-cols-2 gap-2">
            {Object.entries(by_type).map(([type, count]) => (
              <div key={type} className={`rounded-lg p-2 border ${SIGNAL_COLORS[type] || "bg-neutral-800"}`}>
                <div className="flex items-center gap-2">
                  <SignalIcon type={type} />
                  <span className="text-xs font-medium capitalize">{type.replace("_", " ")}</span>
                </div>
                <p className="text-lg font-bold mt-1">{count}</p>
              </div>
            ))}
          </div>
        </div>

        {/* Recent Signals */}
        {recent_signals.length > 0 && (
          <div>
            <p className="text-xs text-neutral-500 mb-2">Recent Signals</p>
            <div className="space-y-2 max-h-48 overflow-y-auto">
              {recent_signals.slice(0, 5).map((signal, i) => (
                <div key={i} className="bg-neutral-800 rounded-lg p-2 text-xs">
                  <div className="flex items-center justify-between mb-1">
                    <Badge variant="outline" className={`text-xs ${SIGNAL_COLORS[signal.signal_type]}`}>
                      {signal.signal_type}
                    </Badge>
                    <span className="text-neutral-500">{new Date(signal.detected_at).toLocaleDateString()}</span>
                  </div>
                  <p className="font-medium truncate">{signal.description}</p>
                  <p className="text-neutral-500 truncate">{signal.company_name || signal.lead_id}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {recent_signals.length === 0 && (
          <div className="text-center py-4 text-neutral-500 text-sm">
            <Zap className="h-8 w-8 mx-auto mb-2 opacity-50" />
            <p>No intent signals detected yet</p>
            <p className="text-xs">Signals appear when leads show buying intent</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
