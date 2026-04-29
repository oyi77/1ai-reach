"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Shield, AlertTriangle, CheckCircle2, AlertCircle, Mail, Trash2, Download, Eye } from "lucide-react";

interface ComplianceOverview {
  total_consents: number;
  active_consents: number;
  withdrawn_consents: number;
  dnc_count: number;
  suppression_count: number;
  bounce_stats: {
    hard_bounces: number;
    soft_bounces: number;
    spam_complaints: number;
  };
  list_health_score: number;
  list_health_status: string;
}

function StatBox({ label, value, icon: Icon, color = "text-neutral-400" }: any) {
  return (
    <div className="bg-neutral-800 rounded-lg p-3">
      <div className="flex items-center gap-2 mb-1">
        <Icon className={`h-4 w-4 ${color}`} />
        <span className="text-xs text-neutral-500">{label}</span>
      </div>
      <p className="text-xl font-bold">{value}</p>
    </div>
  );
}

export function ComplianceDashboard() {
  const { data, isLoading, error, mutate } = useSWR<ComplianceOverview>(
    "/api/v1/compliance/overview",
    fetcher,
    { refreshInterval: 60000 }
  );

  if (isLoading) {
    return (
      <Card className="bg-neutral-900 border-neutral-800">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-neutral-500">
            <Shield className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading compliance...</span>
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
            <span className="text-sm">Compliance data unavailable</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const { total_consents, active_consents, dnc_count, suppression_count, bounce_stats, list_health_score, list_health_status } = data;

  const healthColor = list_health_status === "excellent" ? "text-green-400" : list_health_status === "good" ? "text-emerald-400" : list_health_status === "fair" ? "text-amber-400" : "text-red-400";

  return (
    <Card className="bg-neutral-900 border-neutral-800">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Compliance & List Health
          </span>
          <Badge variant={list_health_status === "excellent" || list_health_status === "good" ? "default" : "destructive"} className="text-xs">
            <span className={healthColor}>{list_health_status.toUpperCase()}</span>
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Health Score */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-neutral-500">List Health Score</p>
            <p className={`text-2xl font-bold ${healthColor}`}>{list_health_score}/100</p>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" size="sm" className="text-xs bg-neutral-800 border-neutral-700" onClick={() => mutate()}>
              Refresh
            </Button>
          </div>
        </div>

        {/* Stats Grid */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
          <StatBox label="Active Consents" value={active_consents} icon={CheckCircle2} color="text-green-400" />
          <StatBox label="Total Consents" value={total_consents} icon={Shield} color="text-blue-400" />
          <StatBox label="Do Not Contact" value={dnc_count} icon={AlertTriangle} color="text-amber-400" />
          <StatBox label="Suppressed" value={suppression_count} icon={AlertCircle} color="text-red-400" />
        </div>

        {/* Bounce Stats */}
        <div className="p-3 bg-neutral-800 rounded-lg">
          <p className="text-xs text-neutral-500 mb-2">Bounce Statistics</p>
          <div className="grid grid-cols-3 gap-2">
            <div className="text-center">
              <p className="text-lg font-bold text-red-400">{bounce_stats.hard_bounces}</p>
              <p className="text-xs text-neutral-500">Hard</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-amber-400">{bounce_stats.soft_bounces}</p>
              <p className="text-xs text-neutral-500">Soft</p>
            </div>
            <div className="text-center">
              <p className="text-lg font-bold text-orange-400">{bounce_stats.spam_complaints}</p>
              <p className="text-xs text-neutral-500">Spam</p>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="flex gap-2 pt-2 border-t border-neutral-800">
          <Button variant="outline" size="sm" className="flex-1 text-xs bg-neutral-800 border-neutral-700">
            <Download className="h-3 w-3 mr-1" />
            Export Data
          </Button>
          <Button variant="outline" size="sm" className="flex-1 text-xs bg-neutral-800 border-neutral-700">
            <Eye className="h-3 w-3 mr-1" />
            View Audit Log
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
