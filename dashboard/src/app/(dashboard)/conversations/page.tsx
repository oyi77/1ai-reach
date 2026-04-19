"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import useSWR from "swr";
import { fetcher, postJSON, type WANumber, type Conversation, type Message } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Send, User, Loader2, ThumbsUp, ThumbsDown, MessageSquare, Bot, Hand, Play } from "lucide-react";

type Feedback = { id: number; message_id: number; rating: string; note: string; corrected_response: string };

export default function ConversationsPage() {
  const { data: waData, isLoading: waLoad } = useSWR<{ numbers: WANumber[] }>("/api/v1/agents/wa/sessions", fetcher);
  const [selectedWA, setSelectedWA] = useState<string>("");
  const [selectedConv, setSelectedConv] = useState<number | null>(null);
  const [replyText, setReplyText] = useState("");
  const [feedbackMsgId, setFeedbackMsgId] = useState<number | null>(null);
  const [feedbackRating, setFeedbackRating] = useState<"good" | "bad">("good");
  const [feedbackNote, setFeedbackNote] = useState("");
  const [feedbackCorrected, setFeedbackCorrected] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (waData?.numbers && waData.numbers.length > 0 && !selectedWA) {
      setSelectedWA(waData.numbers[0].id);
    }
  }, [waData, selectedWA]);

  const waId = selectedWA || "";
  const { data: convData } = useSWR<{ conversations: Conversation[] }>(
    waId ? `/api/v1/legacy/conversations?wa_number_id=${waId}` : null, fetcher, { refreshInterval: 5000 }
  );
  const { data: msgData, mutate: mutateMsgs } = useSWR<{ messages: Message[] }>(
    selectedConv ? `/api/v1/legacy/conversations/${selectedConv}/messages?limit=200` : null, fetcher, { refreshInterval: 3000 }
  );
  const { data: fbData } = useSWR<{ feedback: Feedback[] }>(
    selectedConv ? `/api/v1/legacy/conversations/${selectedConv}/feedback` : null, fetcher
  );

  const conversations = convData?.conversations ?? [];
  const messages = useMemo(() => msgData?.messages ?? [], [msgData?.messages]);
  const feedbackMap = new Map((fbData?.feedback ?? []).map((f) => [f.message_id, f]));

  const currentConv = conversations.find((c) => c.id === selectedConv);
  const isManualMode = currentConv?.manual_mode === 1;

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  if (waLoad) {
    return <div className="p-6 flex items-center justify-center h-[50vh]"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  async function sendReply() {
    if (!selectedConv || !replyText.trim()) return;
    await postJSON(`/api/v1/legacy/conversations/${selectedConv}/messages`, { message: replyText });
    setReplyText("");
    mutateMsgs();
  }

  async function submitFeedback() {
    if (!selectedConv || !feedbackMsgId) return;
    setSubmitting(true);
    try {
      await postJSON(`/api/v1/legacy/conversations/${selectedConv}/feedback`, {
        message_id: feedbackMsgId,
        rating: feedbackRating,
        note: feedbackNote,
        corrected_response: feedbackCorrected,
      });
      setFeedbackMsgId(null);
      setFeedbackNote("");
      setFeedbackCorrected("");
      mutateMsgs();
    } finally {
      setSubmitting(false);
    }
  }

  async function toggleTakeover(takeover: boolean) {
    if (!selectedConv) return;
    const endpoint = takeover ? "takeover" : "release";
    await postJSON(`/api/v1/legacy/conversations/${selectedConv}/${endpoint}`, {});
    mutateMsgs();
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <MessageSquare className="h-6 w-6" />
          Chat Review
        </h1>
        <div className="flex gap-2 items-center">
          <Select value={selectedWA} onValueChange={(v) => { setSelectedWA(v || ""); setSelectedConv(null); }}>
            <SelectTrigger className="w-64 bg-neutral-900 border-neutral-800">
              <SelectValue placeholder="Select WA Number" />
            </SelectTrigger>
            <SelectContent>
              {waData?.numbers.map((n) => (
                <SelectItem key={n.id} value={n.id}>{n.label} ({n.phone})</SelectItem>
              ))}
            </SelectContent>
          </Select>
          {selectedConv && (
            isManualMode ? (
              <Button onClick={() => toggleTakeover(false)} variant="outline" className="border-green-700 text-green-400">
                <Play className="h-4 w-4 mr-1" /> Return to AI
              </Button>
            ) : (
              <Button onClick={() => toggleTakeover(true)} variant="outline" className="border-orange-700 text-orange-400">
                <Hand className="h-4 w-4 mr-1" /> Take Over
              </Button>
            )
          )}
        </div>
      </div>

      {selectedConv && isManualMode && (
        <div className="bg-orange-950 border border-orange-700 rounded-lg p-3 text-sm text-orange-200 flex items-center gap-2">
          <Hand className="h-4 w-4" />
          <span className="font-semibold">Admin mode</span> — your replies go directly to the customer. AI is paused.
        </div>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-220px)]">
        <Card className="bg-neutral-900 border-neutral-800 overflow-hidden">
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Chats ({conversations.length})</CardTitle>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[calc(100vh-300px)]">
              {conversations.map((conv) => {
                const lastMsg = conv.last_message_text || conv.contact_phone;
                const hasManual = conv.manual_mode === 1;
                return (
                  <button
                    key={conv.id}
                    onClick={() => setSelectedConv(conv.id)}
                    className={`w-full text-left px-4 py-3 border-b border-neutral-800 hover:bg-neutral-800/50 transition-colors ${selectedConv === conv.id ? "bg-orange-500/10 border-l-2 border-l-orange-500" : ""}`}
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-sm truncate max-w-[160px]">{conv.contact_name || conv.contact_phone}</span>
                      <div className="flex gap-1">
                        {hasManual && <Badge className="text-xs bg-orange-700">Admin</Badge>}
                        <Badge variant="secondary" className="text-xs bg-neutral-800">{conv.stage}</Badge>
                      </div>
                    </div>
                    <p className="text-xs text-neutral-500 mt-1 truncate">{lastMsg}</p>
                  </button>
                );
              })}
              {conversations.length === 0 && <p className="text-neutral-500 text-center py-8 text-sm">No conversations</p>}
            </ScrollArea>
          </CardContent>
        </Card>

        <Card className="lg:col-span-2 bg-neutral-900 border-neutral-800 flex flex-col">
          {selectedConv ? (
            <>
              <CardHeader className="pb-2 border-b border-neutral-800">
                <CardTitle className="text-sm flex items-center gap-3">
                  <User className="h-4 w-4" />
                  <span>{currentConv?.contact_name || currentConv?.contact_phone}</span>
                  <span className="text-neutral-500 text-xs">{currentConv?.contact_phone}</span>
                </CardTitle>
              </CardHeader>
              <CardContent className="flex-1 p-0 overflow-hidden">
                <ScrollArea className="h-[calc(100vh-370px)] p-4">
                  <div ref={scrollRef} className="space-y-3">
                    {messages.map((msg) => {
                      const fb = feedbackMap.get(msg.id);
                      const isAI = msg.direction === "out";
                      return (
                        <div key={msg.id} className={`flex ${isAI ? "justify-end" : "justify-start"}`}>
                          <div className={`max-w-[75%] rounded-lg px-3 py-2 text-sm relative group ${
                            isAI
                              ? fb?.rating === "good" ? "bg-green-900/50 border border-green-700 text-white"
                                : fb?.rating === "bad" ? "bg-red-900/50 border border-red-700 text-white"
                                : "bg-orange-600 text-white"
                              : "bg-neutral-800 text-neutral-200"
                          }`}>
                            {isAI && (
                              <div className="flex items-center gap-1 mb-1">
                                <Bot className="h-3 w-3" />
                                <span className="text-xs opacity-70">AI</span>
                                {fb?.rating === "good" && <ThumbsUp className="h-3 w-3 text-green-400 ml-1" />}
                                {fb?.rating === "bad" && <ThumbsDown className="h-3 w-3 text-red-400 ml-1" />}
                              </div>
                            )}
                            <p className="whitespace-pre-wrap">{msg.message_text}</p>
                            <div className="flex items-center justify-between mt-1">
                              <p className={`text-xs ${isAI ? "text-orange-200" : "text-neutral-500"}`}>
                                {msg.timestamp?.slice(11, 16)}
                              </p>
                              {isAI && !fb && (
                                <div className="opacity-0 group-hover:opacity-100 transition-opacity flex gap-1">
                                  <button onClick={() => { setFeedbackMsgId(msg.id); setFeedbackRating("good"); }} className="p-1 rounded hover:bg-green-800 text-green-300" title="Good response">
                                    <ThumbsUp className="h-3 w-3" />
                                  </button>
                                  <button onClick={() => { setFeedbackMsgId(msg.id); setFeedbackRating("bad"); }} className="p-1 rounded hover:bg-red-800 text-red-300" title="Bad response">
                                    <ThumbsDown className="h-3 w-3" />
                                  </button>
                                </div>
                              )}
                            </div>
                            {fb?.corrected_response && (
                              <div className="mt-2 pt-2 border-t border-neutral-600">
                                <p className="text-xs text-yellow-300 mb-1">Corrected:</p>
                                <p className="text-xs text-yellow-100">{fb.corrected_response}</p>
                              </div>
                            )}
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </ScrollArea>
              </CardContent>
              <div className="p-3 border-t border-neutral-800 flex gap-2">
                <Input
                  value={replyText}
                  onChange={(e) => setReplyText(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && sendReply()}
                  placeholder={isManualMode ? "Reply as admin..." : "Reply..."}
                  className="bg-neutral-800 border-neutral-700"
                />
                <Button onClick={sendReply} size="icon" className="bg-orange-600 hover:bg-orange-700">
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </>
          ) : (
            <div className="flex-1 flex items-center justify-center flex-col gap-3">
              <MessageSquare className="h-12 w-12 text-neutral-600" />
              <p className="text-neutral-500">Select a conversation to review</p>
              <p className="text-neutral-600 text-sm">Rate AI responses to improve future replies</p>
            </div>
          )}
        </Card>
      </div>

      <Dialog open={feedbackMsgId !== null} onOpenChange={() => setFeedbackMsgId(null)}>
        <DialogContent className="bg-neutral-900 border-neutral-800">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              {feedbackRating === "good" ? <ThumbsUp className="text-green-500" /> : <ThumbsDown className="text-red-500" />}
              {feedbackRating === "good" ? "Good Response" : "Needs Improvement"}
            </DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium text-neutral-300">Rating</label>
              <div className="flex gap-2 mt-1">
                <Button size="sm" variant={feedbackRating === "good" ? "default" : "outline"} className={feedbackRating === "good" ? "bg-green-700" : "border-neutral-700"} onClick={() => setFeedbackRating("good")}>
                  <ThumbsUp className="h-3 w-3 mr-1" /> Good
                </Button>
                <Button size="sm" variant={feedbackRating === "bad" ? "default" : "outline"} className={feedbackRating === "bad" ? "bg-red-700" : "border-neutral-700"} onClick={() => setFeedbackRating("bad")}>
                  <ThumbsDown className="h-3 w-3 mr-1" /> Bad
                </Button>
              </div>
            </div>
            <div>
              <label className="text-sm font-medium text-neutral-300">Note</label>
              <Input value={feedbackNote} onChange={(e) => setFeedbackNote(e.target.value)} placeholder="Why was this good/bad?" className="bg-neutral-800 border-neutral-700 mt-1" />
            </div>
            {feedbackRating === "bad" && (
              <div>
                <label className="text-sm font-medium text-neutral-300">Better response</label>
                <Textarea value={feedbackCorrected} onChange={(e) => setFeedbackCorrected(e.target.value)} placeholder="What should the AI have said?" rows={3} className="bg-neutral-800 border-neutral-700 mt-1" />
              </div>
            )}
            <Button onClick={submitFeedback} disabled={submitting} className="w-full bg-orange-600 hover:bg-orange-700">
              {submitting ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : null}
              Submit Feedback
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
