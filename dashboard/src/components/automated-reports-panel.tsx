"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { FileText, Mail, Calendar, AlertCircle, Download } from "lucide-react";

interface Report {
  id: string;
  report_type: string;
  period: string;
  generated_at: string;
  file_path: string;
  pipeline: Record<string, number>;
  conversion_rates: Record<string, string>;
}

interface ReportsOverview {
  total_reports: number;
  weekly_reports: number;
  monthly_reports: number;
  recent_reports: Report[];
}

export function AutomatedReportsPanel() {
  const { data, isLoading, error, mutate } = useSWR<{ data: ReportsOverview }>(
    "/api/v1/reports/overview",
    fetcher,
    { refreshInterval: 300000 }
  );

  if (isLoading) {
    return (
      <Card className="bg-neutral-900 border-neutral-800">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-neutral-500">
            <FileText className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading reports...</span>
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
            <span className="text-sm">Reports unavailable</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const { total_reports, weekly_reports, monthly_reports, recent_reports } = data.data;

  return (
    <Card className="bg-neutral-900 border-neutral-800">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center justify-between">
          <span className="flex items-center gap-2">
            <FileText className="h-4 w-4 text-blue-400" />
            Automated Reports
          </span>
          <Button variant="outline" size="sm" className="h-6 text-xs bg-neutral-800 border-neutral-700" onClick={() => mutate()}>
            Refresh
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {/* Summary */}
        <div className="grid grid-cols-3 gap-2">
          <div className="bg-neutral-800 rounded-lg p-3 text-center">
            <p className="text-xs text-neutral-500">Total</p>
            <p className="text-lg font-bold">{total_reports}</p>
          </div>
          <div className="bg-neutral-800 rounded-lg p-3 text-center">
            <p className="text-xs text-neutral-500">Weekly</p>
            <p className="text-lg font-bold text-blue-400">{weekly_reports}</p>
          </div>
          <div className="bg-neutral-800 rounded-lg p-3 text-center">
            <p className="text-xs text-neutral-500">Monthly</p>
            <p className="text-lg font-bold text-purple-400">{monthly_reports}</p>
          </div>
        </div>

        {/* Recent Reports */}
        {recent_reports.length > 0 ? (
          <div>
            <p className="text-xs text-neutral-500 mb-2">Recent Reports</p>
            <div className="space-y-2 max-h-64 overflow-y-auto">
              {recent_reports.slice(0, 6).map((report) => (
                <div key={report.id} className="bg-neutral-800 rounded-lg p-3">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Badge variant="outline" className="text-xs">
                        {report.report_type}
                      </Badge>
                      <span className="font-medium text-sm">{report.period}</span>
                    </div>
                    <span className="text-xs text-neutral-500">
                      {new Date(report.generated_at).toLocaleDateString()}
                    </span>
                  </div>

                  {/* Key Metrics */}
                  <div className="grid grid-cols-3 gap-2 text-xs">
                    <div>
                      <p className="text-neutral-500">Leads</p>
                      <p className="font-medium">{report.pipeline?.total_leads || 0}</p>
                    </div>
                    <div>
                      <p className="text-neutral-500">Contacted</p>
                      <p className="font-medium">{report.pipeline?.contacted || 0}</p>
                    </div>
                    <div>
                      <p className="text-neutral-500">Reply Rate</p>
                      <p className="font-medium text-green-400">{report.conversion_rates?.reply_rate || "0%"}</p>
                    </div>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 mt-2 pt-2 border-t border-neutral-700">
                    <Button variant="outline" size="sm" className="flex-1 h-7 text-xs bg-neutral-700 border-neutral-600">
                      <Download className="h-3 w-3 mr-1" />
                      Download
                    </Button>
                    <Button variant="outline" size="sm" className="flex-1 h-7 text-xs bg-neutral-700 border-neutral-600">
                      <Mail className="h-3 w-3 mr-1" />
                      Email
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ) : (
          <div className="text-center py-6 text-neutral-500">
            <FileText className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No reports generated yet</p>
            <p className="text-xs mt-1">Weekly and monthly reports auto-generated</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
