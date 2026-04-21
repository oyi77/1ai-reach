"use client";

import { useState, useMemo } from "react";
import useSWR from "swr";
import { fetcher, type Lead } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Loader2, Search, Mail, Phone, Globe, MessageSquare, FileText, Clock } from "lucide-react";

interface TimelineData {
  lead: Lead;
  research: string;
  proposal: {
    email: string;
    whatsapp: string;
  };
  messages: Array<{
    id: number;
    direction: "in" | "out";
    channel: string;
    message_text: string;
    timestamp: string;
  }>;
}

const STAGE_COLORS: Record<string, string> = {
  new: "bg-blue-600",
  enriched: "bg-purple-600",
  draft_ready: "bg-amber-600",
  needs_revision: "bg-red-600",
  reviewed: "bg-emerald-600",
  contacted: "bg-cyan-600",
  followed_up: "bg-pink-600",
  replied: "bg-orange-500",
  meeting_booked: "bg-green-600",
  won: "bg-green-700",
  lost: "bg-red-700",
  cold: "bg-neutral-600",
};

export default function OutreachTrackerPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [selectedLeadId, setSelectedLeadId] = useState<string | null>(null);
  const [sheetOpen, setSheetOpen] = useState(false);

  const { data: leadsData, isLoading: leadsLoading } = useSWR<{ count: number; items: Lead[] }>(
    "/api/v1/agents/leads",
    fetcher,
    { refreshInterval: 10000 }
  );

  const { data: timelineData, isLoading: timelineLoading } = useSWR<TimelineData>(
    selectedLeadId ? `/api/v1/agents/leads/${selectedLeadId}/timeline` : null,
    fetcher
  );

  const leads = leadsData?.items ?? [];

  const filteredLeads = useMemo(() => {
    return leads.filter((lead) => {
      const matchesSearch =
        !searchQuery ||
        (lead.company_name?.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (lead.website?.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (lead.contact_name?.toLowerCase().includes(searchQuery.toLowerCase()));

      const matchesStatus = statusFilter === "all" || lead.status === statusFilter;

      return matchesSearch && matchesStatus;
    });
  }, [leads, searchQuery, statusFilter]);

  const handleRowClick = (leadId: string) => {
    setSelectedLeadId(leadId);
    setSheetOpen(true);
  };

  const handleSheetClose = () => {
    setSheetOpen(false);
    setTimeout(() => setSelectedLeadId(null), 300);
  };

  if (leadsLoading) {
    return (
      <div className="p-6 flex items-center justify-center h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-orange-500" />
      </div>
    );
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <FileText className="h-6 w-6" />
          Outreach Tracker
        </h1>
      </div>

      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader className="pb-3">
          <div className="flex items-center gap-3">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-neutral-500" />
              <Input
                placeholder="Search by company name, website, or contact..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-10 bg-neutral-800 border-neutral-700"
              />
            </div>
            <Select value={statusFilter} onValueChange={(value) => setStatusFilter(value || "all")}>
              <SelectTrigger className="w-48 bg-neutral-800 border-neutral-700">
                <SelectValue placeholder="Filter by status" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All Statuses</SelectItem>
                <SelectItem value="contacted">Contacted</SelectItem>
                <SelectItem value="replied">Replied</SelectItem>
                <SelectItem value="meeting_booked">Meeting Booked</SelectItem>
                <SelectItem value="won">Won</SelectItem>
                <SelectItem value="lost">Lost</SelectItem>
                <SelectItem value="cold">Cold</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {filteredLeads.length > 0 ? (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Company</TableHead>
                  <TableHead>Website</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Contacted</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredLeads.map((lead) => (
                  <TableRow
                    key={lead.id}
                    onClick={() => handleRowClick(lead.id)}
                    className="cursor-pointer hover:bg-neutral-800/50 transition-colors"
                  >
                    <TableCell className="font-medium">
                      {String(lead.company_name || "—")}
                    </TableCell>
                    <TableCell className="text-neutral-400 text-sm">
                      {lead.website || "—"}
                    </TableCell>
                    <TableCell>
                      <Badge className={`${STAGE_COLORS[lead.status] || "bg-neutral-600"} text-white`}>
                        {lead.status.replace(/_/g, " ")}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-neutral-500 text-xs">
                      {(lead as any).contacted_at?.slice(0, 16).replace("T", " ") || "—"}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          ) : (
            <p className="text-neutral-500 text-center py-8">
              {searchQuery || statusFilter !== "all"
                ? "No leads match your filters"
                : "No leads yet. Run the pipeline to scrape leads."}
            </p>
          )}
        </CardContent>
      </Card>

      <Sheet open={sheetOpen} onOpenChange={handleSheetClose}>
        <SheetContent className="w-full sm:max-w-2xl overflow-y-auto">
          {timelineLoading ? (
            <div className="flex items-center justify-center h-full">
              <Loader2 className="h-8 w-8 animate-spin text-orange-500" />
            </div>
          ) : timelineData ? (
            <>
              <SheetHeader>
                <SheetTitle className="text-xl">
                  {String(timelineData.lead.company_name || "Lead Details")}
                </SheetTitle>
                <SheetDescription>
                  Complete outreach timeline and proposal history
                </SheetDescription>
              </SheetHeader>

              <div className="mt-6 space-y-6">
                {/* Lead Info Section */}
                <div className="space-y-3">
                  <h3 className="text-sm font-semibold text-neutral-400 uppercase tracking-wide">
                    Lead Information
                  </h3>
                  <div className="bg-neutral-800/50 rounded-lg p-4 space-y-2">
                    {timelineData.lead.contact_name && (
                      <div className="flex items-center gap-2 text-sm">
                        <span className="text-neutral-500">Contact:</span>
                        <span className="text-neutral-200">{timelineData.lead.contact_name}</span>
                      </div>
                    )}
                    {timelineData.lead.email && (
                      <div className="flex items-center gap-2 text-sm">
                        <Mail className="h-4 w-4 text-neutral-500" />
                        <span className="text-neutral-200">{timelineData.lead.email}</span>
                      </div>
                    )}
                    {timelineData.lead.phone && (
                      <div className="flex items-center gap-2 text-sm">
                        <Phone className="h-4 w-4 text-neutral-500" />
                        <span className="text-neutral-200">{timelineData.lead.phone}</span>
                      </div>
                    )}
                    {timelineData.lead.website && (
                      <div className="flex items-center gap-2 text-sm">
                        <Globe className="h-4 w-4 text-neutral-500" />
                        <a
                          href={timelineData.lead.website}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-orange-400 hover:text-orange-300 underline"
                        >
                          {timelineData.lead.website}
                        </a>
                      </div>
                    )}
                    <div className="flex items-center gap-2 text-sm pt-2 border-t border-neutral-700">
                      <span className="text-neutral-500">Status:</span>
                      <Badge className={`${STAGE_COLORS[timelineData.lead.status] || "bg-neutral-600"} text-white`}>
                        {timelineData.lead.status.replace(/_/g, " ")}
                      </Badge>
                    </div>
                  </div>
                </div>

                {/* Research Brief Section */}
                {timelineData.research && (
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-neutral-400 uppercase tracking-wide">
                      Research Brief
                    </h3>
                    <div className="bg-neutral-800/50 rounded-lg p-4">
                      <ScrollArea className="max-h-64">
                        <pre className="text-sm text-neutral-300 whitespace-pre-wrap font-mono">
                          {timelineData.research}
                        </pre>
                      </ScrollArea>
                    </div>
                  </div>
                )}

                {/* Proposal Section */}
                {(timelineData.proposal.email || timelineData.proposal.whatsapp) && (
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-neutral-400 uppercase tracking-wide">
                      Proposal
                    </h3>
                    <Tabs defaultValue="email" className="w-full">
                      <TabsList className="w-full bg-neutral-800">
                        <TabsTrigger value="email" className="flex-1">
                          <Mail className="h-4 w-4 mr-2" />
                          Email
                        </TabsTrigger>
                        <TabsTrigger value="whatsapp" className="flex-1">
                          <MessageSquare className="h-4 w-4 mr-2" />
                          WhatsApp
                        </TabsTrigger>
                      </TabsList>
                      <TabsContent value="email" className="mt-3">
                        <div className="bg-neutral-800/50 rounded-lg p-4">
                          <ScrollArea className="max-h-96">
                            <div className="text-sm text-neutral-300 whitespace-pre-wrap">
                              {timelineData.proposal.email || "No email proposal available"}
                            </div>
                          </ScrollArea>
                        </div>
                      </TabsContent>
                      <TabsContent value="whatsapp" className="mt-3">
                        <div className="bg-neutral-800/50 rounded-lg p-4">
                          <ScrollArea className="max-h-96">
                            <div className="text-sm text-neutral-300 whitespace-pre-wrap">
                              {timelineData.proposal.whatsapp || "No WhatsApp message available"}
                            </div>
                          </ScrollArea>
                        </div>
                      </TabsContent>
                    </Tabs>
                  </div>
                )}

                {/* Messages Timeline Section */}
                {timelineData.messages && timelineData.messages.length > 0 && (
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold text-neutral-400 uppercase tracking-wide">
                      Messages Timeline
                    </h3>
                    <div className="space-y-2">
                      {timelineData.messages.map((msg) => (
                        <div
                          key={msg.id}
                          className={`flex gap-3 p-3 rounded-lg ${
                            msg.direction === "out"
                              ? "bg-orange-900/20 border border-orange-700/30"
                              : "bg-neutral-800/50 border border-neutral-700"
                          }`}
                        >
                          <div className="flex-shrink-0">
                            {msg.direction === "out" ? (
                              <div className="h-8 w-8 rounded-full bg-orange-600 flex items-center justify-center">
                                <Mail className="h-4 w-4 text-white" />
                              </div>
                            ) : (
                              <div className="h-8 w-8 rounded-full bg-neutral-700 flex items-center justify-center">
                                <MessageSquare className="h-4 w-4 text-neutral-300" />
                              </div>
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2 mb-1">
                              <Badge
                                variant="secondary"
                                className={`text-xs ${
                                  msg.direction === "out"
                                    ? "bg-orange-700 text-white"
                                    : "bg-neutral-700"
                                }`}
                              >
                                {msg.direction === "out" ? "Sent" : "Received"}
                              </Badge>
                              <Badge variant="outline" className="text-xs border-neutral-600">
                                {msg.channel}
                              </Badge>
                              <span className="text-xs text-neutral-500 flex items-center gap-1">
                                <Clock className="h-3 w-3" />
                                {msg.timestamp?.slice(0, 16).replace("T", " ")}
                              </span>
                            </div>
                            <p className="text-sm text-neutral-300 whitespace-pre-wrap">
                              {msg.message_text}
                            </p>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </>
          ) : (
            <div className="flex items-center justify-center h-full">
              <p className="text-neutral-500">No timeline data available</p>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}
