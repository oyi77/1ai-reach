"use client";

import { useState, useEffect } from "react";
import { Mail, Check, Eye, MousePointer, AlertCircle } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  fetchConversationEmails,
  fetchConversationEmailStats,
  type EmailEvent,
  type EmailStats,
} from "@/lib/api";

interface EmailTrackingPanelProps {
  conversationId: number | null;
}

const eventIcons: Record<string, React.ReactNode> = {
  sent: <Mail className="h-4 w-4" />,
  delivered: <Check className="h-4 w-4" />,
  opened: <Eye className="h-4 w-4" />,
  clicked: <MousePointer className="h-4 w-4" />,
  bounced: <AlertCircle className="h-4 w-4" />,
};

const eventColors: Record<string, string> = {
  sent: "bg-blue-100 text-blue-700",
  delivered: "bg-green-100 text-green-700",
  opened: "bg-purple-100 text-purple-700",
  clicked: "bg-orange-100 text-orange-700",
  bounced: "bg-red-100 text-red-700",
};

export function EmailTrackingPanel({ conversationId }: EmailTrackingPanelProps) {
  const [events, setEvents] = useState<EmailEvent[]>([]);
  const [stats, setStats] = useState<EmailStats | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!conversationId) {
      setEvents([]);
      setStats(null);
      return;
    }
    loadEmailData();
  }, [conversationId]);

  const loadEmailData = async () => {
    if (!conversationId) return;
    setLoading(true);
    try {
      const [eventsData, statsData] = await Promise.all([
        fetchConversationEmails(conversationId),
        fetchConversationEmailStats(conversationId),
      ]);
      setEvents(eventsData.events);
      setStats(statsData);
    } catch (err) {
      console.error("Failed to load email data:", err);
    } finally {
      setLoading(false);
    }
  };

  if (!conversationId) {
    return (
      <Card>
        <CardContent className="flex items-center justify-center h-40 text-muted-foreground">
          Select a conversation to view email tracking
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium flex items-center gap-2">
          <Mail className="h-4 w-4" />
          Email Tracking
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {stats && (
          <div className="grid grid-cols-4 gap-2 text-center">
            <div className="bg-muted rounded p-2">
              <div className="text-lg font-bold">{stats.total_sent}</div>
              <div className="text-xs text-muted-foreground">Sent</div>
            </div>
            <div className="bg-muted rounded p-2">
              <div className="text-lg font-bold">{stats.total_delivered}</div>
              <div className="text-xs text-muted-foreground">Delivered</div>
            </div>
            <div className="bg-muted rounded p-2">
              <div className="text-lg font-bold">{stats.total_opened}</div>
              <div className="text-xs text-muted-foreground">Opened</div>
            </div>
            <div className="bg-muted rounded p-2">
              <div className="text-lg font-bold">{stats.total_clicked}</div>
              <div className="text-xs text-muted-foreground">Clicked</div>
            </div>
          </div>
        )}

        {loading ? (
          <div className="text-center py-4 text-muted-foreground">Loading...</div>
        ) : events.length === 0 ? (
          <div className="text-center py-4 text-muted-foreground text-sm">
            No email events for this conversation
          </div>
        ) : (
          <div className="space-y-2 max-h-60 overflow-y-auto">
            {events.map((event) => (
              <div
                key={event.id}
                className="flex items-center gap-3 p-2 rounded border text-sm"
              >
                <Badge
                  variant="secondary"
                  className={eventColors[event.event_type] || "bg-gray-100"}
                >
                  {eventIcons[event.event_type] || <Mail className="h-4 w-4" />}
                </Badge>
                <div className="flex-1 min-w-0">
                  <div className="truncate">{event.email}</div>
                  <div className="text-xs text-muted-foreground">
                    {event.subject || event.event_type}
                  </div>
                </div>
                <div className="text-xs text-muted-foreground whitespace-nowrap">
                  {new Date(event.timestamp).toLocaleString()}
                </div>
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
