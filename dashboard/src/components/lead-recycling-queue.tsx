"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Recycle, Clock, Mail, MessageCircle, CheckCircle2, AlertCircle } from "lucide-react";

interface RecycleCandidate {
  lead_id: string;
  company_name: string;
  email: string;
  phone: string;
  days_since_contact: number;
  status: string;
  priority: string;
  last_contacted: string;
}

interface RecyclingOverview {
  total_cold_leads: number;
  by_interval: Record<number, number>;
  candidates: RecycleCandidate[];
}

const PRIORITY_COLORS: Record<string, string> = {
  high: "bg-red-500/20 text-red-400 border-red-500/40",
  medium: "bg-amber-500/20 text-amber-400 border-amber-500/40",
  low: "bg-blue-500/20 text-blue-400 border-blue-500/40",
};

export function LeadRecyclingQueue() {
  const { data, isLoading, error, mutate } = useSWR<RecyclingOverview>(
    "/api/v1/outreach/recycling/overview",
    fetcher,
    { refreshInterval: 300000 }
  );

  if (isLoading) {
    return (
      <Card className="bg-neutral-900 border-neutral-800">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-neutral-500">
            <Recycle className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading recycling queue...</span>
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
            <span className="text-sm">Recycling data unavailable</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const { total_cold_leads, by_interval, candidates } = data;

  return (
    <Card className="bg-neutral-900 border-neutral-800">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Recycle className="h-4 w-4 text-green-400" />
            Lead Recycling Queue
          </span>
          <Button variant="outline" size="sm" className="h-6 text-xs bg-neutral-800 border-neutral-700" onClick={() => mutate()}>
            Refresh
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary */}
        <div className="grid grid-cols-4 gap-2">
          <div className="bg-neutral-800 rounded-lg p-2 text-center">
            <p className="text-xs text-neutral-500">Total Cold</p>
            <p className="text-lg font-bold">{total_cold_leads}</p>
          </div>
          <div className="bg-neutral-800 rounded-lg p-2 text-center">
            <p className="text-xs text-neutral-500">30 Days</p>
            <p className="text-lg font-bold text-red-400">{by_interval[30] || 0}</p>
          </div>
          <div className="bg-neutral-800 rounded-lg p-2 text-center">
            <p className="text-xs text-neutral-500">60 Days</p>
            <p className="text-lg font-bold text-amber-400">{by_interval[60] || 0}</p>
          </div>
          <div className="bg-neutral-800 rounded-lg p-2 text-center">
            <p className="text-xs text-neutral-500">90 Days</p>
            <p className="text-lg font-bold text-blue-400">{by_interval[90] || 0}</p>
          </div>
        </div>

        {/* Candidates */}
        {candidates.length > 0 ? (
          <div>
            <p className="text-xs text-neutral-500 mb-2">Ready for Re-engagement</p>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {candidates.slice(0, 8).map((candidate) => (
                <div key={candidate.lead_id} className="bg-neutral-800 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className={`text-xs ${PRIORITY_COLORS[candidate.priority]}`}>
                        {candidate.priority}
                      </Badge>
                      <span className="font-medium text-sm">{candidate.company_name}</span>
                    </div>
                    <div className="flex items-center gap-3 text-xs text-neutral-500">
                      <span className="flex items-center gap-1">
                        <Clock className="h-3 w-3" />
                        {candidate.days_since_contact}d
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-4 text-xs">
                    {candidate.email && (
                      <span className="flex items-center gap-1 text-neutral-400">
                        <Mail className="h-3 w-3" />
                        {candidate.email.slice(0, 20)}...
                      </span>
                    )}
                    {candidate.phone && (
                      <span className="flex items-center gap-1 text-neutral-400">
                        <MessageCircle className="h-3 w-3" />
                        WA available
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-center py-6 text-neutral-500">
            <Recycle className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No leads ready for recycling</p>
            <p className="text-xs mt-1">Leads appear here after 30/60/90 days of no response</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
