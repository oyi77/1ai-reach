"use client";

import useSWR from "swr";
import { fetcher, type AnalyticsData } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2, TrendingUp, TrendingDown, Mail, MessageCircle, BarChart3, Zap } from "lucide-react";
import { PipelineHealthCard } from "@/components/pipeline-health-card";
import { DeliverabilityDashboard } from "@/components/deliverability-dashboard";

const FUNNEL_STAGES = [
  { key: "new", label: "New", color: "bg-blue-600" },
  { key: "enriched", label: "Enriched", color: "bg-purple-600" },
  { key: "draft_ready", label: "Draft Ready", color: "bg-amber-600" },
  { key: "reviewed", label: "Reviewed", color: "bg-emerald-600" },
  { key: "contacted", label: "Contacted", color: "bg-cyan-600" },
  { key: "replied", label: "Replied", color: "bg-orange-500" },
  { key: "meeting_booked", label: "Meeting Booked", color: "bg-green-600" },
  { key: "won", label: "Won", color: "bg-green-700" },
];

const CONVERSION_STEPS = [
  { key: "new_to_enriched", label: "New → Enriched" },
  { key: "enriched_to_draft", label: "Enriched → Draft" },
  { key: "draft_to_reviewed", label: "Draft → Reviewed" },
  { key: "reviewed_to_contacted", label: "Reviewed → Contacted" },
  { key: "contacted_to_replied", label: "Contacted → Replied" },
  { key: "replied_to_meeting", label: "Replied → Meeting" },
  { key: "meeting_to_won", label: "Meeting → Won" },
];

function Pct({ value, bold }: { value: number; bold?: boolean }) {
  const color = value >= 30 ? "text-green-400" : value >= 10 ? "text-amber-400" : "text-red-400";
  return <span className={`${color} ${bold ? "font-bold text-lg" : "text-sm"}`}>{value}%</span>;
}

function StatCard({
  title,
  value,
  sub,
  icon: Icon,
  highlight,
}: {
  title: string;
  value: string | number;
  sub?: string;
  icon?: React.ElementType;
  highlight?: boolean;
}) {
  return (
    <Card className={`${highlight ? "bg-orange-500/10 border-orange-500/40" : "bg-neutral-900 border-neutral-800"}`}>
      <CardContent className="pt-4 pb-4">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-neutral-500 uppercase tracking-wide">{title}</p>
            <p className={`text-2xl font-bold mt-1 ${highlight ? "text-orange-400" : ""}`}>{value}</p>
            {sub && <p className="text-xs text-neutral-500 mt-1">{sub}</p>}
          </div>
          {Icon && <Icon className={`h-5 w-5 mt-1 ${highlight ? "text-orange-400" : "text-neutral-600"}`} />}
        </div>
      </CardContent>
    </Card>
  );
}

export default function AnalyticsPage() {
  const { data, isLoading, error } = useSWR<AnalyticsData>("/api/v1/agents/analytics", fetcher, {
    refreshInterval: 30000,
  });

  if (isLoading) {
    return (
      <div className="p-6 flex items-center justify-center h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-orange-500" />
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="p-6">
        <p className="text-red-400">Failed to load analytics. Is the API running?</p>
      </div>
    );
  }

  const { kpis, conversion_rates, funnel_counts, channel_email, channel_wa, velocity, industry_performance, tier_stats, score_histogram, service_performance } = data;

  const maxFunnelCount = Math.max(...FUNNEL_STAGES.map((s) => funnel_counts[s.key] ?? 0), 1);

  return (
    <div className="p-6 space-y-6">
      <div className="flex items-center gap-3">
        <BarChart3 className="h-6 w-6 text-orange-500" />
        <h1 className="text-2xl font-bold">Marketing Analytics</h1>
        <Badge variant="outline" className="border-neutral-700 text-neutral-500 text-xs ml-auto">
          auto-refresh 30s
        </Badge>
      </div>

      {/* ── Pipeline Health Widget ── */}
      <DeliverabilityDashboard />
      <PipelineHealthCard />

      {/* ── Section 1: KPI Cards ── */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        <StatCard
          title="Full Funnel"
          value={`${kpis.full_funnel_conversion}%`}
          sub="new → won"
          icon={TrendingUp}
          highlight
        />
        <StatCard
          title="Reply Rate"
          value={`${kpis.reply_rate}%`}
          sub="contacted → replied"
          icon={MessageCircle}
          highlight
        />
        <StatCard title="Avg Lead Score" value={kpis.avg_lead_score} sub="out of 10" icon={Zap} />
        <StatCard title="This Week" value={`+${kpis.leads_this_week}`} sub="new leads" />
        <StatCard title="Pipeline Active" value={kpis.pipeline_active} sub="working leads" />
        <StatCard title="Total Leads" value={kpis.total_leads} />
      </div>

      {/* ── Section 2: Conversion Funnel ── */}
      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader>
          <CardTitle className="text-base">Conversion Funnel</CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          {FUNNEL_STAGES.map((stage, i) => {
            const count = funnel_counts[stage.key] ?? 0;
            const barPct = Math.round((count / maxFunnelCount) * 100);
            const convKey = CONVERSION_STEPS[i]?.key as keyof typeof conversion_rates | undefined;
            const convRate = convKey ? conversion_rates[convKey] : null;
            return (
              <div key={stage.key}>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-neutral-400 w-28 truncate">{stage.label}</span>
                  <div className="flex-1 bg-neutral-800 rounded-full h-5 overflow-hidden">
                    <div
                      className={`${stage.color} h-full rounded-full transition-all`}
                      style={{ width: `${barPct}%` }}
                    />
                  </div>
                  <span className="text-sm font-medium w-10 text-right">{count}</span>
                  {convRate !== null && i < FUNNEL_STAGES.length - 1 && (
                    <span className="text-xs text-neutral-500 w-14 text-right">→ {convRate}%</span>
                  )}
                </div>
              </div>
            );
          })}
        </CardContent>
      </Card>

      {/* ── Section 3: Stage-to-Stage Conversion Rates ── */}
      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader>
          <CardTitle className="text-base">Stage Conversion Rates</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {CONVERSION_STEPS.map((step) => {
              const rate = conversion_rates[step.key as keyof typeof conversion_rates];
              return (
                <div key={step.key} className="bg-neutral-800 rounded-lg p-3 text-center">
                  <p className="text-xs text-neutral-500 mb-1">{step.label}</p>
                  <Pct value={rate} bold />
                </div>
              );
            })}
          </div>
        </CardContent>
      </Card>

      {/* ── Section 4: Channel Performance ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <Mail className="h-4 w-4 text-blue-400" /> Email Performance
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              { label: "Sent", value: channel_email.sent },
              { label: "Delivered", value: channel_email.delivered, rate: channel_email.delivery_rate },
              { label: "Opened", value: channel_email.opened, rate: channel_email.open_rate },
              { label: "Clicked", value: channel_email.clicked, rate: channel_email.click_rate },
              { label: "Bounced", value: channel_email.bounced, rate: channel_email.bounce_rate, isNeg: true },
            ].map((row) => (
              <div key={row.label} className="flex items-center justify-between">
                <span className="text-sm text-neutral-400">{row.label}</span>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium">{row.value}</span>
                  {row.rate !== undefined && (
                    <span
                      className={`text-xs px-1.5 py-0.5 rounded ${row.isNeg ? "bg-red-500/20 text-red-400" : "bg-green-500/20 text-green-400"}`}
                    >
                      {row.rate}%
                    </span>
                  )}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>

        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader>
            <CardTitle className="text-base flex items-center gap-2">
              <MessageCircle className="h-4 w-4 text-green-400" /> WhatsApp Performance
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {[
              { label: "Sent", value: channel_wa.sent },
              { label: "Replied", value: channel_wa.replied, rate: channel_wa.reply_rate },
            ].map((row) => (
              <div key={row.label} className="flex items-center justify-between">
                <span className="text-sm text-neutral-400">{row.label}</span>
                <div className="flex items-center gap-3">
                  <span className="text-sm font-medium">{row.value}</span>
                  {row.rate !== undefined && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-green-500/20 text-green-400">{row.rate}%</span>
                  )}
                </div>
              </div>
            ))}
            <div className="mt-4 pt-4 border-t border-neutral-800">
              <p className="text-xs text-neutral-500">Lead velocity</p>
              <div className="flex gap-4 mt-2">
                <div>
                  <p className="text-lg font-bold">{velocity.leads_this_week}</p>
                  <p className="text-xs text-neutral-500">this week</p>
                </div>
                <div>
                  <p className="text-lg font-bold">{velocity.leads_this_month}</p>
                  <p className="text-xs text-neutral-500">this month</p>
                </div>
                {velocity.avg_days_to_contact !== null && (
                  <div>
                    <p className="text-lg font-bold">{velocity.avg_days_to_contact}d</p>
                    <p className="text-xs text-neutral-500">avg to contact</p>
                  </div>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* ── Section 5: Tier + Score Distribution ── */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader>
            <CardTitle className="text-base">Lead Tier Distribution</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(["hot", "warm", "cold", "skip"] as const).map((tier) => {
              const stats = tier_stats[tier];
              if (!stats) return null;
              const tierColorBg: Record<string, string> = {
                hot: "bg-red-500",
                warm: "bg-amber-500",
                cold: "bg-blue-500",
                skip: "bg-neutral-500",
              };
              const tierColorText: Record<string, string> = {
                hot: "text-red-400",
                warm: "text-amber-400",
                cold: "text-blue-400",
                skip: "text-neutral-400",
              };
              const totalTier = Object.values(tier_stats).reduce((s, t) => s + t.count, 0);
              const barPct = totalTier > 0 ? Math.round((stats.count / totalTier) * 100) : 0;
              return (
                <div key={tier}>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs font-medium w-10 ${tierColorText[tier]}`}>
                      {tier.toUpperCase()}
                    </span>
                    <div className="flex-1 bg-neutral-800 rounded-full h-4 overflow-hidden">
                      <div className={`${tierColorBg[tier]} h-full rounded-full`} style={{ width: `${barPct}%` }} />
                    </div>
                    <span className="text-xs text-neutral-400 w-8 text-right">{stats.count}</span>
                    <span className="text-xs text-green-400 w-16 text-right">
                      {stats.reply_rate}% reply
                    </span>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>

        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader>
            <CardTitle className="text-base">Lead Score Distribution</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {(["0-3", "3-5", "5-7", "7-10"] as const).map((bucket) => {
              const count = score_histogram[bucket] ?? 0;
              const totalScored = Object.values(score_histogram).reduce((a, b) => a + b, 0);
              const barPct = totalScored > 0 ? Math.round((count / totalScored) * 100) : 0;
              const colors = ["bg-red-600", "bg-amber-600", "bg-yellow-500", "bg-green-500"];
              const colorIdx = ["0-3", "3-5", "5-7", "7-10"].indexOf(bucket);
              return (
                <div key={bucket} className="flex items-center gap-3">
                  <span className="text-xs text-neutral-400 w-12">{bucket}</span>
                  <div className="flex-1 bg-neutral-800 rounded-full h-4 overflow-hidden">
                    <div className={`${colors[colorIdx]} h-full rounded-full`} style={{ width: `${barPct}%` }} />
                  </div>
                  <span className="text-xs text-neutral-400 w-8 text-right">{count}</span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      </div>

      {/* ── Section 6: Industry Performance Table ── */}
      {industry_performance.length > 0 && (
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader>
            <CardTitle className="text-base">Industry Performance</CardTitle>
          </CardHeader>
          <CardContent>
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Industry</TableHead>
                  <TableHead className="text-right">Leads</TableHead>
                  <TableHead className="text-right">Contacted</TableHead>
                  <TableHead className="text-right">Replied</TableHead>
                  <TableHead className="text-right">Reply Rate</TableHead>
                  <TableHead className="text-right">Converted</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {industry_performance.slice(0, 15).map((row) => {
                  const rowBg =
                    row.reply_rate >= 20
                      ? "bg-green-500/5"
                      : row.reply_rate === 0 && row.contacted > 0
                      ? "bg-red-500/5"
                      : "";
                  return (
                    <TableRow key={row.industry} className={rowBg}>
                      <TableCell className="font-medium text-xs">{row.industry.replace(/_/g, " ")}</TableCell>
                      <TableCell className="text-right text-xs">{row.leads}</TableCell>
                      <TableCell className="text-right text-xs">{row.contacted}</TableCell>
                      <TableCell className="text-right text-xs">{row.replied}</TableCell>
                      <TableCell className="text-right text-xs">
                        <Pct value={row.reply_rate} />
                      </TableCell>
                      <TableCell className="text-right text-xs">{row.converted}</TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {/* ── Section 7: Service Performance ── */}
      {service_performance.length > 0 && (
        <Card className="bg-neutral-900 border-neutral-800">
          <CardHeader>
            <CardTitle className="text-base">Service Performance</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {service_performance.slice(0, 10).map((svc) => {
              const maxSvcCount = Math.max(...service_performance.map((s) => s.total), 1);
              const barPct = Math.round((svc.total / maxSvcCount) * 100);
              return (
                <div key={svc.service} className="flex items-center gap-3">
                  <span className="text-xs text-neutral-400 w-40 truncate">{svc.service.replace(/_/g, " ")}</span>
                  <div className="flex-1 bg-neutral-800 rounded-full h-4 overflow-hidden">
                    <div className="bg-orange-500 h-full rounded-full" style={{ width: `${barPct}%` }} />
                  </div>
                  <span className="text-xs text-neutral-400 w-8 text-right">{svc.total}</span>
                  <span className="text-xs text-green-400 w-16 text-right">{svc.reply_rate}% reply</span>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
