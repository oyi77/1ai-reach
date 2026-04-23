"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, patchJSON, type WANumber } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Loader2 } from "lucide-react";

interface WAHAStatus {
  name: string;
  status: string;
  phone?: string;
}

interface MergedSession extends WANumber {
  live_status?: string;
}

const PERSONAS = [
  "General Assistant",
  "Skincare Expert",
  "Beauty Consultant",
  "Product Specialist",
  "Sales Agent",
  "Customer Support",
];

const MODES = [
  { value: "cs", label: "CS (Customer Service)" },
  { value: "cold", label: "Cold Outreach" },
  { value: "outreach", label: "Warm Outreach" },
  { value: "paused", label: "Paused" },
];

const STATUS_COLORS: Record<string, string> = {
  WORKING: "bg-green-600",
  SCAN_QR_CODE: "bg-yellow-600",
  FAILED: "bg-red-600",
  STOPPED: "bg-red-600",
};

export default function WANumbersPage() {
  const { data: dbData, isLoading: dbLoad } = useSWR<{ numbers: WANumber[] }>(
    "/api/v1/agents/wa/sessions",
    fetcher,
    { refreshInterval: 10000 }
  );
  const { data: statusResponse, isLoading: statusLoad } = useSWR<{ sessions: WAHAStatus[] }>(
    "/api/v1/agents/wa/sessions/status",
    fetcher,
    { refreshInterval: 10000 }
  );
  const statusData = Array.isArray(statusResponse?.sessions) ? statusResponse.sessions : [];

  const [updating, setUpdating] = useState<string | null>(null);

  if (dbLoad || statusLoad) {
    return (
      <div className="p-6 flex items-center justify-center h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-orange-500" />
      </div>
    );
  }

  const sessions: MergedSession[] = (dbData?.numbers || []).map((session) => {
    const liveStatus = statusData.find((s) => s.name === session.session_name);
    return {
      ...session,
      live_status: liveStatus?.status || "UNKNOWN",
    };
  });

  async function updatePersona(sessionId: string, persona: string) {
    setUpdating(sessionId);
    try {
      await patchJSON(`/api/v1/agents/wa/sessions/${sessionId}/persona`, { persona });
    } catch (error) {
      console.error("Failed to update persona:", error);
    } finally {
      setUpdating(null);
    }
  }

  async function updateMode(sessionId: string, mode: string) {
    setUpdating(sessionId);
    try {
      await patchJSON(`/api/v1/agents/wa/sessions/${sessionId}/mode`, { mode });
    } catch (error) {
      console.error("Failed to update mode:", error);
    } finally {
      setUpdating(null);
    }
  }

  return (
    <div className="p-6 space-y-6">
      <h1 className="text-2xl font-bold">WAHA Assignments</h1>

      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader>
          <CardTitle>WhatsApp Sessions ({sessions.length})</CardTitle>
        </CardHeader>
        <CardContent>
          {sessions.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Session Name</TableHead>
                  <TableHead>Label</TableHead>
                  <TableHead>Phone</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Mode</TableHead>
                  <TableHead>Persona</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {sessions.map((session) => (
                  <TableRow key={session.id}>
                    <TableCell className="font-medium font-mono text-sm">
                      {session.session_name}
                    </TableCell>
                    <TableCell>{session.label}</TableCell>
                    <TableCell className="font-mono text-sm">{session.phone || "—"}</TableCell>
                    <TableCell>
                      <Badge
                        className={`${
                          STATUS_COLORS[session.live_status || "UNKNOWN"] || "bg-neutral-600"
                        } text-white`}
                      >
                        {session.live_status || "UNKNOWN"}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <Select
                        value={session.mode}
                        onValueChange={(value) => value && updateMode(session.id, value)}
                        disabled={updating === session.id}
                      >
                        <SelectTrigger className="w-44 bg-neutral-800 border-neutral-700">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {MODES.map((m) => (
                            <SelectItem key={m.value} value={m.value}>
                              {m.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Select
                        value={session.persona || "General Assistant"}
                        onValueChange={(value) => updatePersona(session.id, value || "General Assistant")}
                        disabled={updating === session.id}
                      >
                        <SelectTrigger className="w-48 bg-neutral-800 border-neutral-700">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {PERSONAS.map((persona) => (
                            <SelectItem key={persona} value={persona}>
                              {persona}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-neutral-500 text-center py-8">
              No WAHA sessions found. Configure sessions in the backend.
            </p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
