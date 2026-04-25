"use client";

import { useState, useRef, useEffect, useMemo } from "react";
import useSWR from "swr";
import { fetcher, postJSON, fetchMessageLogs, fetchWahaHistory, sendMedia, fetchPresence, fetchTemplates, fetchTags, addTags, removeTag, type WANumber, type Conversation, type Message, type MessageLog, type WahaMessage, type Template, type Tag, type PresenceInfo } from "@/lib/api";
import { ContactProfilePanel } from "@/components/contact-profile-panel";
import { ProposalsTab } from "@/components/proposals-tab";
import { EmailTrackingPanel } from "@/components/email-tracking-panel";
import { LabelsFilter } from "@/components/labels-filter";
import { Activity, Paperclip, Zap, Tag as TagIcon, Loader2, ThumbsUp, ThumbsDown, MessageSquare, Bot, Hand, Play, Square, Phone, Search, ChevronDown, ChevronRight, X } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Dialog, DialogContent, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Send, User } from "lucide-react";

type Feedback = { id: number; message_id: number; rating: string; note: string; corrected_response: string };

export default function ConversationsPage() {
  const { data: waData, isLoading: waLoad } = useSWR<{ numbers: WANumber[] }>("/api/v1/agents/wa/sessions", fetcher);
  const [selectedConv, setSelectedConv] = useState<number | null>(null);
  const [replyText, setReplyText] = useState("");
  const [feedbackMsgId, setFeedbackMsgId] = useState<number | null>(null);
  const [feedbackRating, setFeedbackRating] = useState<"good" | "bad">("good");
  const [feedbackNote, setFeedbackNote] = useState("");
  const [feedbackCorrected, setFeedbackCorrected] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [collapsedGroups, setCollapsedGroups] = useState<Set<string>>(new Set());
  const [newChatOpen, setNewChatOpen] = useState(false);
  const [newChatPhone, setNewChatPhone] = useState("");
  const [newChatMsg, setNewChatMsg] = useState("");
  const [showLog, setShowLog] = useState(false);
  const { data: logData, mutate: mutateLogs } = useSWR<MessageLog[]>(
    showLog ? "/api/v1/conversations/logs?limit=50" : null,
    fetcher,
    { refreshInterval: 5000 }
  );
  const [newChatWA, setNewChatWA] = useState("");
  const [sendingNew, setSendingNew] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  // CRM Phase A state
  const [wahaHistory, setWahaHistory] = useState<WahaMessage[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [noMoreHistory, setNoMoreHistory] = useState(false);
  const [mediaFile, setMediaFile] = useState<File | null>(null);
  const [mediaPreview, setMediaPreview] = useState<string | null>(null);
  const [sendingMedia, setSendingMedia] = useState(false);
  const [presenceMap, setPresenceMap] = useState<Map<string, PresenceInfo>>(new Map());
  const [showTemplates, setShowTemplates] = useState(false);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [convTags, setConvTags] = useState<Tag[]>([]);
  const [newTag, setNewTag] = useState("");
  const [showTagInput, setShowTagInput] = useState(false);

  // Fetch ALL conversations across all WA numbers
  const { data: allConvData, mutate: mutateAllConv } = useSWR<{ conversations: Conversation[] }>(
    "/api/v1/conversations", fetcher, { refreshInterval: 5000 }
  );
  const { data: msgData, mutate: mutateMsgs } = useSWR<{ messages: Message[] }>(
    selectedConv ? `/api/v1/conversations/${selectedConv}/messages?limit=200` : null, fetcher, { refreshInterval: 3000 }
  );
  const { data: fbData } = useSWR<{ feedback: Feedback[] }>(
    selectedConv ? `/api/v1/conversations/${selectedConv}/feedback` : null, fetcher
  );

  const numbers = waData?.numbers ?? [];
  const allConversations = allConvData?.conversations ?? [];
  const messages = useMemo(() => msgData?.messages ?? [], [msgData?.messages]);
  const feedbackMap = new Map((fbData?.feedback ?? []).map((f) => [f.message_id, f]));

  const currentConv = allConversations.find((c) => c.id === selectedConv);
  const isManualMode = currentConv?.manual_mode === 1;

  // Build a map of wa_number_id -> number info for labels
  const numberMap = useMemo(() => {
    const m = new Map<string, WANumber>();
    numbers.forEach((n) => m.set(n.id, n));
    return m;
  }, [numbers]);

  // Group conversations by wa_number_id
  const groupedConversations = useMemo(() => {
    const groups = new Map<string, Conversation[]>();
    for (const conv of allConversations) {
      const waId = conv.wa_number_id || "unknown";
      if (!groups.has(waId)) groups.set(waId, []);
      groups.get(waId)!.push(conv);
    }
    // Sort groups: active WAs first per sidebar order
    const sorted = new Map<string, Conversation[]>();
    const waOrder = numbers.map((n) => n.id);
    for (const waId of waOrder) {
      if (groups.has(waId)) sorted.set(waId, groups.get(waId)!);
    }
    for (const [waId, convs] of groups) {
      if (!sorted.has(waId)) sorted.set(waId, convs);
    }
    return sorted;
  }, [allConversations, numbers]);

  // Filter conversations by search query
  const filteredGroups = useMemo(() => {
    if (!searchQuery.trim()) return groupedConversations;
    const q = searchQuery.toLowerCase();
    const filtered = new Map<string, Conversation[]>();
    for (const [waId, convs] of groupedConversations) {
      const matching = convs.filter((c) =>
        (c.contact_name || "").toLowerCase().includes(q) ||
        (c.contact_phone || "").toLowerCase().includes(q) ||
        (c.last_message_text || "").toLowerCase().includes(q)
      );
      if (matching.length > 0) filtered.set(waId, matching);
    }
    return filtered;
  }, [groupedConversations, searchQuery]);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages]);

  // Load presence for all WA sessions
  useEffect(() => {
    if (numbers.length === 0) return;
    const loadPresence = async () => {
      const newMap = new Map<string, PresenceInfo>();
      for (const n of numbers) {
        try {
          const data = await fetchPresence(n.session_name || n.id);
          for (const p of data.presences) {
            newMap.set(p.contact_phone, p);
          }
        } catch {}
      }
      setPresenceMap(newMap);
    };
    loadPresence();
    const interval = setInterval(loadPresence, 15000);
    return () => clearInterval(interval);
  }, [numbers]);

  // Load templates and tags when conversation changes
  useEffect(() => {
    if (!selectedConv) return;
    fetchTemplates().then((d) => setTemplates(d.templates || [])).catch(() => {});
    fetchTags(selectedConv).then((d) => setConvTags(d.tags || [])).catch(() => {});
    setWahaHistory([]);
    setNoMoreHistory(false);
  }, [selectedConv]);

  if (waLoad) {
    return <div className="p-6 flex items-center justify-center h-[50vh]"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  async function sendReply() {
    if (!selectedConv || !replyText.trim()) return;
    await postJSON(`/api/v1/conversations/${selectedConv}/messages`, { message: replyText });
    setReplyText("");
    mutateMsgs();
  }

  async function submitFeedback() {
    if (!selectedConv || !feedbackMsgId) return;
    setSubmitting(true);
    try {
      await postJSON(`/api/v1/conversations/${selectedConv}/feedback`, {
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
    await postJSON(`/api/v1/conversations/${selectedConv}/${endpoint}`, {});
    mutateMsgs();
  }

  async function stopConversation() {
    if (!selectedConv) return;
    if (!confirm("Stop this conversation? AI will stop responding to this customer.")) return;
    await postJSON(`/api/v1/conversations/${selectedConv}/stop`, {});
    mutateAllConv();
  }

  async function sendNewChat() {
    if (!newChatWA || !newChatPhone || !newChatMsg) return;
    setSendingNew(true);
    try {
      await postJSON("/api/v1/conversations/new", {
        wa_number_id: newChatWA,
        phone: newChatPhone.replace(/[^0-9]/g, ""),
        message: newChatMsg,
      });
      setNewChatOpen(false);
      setNewChatPhone("");
      setNewChatMsg("");
      mutateAllConv();
    } catch (e) {
      alert("Failed to send: " + e);
    } finally {
      setSendingNew(false);
    }
  }

  function toggleGroup(waId: string) {
    setCollapsedGroups((prev) => {
      const next = new Set(prev);
      if (next.has(waId)) next.delete(waId);
      else next.add(waId);
      return next;
    });
  }

  async function loadOlderMessages() {
    if (!selectedConv || loadingHistory || noMoreHistory) return;
    setLoadingHistory(true);
    try {
      const oldestTs = wahaHistory.length > 0 ? String(wahaHistory[0].timestamp) : undefined;
      const data = await fetchWahaHistory(selectedConv, 50, oldestTs);
      if (data.messages.length === 0) {
        setNoMoreHistory(true);
      } else {
        setWahaHistory((prev) => [...data.messages, ...prev]);
      }
    } catch (e) {
      console.error("Failed to load history:", e);
    } finally {
      setLoadingHistory(false);
    }
  }

  async function handleSendMedia() {
    if (!selectedConv || !mediaFile) return;
    setSendingMedia(true);
    try {
      const ext = mediaFile.name.split(".").pop()?.toLowerCase() || "";
      const typeMap: Record<string, string> = { jpg: "image", jpeg: "image", png: "image", gif: "image", webp: "image", mp4: "video", pdf: "document", doc: "document", docx: "document", ogg: "voice", mp3: "voice" };
      const mediaType = typeMap[ext] || "document";
      await sendMedia(selectedConv, mediaFile, mediaType, replyText || undefined);
      setMediaFile(null);
      setMediaPreview(null);
      setReplyText("");
      mutateMsgs();
    } catch (e) {
      alert("Failed to send media: " + e);
    } finally {
      setSendingMedia(false);
    }
  }

  function handleFileSelect(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    setMediaFile(file);
    if (file.type.startsWith("image/")) {
      const reader = new FileReader();
      reader.onload = (ev) => setMediaPreview(ev.target?.result as string);
      reader.readAsDataURL(file);
    } else {
      setMediaPreview(null);
    }
  }

  async function handleAddTag() {
    if (!selectedConv || !newTag.trim()) return;
    try {
      await addTags(selectedConv, [newTag.trim()]);
      setNewTag("");
      const data = await fetchTags(selectedConv);
      setConvTags(data.tags || []);
    } catch (e) {
      console.error("Failed to add tag:", e);
    }
  }

  async function handleRemoveTag(tag: string) {
    if (!selectedConv) return;
    try {
      await removeTag(selectedConv, tag);
      const data = await fetchTags(selectedConv);
      setConvTags(data.tags || []);
    } catch (e) {
      console.error("Failed to remove tag:", e);
    }
  }

  const statusColors: Record<string, string> = {
    active: "bg-green-700",
    stopped: "bg-red-700",
    escalated: "bg-yellow-700",
    completed: "bg-blue-700",
    new: "bg-neutral-600",
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold flex items-center gap-2">
          <MessageSquare className="h-6 w-6" />
          Chat Review
        </h1>
        <div className="flex gap-2 items-center">
          <Button onClick={() => setNewChatOpen(true)} className="bg-green-700 hover:bg-green-600">
            <Send className="h-4 w-4 mr-1" /> New Chat
          </Button>
          {selectedConv && (
            <>
              <Button onClick={stopConversation} variant="outline" className="border-red-800 text-red-400">
                <Square className="h-4 w-4 mr-1" /> Stop
              </Button>
              {isManualMode ? (
                <Button onClick={() => toggleTakeover(false)} variant="outline" className="border-green-700 text-green-400">
                  <Play className="h-4 w-4 mr-1" /> Return to AI
                </Button>
              ) : (
                <Button onClick={() => toggleTakeover(true)} variant="outline" className="border-orange-700 text-orange-400">
                  <Hand className="h-4 w-4 mr-1" /> Take Over
                </Button>
              )}
            </>
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
        {/* Left panel: Grouped conversation list */}
        <Card className="bg-neutral-900 border-neutral-800 overflow-hidden">
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm">Chats ({allConversations.length})</CardTitle>
            </div>
            <div className="relative mt-2">
              <Search className="absolute left-2.5 top-2.5 h-4 w-4 text-neutral-500" />
              <Input
                placeholder="Search conversations..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 h-8 bg-neutral-800 border-neutral-700 text-sm"
              />
            </div>
          </CardHeader>
          <CardContent className="p-0">
            <ScrollArea className="h-[calc(100vh-330px)]">
              {Array.from(filteredGroups.entries()).map(([waId, convs]) => {
                const numberInfo = numberMap.get(waId);
                const isCollapsed = collapsedGroups.has(waId);
                const label = numberInfo?.label || waId;
                const phone = numberInfo?.phone || "";

                return (
                  <div key={waId}>
                    {/* Group header */}
                    <button
                      onClick={() => toggleGroup(waId)}
                      className="w-full flex items-center gap-2 px-4 py-2 bg-neutral-800/80 border-b border-neutral-700 hover:bg-neutral-800 transition-colors sticky top-0 z-10"
                    >
                      {isCollapsed ? (
                        <ChevronRight className="h-3.5 w-3.5 text-neutral-400 shrink-0" />
                      ) : (
                        <ChevronDown className="h-3.5 w-3.5 text-neutral-400 shrink-0" />
                      )}
                      <Phone className="h-3.5 w-3.5 text-orange-400 shrink-0" />
                      <span className="font-semibold text-sm text-neutral-200 truncate">{label}</span>
                      {phone && <span className="text-xs text-neutral-500 truncate">{phone}</span>}
                      <Badge variant="secondary" className="text-xs bg-neutral-700 ml-auto shrink-0">{convs.length}</Badge>
                    </button>

                    {/* Conversation items */}
                    {!isCollapsed && convs.map((conv) => {
                      const lastMsg = conv.last_message_text || conv.contact_phone;
                      const hasManual = conv.manual_mode === 1;
                      const presInfo = presenceMap.get(conv.contact_phone);
                      const presColor = presInfo?.status === "online" ? "bg-green-500" : presInfo?.status === "composing" ? "bg-yellow-500" : "bg-neutral-600";
                      const convTagsForConv = selectedConv === conv.id ? convTags : [];
                      return (
                        <button
                          key={conv.id}
                          onClick={() => setSelectedConv(conv.id)}
                          className={`w-full text-left px-4 py-2.5 border-b border-neutral-800/50 hover:bg-neutral-800/50 transition-colors pl-6 ${selectedConv === conv.id ? "bg-orange-500/10 border-l-2 border-l-orange-500" : ""}`}
                        >
                          <div className="flex items-center justify-between">
                            <span className="font-medium text-sm truncate max-w-[140px] flex items-center gap-1.5">
                              <span className={`w-2 h-2 rounded-full shrink-0 ${presColor}`} title={presInfo?.status === "online" ? "Online" : presInfo?.status === "composing" ? "Typing..." : presInfo?.last_seen_at ? `Last seen ${new Date(presInfo.last_seen_at).toLocaleString()}` : "Offline"} />
                              {conv.contact_name || conv.contact_phone?.replace("@c.us", "").replace("@lid", "🔒")}
                            </span>
                            <div className="flex gap-1">
                              {hasManual && <Badge className="text-xs bg-orange-700">Admin</Badge>}
                              <Badge variant="secondary" className={`text-xs ${statusColors[conv.status ?? ""] || "bg-neutral-700"}`}>{conv.status || "unknown"}</Badge>
                            </div>
                          </div>
                          <p className="text-xs text-neutral-500 mt-0.5 truncate">{lastMsg}</p>
                          {convTagsForConv.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-1">
                              {convTagsForConv.map((t) => (
                                <span key={t.id} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-xs rounded-full bg-neutral-700 text-neutral-300">
                                  {t.tag}
                                  <button onClick={(e) => { e.stopPropagation(); handleRemoveTag(t.tag); }} className="hover:text-red-400 ml-0.5"><X className="h-2.5 w-2.5" /></button>
                                </span>
                              ))}
                            </div>
                          )}
                        </button>
                      );
                    })}
                  </div>
                );
              })}
              {allConversations.length === 0 && <p className="text-neutral-500 text-center py-8 text-sm">No conversations</p>}
            </ScrollArea>
          </CardContent>
        </Card>

        {/* Right panel: Message view */}
        <Card className="lg:col-span-2 bg-neutral-900 border-neutral-800 flex flex-col">
          {selectedConv ? (
            <>
              <CardHeader className="pb-2 border-b border-neutral-800">
                <CardTitle className="text-sm flex items-center gap-3">
                  <User className="h-4 w-4" />
                  <span>{currentConv?.contact_name || currentConv?.contact_phone?.replace("@c.us", "")}</span>
                  {currentConv?.contact_phone && (
                    <span className="text-neutral-500 text-xs">{currentConv.contact_phone.replace("@c.us", "")}</span>
                  )}
                  {currentConv?.wa_number_id && (
                    <Badge variant="secondary" className="text-xs bg-orange-700/30 text-orange-300 ml-1">
                      {numberMap.get(currentConv.wa_number_id)?.label || currentConv.wa_number_id}
                    </Badge>
                  )}
                </CardTitle>
              </CardHeader>
              <CardContent className="flex-1 p-0 overflow-hidden">
                <ScrollArea className="h-[calc(100vh-370px)] p-4">
                  <div ref={scrollRef} className="space-y-3">
                    {/* Load older messages button */}
                    {selectedConv && (
                      <div className="text-center py-2">
                        {loadingHistory ? (
                          <Loader2 className="h-4 w-4 animate-spin mx-auto text-neutral-500" />
                        ) : noMoreHistory ? (
                          <p className="text-xs text-neutral-600">No more messages</p>
                        ) : (
                          <button onClick={loadOlderMessages} className="text-xs text-orange-400 hover:text-orange-300 underline">
                            Load older messages
                          </button>
                        )}
                      </div>
                    )}
                    {/* WAHA history messages */}
                    {wahaHistory.map((msg) => (
                      <div key={`waha-${msg.id}`} className={`flex ${msg.direction === "out" ? "justify-end" : "justify-start"}`}>
                        <div className={`max-w-[75%] rounded-lg px-3 py-2 text-sm ${msg.direction === "out" ? "bg-orange-600 text-white" : "bg-neutral-800 text-neutral-200"}`}>
                          <p className="whitespace-pre-wrap">{msg.text}</p>
                          <p className="text-xs opacity-50 mt-1">{msg.type !== "chat" ? `[${msg.type}]` : ""} {new Date(msg.timestamp * 1000).toLocaleTimeString().slice(0, 5)}</p>
                        </div>
                      </div>
                    ))}
                    {/* Local messages */}
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
              <div className="p-3 border-t border-neutral-800">
                {/* Tags for selected conversation */}
                {selectedConv && convTags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-2">
                    {convTags.map((t) => (
                      <span key={t.id} className="inline-flex items-center gap-0.5 px-1.5 py-0.5 text-xs rounded-full bg-neutral-700 text-neutral-300">
                        {t.tag}
                        <button onClick={() => handleRemoveTag(t.tag)} className="hover:text-red-400 ml-0.5"><X className="h-2.5 w-2.5" /></button>
                      </span>
                    ))}
                  </div>
                )}
                {/* Add tag input */}
                {selectedConv && showTagInput && (
                  <div className="flex gap-1 mb-2">
                    <Input value={newTag} onChange={(e) => setNewTag(e.target.value)} onKeyDown={(e) => e.key === "Enter" && handleAddTag()} placeholder="Add tag..." className="h-7 text-xs bg-neutral-800 border-neutral-700" />
                    <Button size="sm" onClick={handleAddTag} className="h-7 bg-orange-600 hover:bg-orange-700 text-xs">Add</Button>
                  </div>
                )}
                {/* Media preview */}
                {mediaPreview && (
                  <div className="mb-2 relative">
                    <img src={mediaPreview} alt="Preview" className="h-20 rounded border border-neutral-700" />
                    <button onClick={() => { setMediaFile(null); setMediaPreview(null); }} className="absolute top-1 right-1 bg-neutral-800 rounded-full p-0.5 hover:bg-red-800"><X className="h-3 w-3" /></button>
                  </div>
                )}
                {mediaFile && !mediaPreview && (
                  <div className="mb-2 text-xs text-neutral-400 flex items-center gap-1">
                    <Paperclip className="h-3 w-3" /> {mediaFile.name}
                    <button onClick={() => { setMediaFile(null); }} className="hover:text-red-400"><X className="h-3 w-3" /></button>
                  </div>
                )}
                {/* Template picker dropdown */}
                {showTemplates && (
                  <div className="mb-2 bg-neutral-800 border border-neutral-700 rounded-lg max-h-40 overflow-y-auto">
                    {templates.length === 0 ? (
                      <p className="text-xs text-neutral-500 p-2">No templates</p>
                    ) : (
                      templates.map((t) => (
                        <button key={t.id} onClick={() => { setReplyText(t.content); setShowTemplates(false); }} className="w-full text-left px-3 py-2 hover:bg-neutral-700 border-b border-neutral-700/50 last:border-0">
                          <span className="text-xs text-orange-400 font-medium">{t.name}</span>
                          <span className="text-xs text-neutral-500 ml-2">{t.category}</span>
                          <p className="text-xs text-neutral-400 truncate">{t.content}</p>
                        </button>
                      ))
                    )}
                  </div>
                )}
                {/* Reply input row */}
                <div className="flex gap-2 items-center">
                  <button onClick={() => setShowTagInput(!showTagInput)} className="p-2 rounded hover:bg-neutral-800 text-neutral-400 hover:text-orange-400" title="Add tag"><TagIcon className="h-4 w-4" /></button>
                  <button onClick={() => setShowTemplates(!showTemplates)} className="p-2 rounded hover:bg-neutral-800 text-neutral-400 hover:text-yellow-400" title="Quick reply templates"><Zap className="h-4 w-4" /></button>
                  <label className="p-2 rounded hover:bg-neutral-800 text-neutral-400 hover:text-blue-400 cursor-pointer" title="Attach file">
                    <Paperclip className="h-4 w-4" />
                    <input type="file" accept="image/*,video/*,.pdf,.doc,.docx,.ogg,.mp3" className="hidden" onChange={handleFileSelect} />
                  </label>
                  <Input
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && !mediaFile && sendReply()}
                    placeholder={isManualMode ? "Reply as admin..." : "Reply..."}
                    className="flex-1 bg-neutral-800 border-neutral-700"
                  />
                  <Button onClick={mediaFile ? handleSendMedia : sendReply} disabled={sendingMedia} size="icon" className="bg-orange-600 hover:bg-orange-700">
                    {sendingMedia ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </div>
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

      {/* Activity Log */}
      <div className="mt-4">
        <Button variant="outline" size="sm" onClick={() => { setShowLog(!showLog); if (!showLog) mutateLogs(); }} className="border-neutral-700 text-neutral-400 hover:text-white">
          <Activity className="h-4 w-4 mr-1" /> {showLog ? "Hide Activity Log" : "Show Activity Log"}
        </Button>
        {showLog && (
          <Card className="mt-2 bg-neutral-900 border-neutral-800">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm text-neutral-300">Message Activity Log</CardTitle>
            </CardHeader>
            <CardContent className="max-h-64 overflow-y-auto">
              {(logData as any)?.logs?.length ? (
                <div className="space-y-1 font-mono text-xs">
                  {(logData as any).logs.map((log: MessageLog, i: number) => (
                    <div key={i} className={`px-2 py-1 rounded ${log.priority === "3" ? "bg-red-900/30 text-red-300" : log.priority === "4" ? "bg-yellow-900/30 text-yellow-300" : "bg-neutral-800 text-neutral-400"}`}>
                      <span className="text-neutral-600">{log.timestamp ? new Date(Number(log.timestamp) / 1000).toLocaleTimeString() : ""}</span>{" "}
                      {log.message}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="text-neutral-500 text-xs">No activity logged yet. Send a message to see logs.</p>
              )}
            </CardContent>
          </Card>
        )}
      </div>

      {/* New Chat Dialog */}
      <Dialog open={newChatOpen} onOpenChange={setNewChatOpen}>
        <DialogContent className="bg-neutral-900 border-neutral-800">
          <DialogHeader>
            <DialogTitle>Start New Conversation</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className="text-sm font-medium text-neutral-300">WA Number</label>
              <select
                value={newChatWA}
                onChange={(e) => setNewChatWA(e.target.value)}
                className="w-full mt-1 bg-neutral-800 border border-neutral-700 rounded-md px-3 py-2 text-sm text-neutral-200"
              >
                <option value="">Select WA number...</option>
                {numbers.map((n) => (
                  <option key={n.id} value={n.id}>{n.label} ({n.phone})</option>
                ))}
              </select>
            </div>
            <div>
              <label className="text-sm font-medium text-neutral-300">Phone Number</label>
              <Input
                value={newChatPhone}
                onChange={(e) => setNewChatPhone(e.target.value)}
                placeholder="6281234567890"
                className="bg-neutral-800 border-neutral-700 mt-1"
              />
            </div>
            <div>
              <label className="text-sm font-medium text-neutral-300">Message</label>
              <Textarea
                value={newChatMsg}
                onChange={(e) => setNewChatMsg(e.target.value)}
                placeholder="Type your message..."
                rows={3}
                className="bg-neutral-800 border-neutral-700 mt-1"
              />
            </div>
            <Button onClick={sendNewChat} disabled={sendingNew || !newChatWA || !newChatPhone || !newChatMsg} className="w-full bg-orange-600 hover:bg-orange-700">
              {sendingNew ? <Loader2 className="h-4 w-4 animate-spin mr-2" /> : <Send className="h-4 w-4 mr-2" />}
              Send Message
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Feedback Dialog */}
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
