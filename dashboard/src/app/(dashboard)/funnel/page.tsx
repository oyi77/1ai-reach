"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, type FunnelData, type Lead } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2 } from "lucide-react";

const STAGES = ["new","enriched","draft_ready","needs_revision","reviewed","contacted","followed_up","replied","meeting_booked","won","lost","cold"];
const STAGE_COLORS: Record<string, string> = {
  new: "bg-blue-600", enriched: "bg-purple-600", draft_ready: "bg-amber-600", needs_revision: "bg-red-600",
  reviewed: "bg-emerald-600", contacted: "bg-cyan-600", followed_up: "bg-pink-600", replied: "bg-orange-500",
  meeting_booked: "bg-green-600", won: "bg-green-700", lost: "bg-red-700", cold: "bg-neutral-600",
};
const TIER_COLORS: Record<string, string> = {
  hot: "bg-red-500", warm: "bg-amber-500", cold: "bg-blue-500", skip: "bg-neutral-500",
};

interface ServiceItem { service: string; leads_matched: number; }
interface ScoringStats { distribution: Record<string, number>; avg_score: number; total: number; scored: number; }

export default function FunnelPage() {
  const { data: funnel, isLoading: fLoad } = useSWR<FunnelData>("/api/v1/agents/funnel", fetcher, { refreshInterval: 5000 });
  const { data: leadsData, isLoading: lLoad } = useSWR<{ count: number; items: Lead[] }>("/api/v1/agents/leads", fetcher, { refreshInterval: 10000 });
  const { data: servicesData } = useSWR<{ data: { services: ServiceItem[] } }>("/api/v1/agents/services/list", fetcher, { refreshInterval: 30000 });
  const { data: scoringData } = useSWR<{ data: ScoringStats }>("/api/v1/agents/scoring/stats", fetcher, { refreshInterval: 30000 });

  const leads = leadsData?.items ?? [];
  const services = servicesData?.data?.services ?? [];
  const tierDist = scoringData?.data?.distribution ?? {};
  const [tierFilter, setTierFilter] = useState<string>("all");
  const filteredLeads = tierFilter === "all" ? leads : leads.filter((l: any) => ((l as any).tier || "").toLowerCase() === tierFilter);

  if (fLoad && lLoad) {
    return <div className="p-6 flex items-center justify-center h-[50vh]"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  const parseServices = (val: any): string[] => {
    if (!val) return [];
    if (typeof val === "string") { try { const parsed = JSON.parse(val); return parsed.map((s: any) => typeof s === "object" && s.service ? s.service : String(s)); } catch { return []; } }
    if (Array.isArray(val)) return val.map((s: any) => typeof s === "object" && s.service ? s.service : String(s));
    return [];
  };

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Funnel</h1>

      {/* Stage Pills */}
      <div className="flex gap-2 flex-wrap">
        {STAGES.map((stage) => {
          const count = funnel?.counts[stage] ?? 0;
          return (
            <div key={stage} className="flex items-center gap-2 bg-neutral-900 rounded-lg px-3 py-2 border border-neutral-800">
              <div className={`h-3 w-3 rounded-sm ${STAGE_COLORS[stage] || "bg-neutral-600"}`} />
              <span className="text-sm capitalize">{stage.replace(/_/g, " ")}</span>
              <Badge variant="secondary" className="bg-neutral-800">{count}</Badge>
            </div>
          );
        })}
      </div>

      {/* Service Distribution */}
      {services.length > 0 && (
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader><CardTitle>Service Distribution</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {services.map((s) => {
              const maxCount = Math.max(...services.map(x => x.leads_matched), 1);
              return (
                <div key={s.service} className="flex items-center gap-3">
                  <span className="text-xs w-40 truncate">{s.service.replace(/_/g, " ")}</span>
                  <div className="flex-1 bg-neutral-800 rounded-full h-4 overflow-hidden">
                    <div className="bg-orange-500 h-full rounded-full" style={{ width: `${(s.leads_matched / maxCount) * 100}%` }} />
                  </div>
                  <Badge variant="secondary" className="bg-neutral-800">{s.leads_matched}</Badge>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* Tier Filter */}
      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader><CardTitle>Tier Distribution</CardTitle></CardHeader>
        <CardContent>
          <div className="flex gap-2 flex-wrap">
            {["all", "hot", "warm", "cold", "skip"].map((t) => (
              <button
                key={t}
                onClick={() => setTierFilter(t)}
                className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                  tierFilter === t
                    ? t === "all" ? "bg-orange-500 text-white" : `${TIER_COLORS[t] || "bg-neutral-600"} text-white`
                    : "bg-neutral-800 text-neutral-400 hover:bg-neutral-700"
                }`}
              >
                {t === "all" ? `All (${leads.length})` : `${t.charAt(0).toUpperCase() + t.slice(1)} (${tierDist[t] || 0})`}
              </button>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Leads Table */}
      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader><CardTitle>All Leads ({filteredLeads.length})</CardTitle></CardHeader>
        <CardContent>
          {filteredLeads.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Tier</TableHead>
                  <TableHead>Services</TableHead>
                  <TableHead>Vertical</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredLeads.slice(0, 50).map((lead) => {
                  const l = lead as any;
                  const tier = l.tier || "";
                  const leadServices = parseServices(l.matched_services);
                  return (
                    <TableRow key={l.id}>
                      <TableCell className="font-medium">{String(l.displayName || l.company_name || "—")}</TableCell>
                      <TableCell className="text-xs">{l.email || l.contact_name || "—"}</TableCell>
                      <TableCell><Badge className={`${STAGE_COLORS[l.status] || "bg-neutral-600"} text-white`}>{l.status}</Badge></TableCell>
                      <TableCell>
                        {tier ? <Badge className={`${TIER_COLORS[tier.toLowerCase()] || "bg-neutral-600"} text-white text-xs`}>{tier}</Badge> : "—"}
                      </TableCell>
                      <TableCell>
                        {leadServices.length > 0 ? (
                          <div className="flex gap-1 flex-wrap">
                            {leadServices.map((s) => (
                              <Badge key={s} variant="outline" className="text-xs border-orange-500/50 text-orange-400">
                                {s.replace(/_/g, " ")}
                              </Badge>
                            ))}
                          </div>
                        ) : "—"}
                      </TableCell>
                      <TableCell>{l.vertical || "—"}</TableCell>
                      <TableCell className="text-neutral-500 text-xs">{l.updated_at?.slice(0, 10) || "—"}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          ) : <p className="text-neutral-500 text-center py-8">No leads match this filter.</p>}
        </CardContent>
      </Card>
    </div>
  );
}
