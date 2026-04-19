"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, patchJSON, type Conversation } from "@/lib/api";
import { Badge } from "@/components/ui/badge";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2 } from "lucide-react";
import type { WANumber } from "@/lib/api";

const STAGES = ["discovery", "interest", "proposal", "negotiation", "close_won", "close_lost"];
const STAGE_COLORS: Record<string, string> = {
  discovery: "border-l-blue-500", interest: "border-l-yellow-500", proposal: "border-l-purple-500",
  negotiation: "border-l-cyan-500", close_won: "border-l-green-500", close_lost: "border-l-red-500",
};

export default function PipelinePage() {
  const { data: waData, isLoading: waLoad } = useSWR<{ numbers: WANumber[] }>("/api/v1/agents/wa/sessions", fetcher);
  const [selectedWA, setSelectedWA] = useState<string>("");
  const [draggedId, setDraggedId] = useState<number | null>(null);
  const waId = selectedWA || waData?.numbers[0]?.id || "";

  const { data: convData, mutate } = useSWR<{ conversations: Conversation[] }>(
    waId ? `/api/v1/legacy/conversations?wa_number_id=${waId}` : null, fetcher, { refreshInterval: 5000 }
  );
  const conversations = convData?.conversations ?? [];

  if (waLoad) {
    return <div className="p-6 flex items-center justify-center h-[50vh]"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  const byStage = Object.fromEntries(STAGES.map((s) => [s, conversations.filter((c) => (c.stage || "discovery") === s)]));

  async function changeStage(convId: number, stage: string) {
    await patchJSON(`/api/v1/legacy/conversations/${convId}/stage`, { stage });
    mutate();
  }

  function handleDragStart(e: React.DragEvent, convId: number) {
    e.dataTransfer.setData("text/plain", String(convId));
    setDraggedId(convId);
  }

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
  }

  function handleDrop(e: React.DragEvent, stage: string) {
    e.preventDefault();
    const convId = Number(e.dataTransfer.getData("text/plain"));
    if (convId) changeStage(convId, stage);
    setDraggedId(null);
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Sales Pipeline</h1>
        <Select value={selectedWA} onValueChange={(v) => v && setSelectedWA(v)}>
          <SelectTrigger className="w-56 bg-neutral-900 border-neutral-800">
            <SelectValue placeholder="Select WA Number" />
          </SelectTrigger>
          <SelectContent>
            {waData?.numbers.map((n) => (
              <SelectItem key={n.id} value={n.id}>{n.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-6 gap-3 h-[calc(100vh-180px)]">
        {STAGES.map((stage) => (
          <div key={stage} className="flex flex-col bg-neutral-900 rounded-lg border border-neutral-800" onDragOver={handleDragOver} onDrop={(e) => handleDrop(e, stage)}>
            <div className={`px-3 py-2 border-b border-neutral-800 border-l-4 ${STAGE_COLORS[stage]}`}>
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wider">{stage.replace("_", " ")}</span>
                <Badge variant="secondary" className="bg-neutral-800 text-xs">{byStage[stage]?.length ?? 0}</Badge>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-2 space-y-2">
              {byStage[stage]?.map((conv) => (
                <div
                  key={conv.id}
                  draggable
                  onDragStart={(e) => handleDragStart(e, conv.id)}
                  className={`bg-neutral-800 rounded-md p-2.5 cursor-grab active:cursor-grabbing hover:bg-neutral-750 border border-neutral-700 ${draggedId === conv.id ? "opacity-50" : ""}`}
                >
                  <p className="text-sm font-medium truncate">{conv.contact_name || conv.contact_phone}</p>
                  <p className="text-xs text-neutral-500 mt-1">{conv.contact_phone}</p>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      {conversations.length === 0 && (
        <p className="text-neutral-500 text-center">No conversations yet. Conversations appear when customers message your WA numbers.</p>
      )}
    </div>
  );
}
