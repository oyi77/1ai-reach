"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Activity, AlertTriangle, CheckCircle2, Mail, Shield, AlertCircle } from "lucide-react";
import { useState } from "react";

interface DeliverabilityOverview {
  primary_domain: string;
  domain_score: number;
  domain_status: "healthy" | "needs_attention" | "critical";
  spf_configured: boolean;
  dkim_configured: boolean;
  dmarc_configured: boolean;
  dmarc_policy: string;
  issues_count: number;
  recommendations: string[];
}

function StatusIcon({ status }: { status: string }) {
  if (status === "healthy") return <CheckCircle2 className="h-5 w-5 text-green-400" />;
  if (status === "needs_attention") return <AlertTriangle className="h-5 w-5 text-amber-400" />;
  return <AlertCircle className="h-5 w-5 text-red-400" />;
}

function ScoreGauge({ score, label }: { score: number; label: string }) {
  const color = score >= 80 ? "text-green-400" : score >= 50 ? "text-amber-400" : "text-red-400";
  const bgColor = score >= 80 ? "bg-green-500" : score >= 50 ? "bg-amber-500" : "bg-red-500";
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center">
      <div className="relative w-24 h-24">
        <svg className="w-24 h-24 transform -rotate-90">
          <circle cx="48" cy="48" r="40" stroke="#262626" strokeWidth="8" fill="none" />
          <circle
            cx="48"
            cy="48"
            r="40"
            stroke="currentColor"
            strokeWidth="8"
            fill="none"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className={color}
            style={{ transition: "stroke-dashoffset 0.5s ease" }}
          />
        </svg>
        <div className="absolute inset-0 flex items-center justify-center">
          <span className={`text-2xl font-bold ${color}`}>{score}</span>
        </div>
      </div>
      <p className="text-xs text-neutral-500 mt-2">{label}</p>
    </div>
  );
}

function DNSRecord({ name, configured, details }: { name: string; configured: boolean; details?: string }) {
  return (
    <div className="flex items-center justify-between p-3 bg-neutral-800 rounded-lg">
      <div className="flex items-center gap-3">
        {configured ? (
          <CheckCircle2 className="h-5 w-5 text-green-400" />
        ) : (
          <AlertCircle className="h-5 w-5 text-red-400" />
        )}
        <div>
          <p className="text-sm font-medium">{name}</p>
          {details && <p className="text-xs text-neutral-500 truncate max-w-[200px]">{details}</p>}
        </div>
      </div>
      <Badge variant={configured ? "default" : "destructive"} className="text-xs">
        {configured ? "Configured" : "Missing"}
      </Badge>
    </div>
  );
}

export function DeliverabilityDashboard() {
  const { data, isLoading, error, mutate } = useSWR<{ data: DeliverabilityOverview }>(
    "/api/v1/deliverability/overview",
    fetcher,
    { refreshInterval: 60000 }
  );

  const [startingWarmup, setStartingWarmup] = useState(false);

  if (isLoading) {
    return (
      <Card className="bg-neutral-900 border-neutral-800">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-neutral-500">
            <Activity className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading deliverability...</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (error || !data) {
    return (
      <Card className="bg-red-500/10 border-red-500/40">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-red-400">
            <AlertCircle className="h-4 w-4" />
            <span className="text-sm">Failed to load deliverability data</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const { primary_domain, domain_score, domain_status, spf_configured, dkim_configured, dmarc_configured, dmarc_policy, issues_count, recommendations } = data.data;

  return (
    <Card className="bg-neutral-900 border-neutral-800">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center justify-between">
          <span className="flex items-center gap-2">
            <Shield className="h-4 w-4" />
            Email Deliverability
          </span>
          <Badge variant={domain_status === "healthy" ? "default" : domain_status === "needs_attention" ? "secondary" : "destructive"} className="text-xs">
            <StatusIcon status={domain_status} />
            <span className="ml-1">{domain_status.replace("_", " ").toUpperCase()}</span>
          </Badge>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Domain & Score */}
        <div className="flex items-center justify-between">
          <div>
            <p className="text-xs text-neutral-500">Primary Domain</p>
            <p className="text-sm font-medium">{primary_domain}</p>
          </div>
          <ScoreGauge score={domain_score} label="Deliverability Score" />
        </div>

        {/* DNS Records */}
        <div className="space-y-2">
          <p className="text-xs text-neutral-500 uppercase tracking-wide">DNS Configuration</p>
          <DNSRecord name="SPF" configured={spf_configured} />
          <DNSRecord name="DKIM" configured={dkim_configured} />
          <DNSRecord name="DMARC" configured={dmarc_configured} details={dmarc_policy !== "none" ? `Policy: ${dmarc_policy}` : undefined} />
        </div>

        {/* Issues */}
        {issues_count > 0 && (
          <div className="p-3 bg-amber-500/10 border border-amber-500/40 rounded-lg">
            <div className="flex items-center gap-2 text-amber-400 mb-2">
              <AlertTriangle className="h-4 w-4" />
              <span className="text-sm font-medium">{issues_count} Issue{issues_count > 1 ? "s" : ""} Found</span>
            </div>
            <ul className="text-xs text-neutral-400 space-y-1">
              {recommendations.slice(0, 3).map((rec, i) => (
                <li key={i}>• {rec}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Actions */}
        <div className="flex gap-2 pt-2 border-t border-neutral-800">
          <Button
            variant="outline"
            size="sm"
            className="flex-1 text-xs bg-neutral-800 border-neutral-700"
            onClick={() => mutate()}
          >
            <Activity className="h-3 w-3 mr-1" />
            Refresh
          </Button>
          <Button
            variant="default"
            size="sm"
            className="flex-1 text-xs bg-orange-500 hover:bg-orange-600"
            onClick={async () => {
              setStartingWarmup(true);
              try {
                const res = await fetch("/api/v1/deliverability/warmup/start", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({ email: `marketing@${primary_domain}` }),
                });
                if (res.ok) {
                  alert("Email warm-up started!");
                }
              } finally {
                setStartingWarmup(false);
              }
            }}
            disabled={startingWarmup}
          >
            <Mail className="h-3 w-3 mr-1" />
            {startingWarmup ? "Starting..." : "Start Warm-up"}
          </Button>
        </div>

        {/* All OK message */}
        {issues_count === 0 && (
          <div className="p-3 bg-green-500/10 border border-green-500/40 rounded-lg">
            <div className="flex items-center gap-2 text-green-400">
              <CheckCircle2 className="h-4 w-4" />
              <span className="text-sm">All DNS records configured correctly!</span>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
