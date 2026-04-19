"use client";

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

export default function FunnelPage() {
  const { data: funnel, isLoading: fLoad } = useSWR<FunnelData>("/api/v1/agents/funnel", fetcher, { refreshInterval: 5000 });
  const { data: leadsData, isLoading: lLoad } = useSWR<{ leads: Lead[] }>("/api/v1/agents/leads", fetcher, { refreshInterval: 10000 });
  const leads = leadsData?.leads ?? [];

  if (fLoad && lLoad) {
    return <div className="p-6 flex items-center justify-center h-[50vh]"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">Funnel</h1>
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
      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader><CardTitle>All Leads ({leads.length})</CardTitle></CardHeader>
        <CardContent>
          {leads.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead>Contact</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Vertical</TableHead>
                  <TableHead>Updated</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {leads.slice(0, 50).map((lead) => (
                  <TableRow key={lead.id}>
                    <TableCell className="font-medium">{String(lead.company_name || '—')}</TableCell>
                    <TableCell>{lead.contact_name || "—"}</TableCell>
                    <TableCell><Badge className={`${STAGE_COLORS[lead.status] || "bg-neutral-600"} text-white`}>{lead.status}</Badge></TableCell>
                    <TableCell>{lead.vertical || "—"}</TableCell>
                    <TableCell className="text-neutral-500 text-xs">{lead.updated_at?.slice(0, 10) || "—"}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : <p className="text-neutral-500 text-center py-8">No leads yet. Run the pipeline to scrape leads.</p>}
        </CardContent>
      </Card>
    </div>
  );
}
