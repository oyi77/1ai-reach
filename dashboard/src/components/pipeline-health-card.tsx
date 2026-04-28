"use client";

import useSWR from "swr";
import { fetcher, fetchPipelineStats, fetchPipelineHealth, type PipelineStats, type PipelineHealth } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Activity, TrendingUp, Users, Zap, AlertCircle, CheckCircle2, Clock } from "lucide-react";

function StatMini({ label, value, icon: Icon, trend }: { label: string; value: number | string; icon?: React.ElementType; trend?: string }) {
  return (
    <div className="flex items-center gap-3">
      {Icon && <Icon className="h-4 w-4 text-neutral-500" />}
      <div>
        <p className="text-xs text-neutral-500">{label}</p>
        <p className="text-lg font-bold">{value}</p>
        {trend && <p className="text-xs text-green-400">{trend}</p>}
      </div>
    </div>
  );
}

function HealthIndicator({ status }: { status: "healthy" | "unhealthy" | "warning" }) {
  const colors = {
    healthy: "bg-green-500",
    unhealthy: "bg-red-500",
    warning: "bg-amber-500",
  };
  return <div className={`h-2 w-2 rounded-full ${colors[status]} animate-pulse`} />;
}

export function PipelineHealthCard() {
  const { data: health, error: healthError } = useSWR<PipelineHealth>("/api/v1/pipeline/health", fetcher, {
    refreshInterval: 60000,
  });

  const { data: stats, error: statsError } = useSWR<PipelineStats>("/api/v1/pipeline/stats", fetcher, {
    refreshInterval: 30000,
  });

  const isLoading = !health && !stats;

  if (isLoading) {
    return (
      <Card className="bg-neutral-900 border-neutral-800">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-neutral-500">
            <Activity className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading pipeline health...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (healthError || statsError || !health) {
    return (
      <Card className="bg-red-500/10 border-red-500/40">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-red-400">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">Pipeline health check failed</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const isHealthy = health.status === "healthy";

  return (
    <Card className={`${isHealthy ? "bg-green-500/5 border-green-500/40" : "bg-red-500/5 border-red-500/40"}`}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Activity className="h-4 w-4" />
            Pipeline Health
          </span>
          <Badge variant={isHealthy ? "default" : "destructive"} className="text-xs">
            {isHealthy ? <CheckCircle2 className="h-3 w-3 mr-1" /> : <AlertCircle className="h-3 w-3 mr-1" />}
            {health.status.toUpperCase()}
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Summary Stats */}
        {stats && (
          <div className="grid grid-cols-4 gap-3">
            <StatMini label="Total Leads" value={stats.summary.total_leads} icon={Users} />
            <StatMini label="24h" value={stats.summary.leads_24h} trend={`+${stats.summary.leads_24h}`} />
            <StatMini label="7d" value={stats.summary.leads_7d} />
            <StatMini label="30d" value={stats.summary.leads_30d} />
          </div>
        )}

        {/* Health Checks */}
        <div className="space-y-1">
          {health.checks.slice(0, 3).map((check) => (
            <div key={check.check} className="flex items-center justify-between text-xs">
              <span className="text-neutral-400 truncate">{check.check.replace("directory:", "")}</span>
              <div className="flex items-center gap-1">
                <HealthIndicator status={check.status} />
                <span className={`text-xs ${check.status === "healthy" ? "text-green-400" : check.status === "warning" ? "text-amber-400" : "text-red-400"}`}>
                  {check.status}
                </span>
              </div>
            </div>
          ))}
        </div>

        {/* Activity */}
        <div className="flex items-center justify-between pt-2 border-t border-neutral-800">
          <div className="flex items-center gap-2 text-xs text-neutral-500">
            <Clock className="h-3 w-3" />
            <span>Last run: {health.last_run || "Never"}</span>
          </div>
          {health.errors_24h > 0 && (
            <Badge variant="destructive" className="text-xs">
              {health.errors_24h} errors (24h)
            </Badge>
          )}
        </div>

        {/* Funnel Rates */}
        {stats && (
          <div className="grid grid-cols-4 gap-2 pt-2 border-t border-neutral-800">
            <div className="text-center">
              <p className="text-xs text-neutral-500">Enrich</p>
              <p className="text-sm font-bold text-green-400">{stats.funnel.conversion_rates.enrichment_rate}%</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-neutral-500">Contact</p>
              <p className="text-sm font-bold text-blue-400">{stats.funnel.conversion_rates.contact_rate}%</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-neutral-500">Reply</p>
              <p className="text-sm font-bold text-orange-400">{stats.funnel.conversion_rates.reply_rate}%</p>
            </div>
            <div className="text-center">
              <p className="text-xs text-neutral-500">Meeting</p>
              <p className="text-sm font-bold text-purple-400">{stats.funnel.conversion_rates.meeting_rate}%</p>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
