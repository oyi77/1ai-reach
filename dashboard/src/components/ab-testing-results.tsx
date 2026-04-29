"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { BarChart3, TrendingUp, AlertCircle, Mail } from "lucide-react";

interface ABTest {
  id: string;
  name: string;
  test_type: string;
  status: string;
  variant_a_rate: number;
  variant_b_rate: number;
  winner: string | null;
  confidence: number;
  total_samples: number;
  created_at: string;
}

interface ABTestingOverview {
  active_tests: number;
  completed_tests: number;
  tests: ABTest[];
}

export function ABTestingResults() {
  const { data, isLoading, error, mutate } = useSWR<ABTestingOverview>(
    "/api/v1/optimization/ab-tests",
    fetcher,
    { refreshInterval: 60000 }
  );

  if (isLoading) {
    return (
      <Card className="bg-neutral-900 border-neutral-800">
        <CardContent className="pt-4 pb-4">
          <div className="flex items-center gap-2 text-neutral-500">
            <BarChart3 className="h-4 w-4 animate-spin" />
            <span className="text-sm">Loading A/B tests...</span>
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
            <span className="text-sm">A/B test data unavailable</span>
          </div>
        </CardContent>
      </Card>
    );
  }

  const { active_tests, completed_tests, tests } = data;

  return (
    <Card className="bg-neutral-900 border-neutral-800">
      <CardHeader className="pb-2">
        <CardTitle className="text-sm flex items-center justify-between">
          <span className="flex items-center gap-2">
            <BarChart3 className="h-4 w-4 text-purple-400" />
            A/B Testing Results
          </span>
          <div className="flex gap-2">
            {active_tests > 0 && (
              <Badge variant="default" className="text-xs bg-green-500">
                {active_tests} Active
              </Badge>
            )}
            <Button variant="outline" size="sm" className="h-6 text-xs bg-neutral-800 border-neutral-700" onClick={() => mutate()}>
              Refresh
            </Button>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* Summary */}
        <div className="grid grid-cols-2 gap-2">
          <div className="bg-neutral-800 rounded-lg p-3">
            <p className="text-xs text-neutral-500">Active Tests</p>
            <p className="text-lg font-bold text-green-400">{active_tests}</p>
          </div>
          <div className="bg-neutral-800 rounded-lg p-3">
            <p className="text-xs text-neutral-500">Completed</p>
            <p className="text-lg font-bold">{completed_tests}</p>
          </div>
        </div>

        {/* Tests List */}
        {tests.length > 0 ? (
          <div className="space-y-2 max-h-64 overflow-y-auto">
            {tests.slice(0, 6).map((test) => (
              <div key={test.id} className="bg-neutral-800 rounded-lg p-3">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <Badge variant="outline" className="text-xs">
                      {test.test_type}
                    </Badge>
                    <span className="font-medium text-sm">{test.name}</span>
                  </div>
                  <Badge variant={test.status === "active" ? "default" : "secondary"} className="text-xs">
                    {test.status}
                  </Badge>
                </div>

                {/* Variant Comparison */}
                <div className="grid grid-cols-2 gap-2 mb-2">
                  <div className="bg-neutral-700/50 rounded p-2 text-center">
                    <p className="text-xs text-neutral-400">Variant A</p>
                    <p className="text-sm font-bold">{test.variant_a_rate}%</p>
                  </div>
                  <div className="bg-neutral-700/50 rounded p-2 text-center">
                    <p className="text-xs text-neutral-400">Variant B</p>
                    <p className="text-sm font-bold">{test.variant_b_rate}%</p>
                  </div>
                </div>

                {/* Winner & Confidence */}
                {test.winner && (
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1 text-green-400">
                      <TrendingUp className="h-3 w-3" />
                      Winner: {test.winner}
                    </span>
                    <span className="text-neutral-500">{test.confidence}% confidence</span>
                  </div>
                )}

                {!test.winner && test.status === "active" && (
                  <div className="text-xs text-neutral-500">
                    <Mail className="h-3 w-3 inline mr-1" />
                    {test.total_samples} samples collected
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-center py-6 text-neutral-500">
            <BarChart3 className="h-12 w-12 mx-auto mb-3 opacity-30" />
            <p className="text-sm">No A/B tests yet</p>
            <p className="text-xs mt-1">Create tests to optimize your outreach</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
