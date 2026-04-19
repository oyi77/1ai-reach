"use client";

import useSWR from "swr";
import { fetcher, type ServiceStatus, type FunnelData } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from "recharts";
import { Activity, Server, Zap, Users, Loader2 } from "lucide-react";

const STAGE_COLORS: Record<string, string> = {
  new: "#3b82f6", enriched: "#8b5cf6", draft_ready: "#f59e0b", needs_revision: "#ef4444",
  reviewed: "#10b981", contacted: "#06b6d4", followed_up: "#ec4899", replied: "#f97316",
  meeting_booked: "#22c55e", won: "#16a34a", lost: "#dc2626", cold: "#6b7280",
};

export default function DashboardPage() {
  const { data: funnel, isLoading: funnelLoading } = useSWR<FunnelData>("/api/v1/agents/funnel", fetcher, { refreshInterval: 5000 });
  const { data: svcData, isLoading: svcLoading } = useSWR<{ services: ServiceStatus[] }>("/api/v1/admin/status", fetcher, { refreshInterval: 3000 });
  const apiOnline = funnel !== undefined;

  if (funnelLoading && svcLoading) {
    return <div className="flex items-center justify-center h-[50vh]"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  const services = svcData?.services ?? [];
  const running = services.filter((s) => s.running).length;
  const chartData = funnel
    ? Object.entries(funnel.counts).map(([name, value]) => ({ name, value, color: STAGE_COLORS[name] || "#6b7280" }))
    : [];

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Dashboard</h1>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-neutral-400">Total Leads</CardTitle>
            <Users className="h-4 w-4 text-neutral-500" />
          </CardHeader>
          <CardContent><div className="text-2xl font-bold">{funnel?.total ?? 0}</div></CardContent>
        </Card>
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-neutral-400">Services Up</CardTitle>
            <Server className="h-4 w-4 text-neutral-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">{running}<span className="text-sm text-neutral-500">/{services.length}</span></div>
          </CardContent>
        </Card>
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-neutral-400">Autonomous Loop</CardTitle>
            <Zap className="h-4 w-4 text-neutral-500" />
          </CardHeader>
          <CardContent>
            <Badge variant={services.find((s) => s.key === "autonomous")?.running ? "default" : "secondary"}
              className={services.find((s) => s.key === "autonomous")?.running ? "bg-green-600" : "bg-neutral-700"}>
              {services.find((s) => s.key === "autonomous")?.running ? "ACTIVE" : "STOPPED"}
            </Badge>
          </CardContent>
        </Card>
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2">
            <CardTitle className="text-sm font-medium text-neutral-400">API Status</CardTitle>
            <Activity className="h-4 w-4 text-neutral-500" />
          </CardHeader>
          <CardContent>
            <Badge className={apiOnline === false ? "bg-red-600" : "bg-green-600"}>
              {apiOnline === false ? "OFFLINE" : apiOnline ? "ONLINE" : "CHECKING..."}
            </Badge>
          </CardContent>
        </Card>
      </div>
      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader><CardTitle>Funnel Overview</CardTitle></CardHeader>
        <CardContent>
          {chartData.length > 0 ? (
            <ResponsiveContainer width="100%" height={300}>
              <BarChart data={chartData}>
                <CartesianGrid strokeDasharray="3 3" stroke="#333" />
                <XAxis dataKey="name" stroke="#666" tick={{ fontSize: 12 }} />
                <YAxis stroke="#666" tick={{ fontSize: 12 }} />
                <Tooltip contentStyle={{ backgroundColor: "#171717", border: "1px solid #333", borderRadius: 6 }} labelStyle={{ color: "#999" }} />
                <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                  {chartData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          ) : <p className="text-neutral-500 text-center py-12">No leads in funnel yet</p>}
        </CardContent>
      </Card>
      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader><CardTitle>Service Status</CardTitle></CardHeader>
        <CardContent>
          <div className="space-y-2">
            {services.map((s) => (
              <div key={s.key} className="flex items-center justify-between py-2 border-b border-neutral-800 last:border-0">
                <div className="flex items-center gap-3">
                  <div className={`h-2.5 w-2.5 rounded-full ${s.running ? "bg-green-500" : "bg-neutral-600"}`} />
                  <span className="font-medium">{s.label}</span>
                </div>
                <div className="flex items-center gap-3 text-sm text-neutral-500">
                  {s.pid && <span>PID {s.pid}</span>}
                  {s.port && <span>:{s.port}</span>}
                  <Badge variant={s.running ? "default" : "secondary"} className={s.running ? "bg-green-600/20 text-green-400" : "bg-neutral-800 text-neutral-500"}>
                    {s.running ? "Running" : "Stopped"}
                  </Badge>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
