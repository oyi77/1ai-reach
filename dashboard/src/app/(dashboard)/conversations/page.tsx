"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, postJSON, type WANumber, type Conversation, type Message } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Send, User } from "lucide-react";

export default function ConversationsPage() {
  const { data: waData } = useSWR<{ numbers: WANumber[] }>("/api/wa-numbers", fetcher);
  const [selectedWA, setSelectedWA] = useState<string>("");
  const [selectedConv, setSelectedConv] = useState<number | null>(null);
  const [replyText, setReplyText] = useState("");

  const waId = selectedWA || waData?.numbers[0]?.id || "";
  const { data: convData } = useSWR<{ conversations: Conversation[] }>(
    waId ? `/api/conversations?wa_number_id=${waId}` : null, fetcher, { refreshInterval: 5000 }
  );
  const { data: msgData, mutate: mutateMsgs } = useSWR<{ messages: Message[] }>(
    selectedConv ? `/api/conversations/${selectedConv}/messages?limit=100` : null, fetcher, { refreshInterval: 3000 }
  );

  const conversations = convData?.conversations ?? [];
  const messages = msgData?.messages ?? [];

  async function sendReply() {
    if (!selectedConv || !replyText.trim()) return;
    await postJSON(`/api/conversations/${selectedConv}/messages`, { message: replyText });
    setReplyText("");
    mutateMsgs();
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Conversations</h1>
        <Select value={selectedWA} onValueChange={(v) => v && setSelectedWA(v)}>
          <SelectTrigger className="w-64 bg-neutral-900 border-neutral-800">
            <SelectValue placeholder="Select WA Number" />
          </SelectTrigger>
          <SelectContent>
            {waData?.numbers.map((n) => (
              <SelectItem key={n.id} value={n.id}>{n.label} ({n.phone})</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-180px)]">
        <Card className="bg-neutral-900 border-neutral-800 overflow-hidden">
          <CardHeader className="pb-2"><CardTitle className="text-sm">Chats ({conversations.length})</CardTitle></CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[calc(100vh-260px)]">
              {conversations.map((conv) => (
                <button
                  key={conv.id}
                  onClick={() => setSelectedConv(conv.id)}
                  className={`w-full text-left px-4 py-3 border-b border-neutral-800 hover:bg-neutral-800/50 transition-colors ${selectedConv === conv.id ? "bg-orange-500/10 border-l-2 border-l-orange-500" : ""}`}
                >
                  <div className="flex items-center justify-between">
                    <span className="font-medium text-sm">{conv.contact_name || conv.contact_phone}</span>
                    <Badge variant="secondary" className="text-xs bg-neutral-800">{conv.stage}</Badge>
                  </div>
                  <p className="text-xs text-neutral-500 mt-1">{conv.contact_phone}</p>
                </button>
              ))}
              {conversations.length === 0 && <p className="text-neutral-500 text-center py-8 text-sm">No conversations</p>}
            </ScrollArea>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2 bg-neutral-900 border-neutral-800 flex flex-col">
          {selectedConv ? (
            <>
              <CardHeader className="pb-2 border-b border-neutral-800">
                <CardTitle className="text-sm flex items-center gap-2">
                  <User className="h-4 w-4" />
                  {conversations.find((c) => c.id === selectedConv)?.contact_name || "Chat"}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex-1 p-0 overflow-hidden">
                <ScrollArea className="h-[calc(100vh-330px)] p-4">
                  <div className="space-y-3">
                    {messages.map((msg) => (
                      <div key={msg.id} className={`flex ${msg.direction === "outbound" ? "justify-end" : "justify-start"}`}>
                        <div className={`max-w-[70%] rounded-lg px-3 py-2 text-sm ${
                          msg.direction === "outbound"
                            ? "bg-orange-600 text-white"
                            : "bg-neutral-800 text-neutral-200"
                        }`}>
                          <p>{msg.message_text}</p>
                          <p className={`text-xs mt-1 ${msg.direction === "outbound" ? "text-orange-200" : "text-neutral-500"}`}>
                            {msg.created_at?.slice(11, 16)} {msg.source && `(${msg.source})`}
                          </p>
                        </div>
                      </div>
                    ))}
                  </div>
                </ScrollArea>
              </CardContent>
              <div className="p-3 border-t border-neutral-800 flex gap-2">
                <Input
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && sendReply()}
                  placeholder="Type a reply..."
                  className="bg-neutral-800 border-neutral-700"
                />
                <Button onClick={sendReply} size="icon" className="bg-orange-600 hover:bg-orange-700">
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center">
              <p className="text-neutral-500">Select a conversation to view messages</p>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
