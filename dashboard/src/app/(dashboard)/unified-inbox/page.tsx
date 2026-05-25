'use client';

import { useState, useEffect, useCallback } from 'react';

interface Message {
  id: number;
  conversation_id: string;
  channel: string;
  direction: 'inbound' | 'outbound';
  body: string;
  media_url?: string;
  timestamp: string;
  status: string;
}

interface Conversation {
  id: string;
  contact_phone: string;
  contact_name: string;
  channel: string;
  status: string;
  last_message: string;
  last_message_at: string;
  unread_count: number;
  assigned_to: string;
  tags: string[];
}

interface InboxStats {
  total_conversations: number;
  active_conversations: number;
  total_unread: number;
  by_channel: Record<string, { total: number; unread: number }>;
  recent_messages: Message[];
}

const CHANNEL_ICONS: Record<string, string> = {
  whatsapp: '💬',
  instagram: '📷',
  facebook: '📘',
  tiktok: '🎵',
};

const CHANNEL_COLORS: Record<string, string> = {
  whatsapp: 'bg-green-600',
  instagram: 'bg-pink-600',
  facebook: 'bg-blue-600',
  tiktok: 'bg-black',
};

export default function UnifiedInbox() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [selectedConv, setSelectedConv] = useState<Conversation | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [stats, setStats] = useState<InboxStats | null>(null);
  const [replyText, setReplyText] = useState('');
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');
  const [search, setSearch] = useState('');

  const API = 'http://localhost:8701';

  // Load conversations
  const loadConversations = useCallback(async () => {
    try {
      const params = new URLSearchParams();
      if (filter !== 'all') params.set('channel', filter);
      if (search) params.set('search', search);

      const r = await fetch(`${API}/api/inbox/conversations?${params}`);
      const data = await r.json();
      setConversations(data.conversations || []);
    } catch (e) {
      console.error('Failed to load conversations', e);
    }
    setLoading(false);
  }, [filter, search]);

  // Load stats
  const loadStats = useCallback(async () => {
    try {
      const r = await fetch(`${API}/api/inbox/stats`);
      setStats(await r.json());
    } catch (e) {
      console.error('Failed to load stats', e);
    }
  }, []);

  useEffect(() => {
    loadConversations();
    loadStats();
    const interval = setInterval(() => {
      loadConversations();
      loadStats();
    }, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, [loadConversations, loadStats]);

  // Load messages for selected conversation
  const selectConversation = async (conv: Conversation) => {
    setSelectedConv(conv);
    conv.unread_count = 0;
    try {
      const r = await fetch(`${API}/api/inbox/conversations/${conv.contact_phone}`);
      const data = await r.json();
      setMessages(data.messages || []);
    } catch (e) {
      console.error('Failed to load messages', e);
    }
  };

  // Send reply
  const sendReply = async () => {
    if (!replyText.trim() || !selectedConv) return;

    try {
      const r = await fetch(`${API}/api/inbox/send`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          channel: selectedConv.channel,
          contact_phone: selectedConv.contact_phone,
          body: replyText,
        }),
      });
      const data = await r.json();

      if (data.sent) {
        // Add to messages
        setMessages(prev => [...prev, {
          id: Date.now(),
          conversation_id: selectedConv.id,
          channel: selectedConv.channel,
          direction: 'outbound',
          body: replyText,
          timestamp: new Date().toISOString(),
          status: 'sent',
        } as Message]);

        setReplyText('');
        selectedConv.last_message = replyText;
      }
    } catch (e) {
      console.error('Failed to send', e);
    }
  };

  // Mark conversation
  const updateStatus = async (conv: Conversation, status: string) => {
    await fetch(`${API}/api/inbox/conversations/${conv.contact_phone}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status }),
    });
    loadConversations();
  };

  return (
    <div className="flex h-[calc(100vh-4rem)] bg-neutral-950 text-neutral-100">
      {/* Sidebar: Conversation List */}
      <div className="w-80 border-r border-neutral-800 flex flex-col">
        {/* Stats Bar */}
        {stats && (
          <div className="p-3 border-b border-neutral-800 bg-neutral-900/50">
            <div className="flex justify-between text-xs text-neutral-400 mb-2">
              <span>{stats.total_conversations} total</span>
              {stats.total_unread > 0 && (
                <span className="text-green-400 font-bold">{stats.total_unread} unread</span>
              )}
            </div>
            <div className="flex gap-1">
              {Object.entries(stats.by_channel).map(([ch, info]) => (
                <button
                  key={ch}
                  onClick={() => setFilter(filter === ch ? 'all' : ch)}
                  className={`px-2 py-0.5 rounded text-xs flex items-center gap-1 ${
                    filter === ch ? 'bg-neutral-600 text-white' : 'bg-neutral-800 text-neutral-400'
                  }`}
                >
                  <span>{CHANNEL_ICONS[ch] || '📱'}</span>
                  <span>{info.unread}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Search */}
        <div className="p-2 border-b border-neutral-800">
          <input
            type="text"
            placeholder="Search conversations..."
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full bg-neutral-800 border border-neutral-700 rounded px-3 py-1.5 text-sm text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-neutral-600"
          />
        </div>

        {/* Conversation List */}
        <div className="flex-1 overflow-y-auto">
          {loading ? (
            <div className="p-4 text-center text-neutral-500 text-sm">Loading...</div>
          ) : conversations.length === 0 ? (
            <div className="p-8 text-center">
              <div className="text-4xl mb-3">📭</div>
              <div className="text-neutral-400 text-sm">No conversations yet</div>
              <div className="text-neutral-600 text-xs mt-1">Messages will appear here when customers reach out</div>
            </div>
          ) : (
            conversations.map(conv => (
              <div
                key={conv.id}
                onClick={() => selectConversation(conv)}
                className={`p-3 border-b border-neutral-800/50 cursor-pointer hover:bg-neutral-900 transition-colors ${
                  selectedConv?.id === conv.id ? 'bg-neutral-900 border-l-2 border-l-green-500' : ''
                } ${conv.unread_count > 0 ? 'bg-neutral-900/30' : ''}`}
              >
                <div className="flex items-start justify-between">
                  <div className="flex items-center gap-2 min-w-0">
                    <span className={`w-2 h-2 rounded-full flex-shrink-0 ${CHANNEL_COLORS[conv.channel] || 'bg-neutral-600'}`} />
                    <div className="min-w-0">
                      <div className="flex items-center gap-1.5">
                        <span className="text-sm font-medium truncate">
                          {conv.contact_name || conv.contact_phone}
                        </span>
                        {conv.unread_count > 0 && (
                          <span className="bg-green-500 text-black text-[10px] px-1.5 py-0.5 rounded-full font-bold">
                            {conv.unread_count}
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-neutral-500 truncate mt-0.5">{conv.last_message}</div>
                    </div>
                  </div>
                  <span className="text-[10px] text-neutral-600 flex-shrink-0 ml-2">
                    {conv.last_message_at ? new Date(conv.last_message_at).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' }) : ''}
                  </span>
                </div>

                {/* Tags */}
                {conv.tags && conv.tags.length > 0 && (
                  <div className="flex gap-1 mt-1.5">
                    {conv.tags.map((tag: string) => (
                      <span key={tag} className="text-[10px] bg-neutral-800 text-neutral-400 px-1.5 py-0.5 rounded">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </div>

      {/* Main: Chat View */}
      <div className="flex-1 flex flex-col">
        {selectedConv ? (
          <>
            {/* Chat Header */}
            <div className="p-3 border-b border-neutral-800 flex items-center justify-between bg-neutral-900/50">
              <div className="flex items-center gap-2">
                <span className="text-lg">{CHANNEL_ICONS[selectedConv.channel]}</span>
                <div>
                  <div className="text-sm font-medium">
                    {selectedConv.contact_name || selectedConv.contact_phone}
                  </div>
                  <div className="text-[10px] text-neutral-500">{selectedConv.channel}</div>
                </div>
              </div>
              <div className="flex gap-1">
                <button
                  onClick={() => updateStatus(selectedConv, 'closed')}
                  className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-neutral-700 text-neutral-400"
                >
                  Close
                </button>
                <button
                  onClick={() => updateStatus(selectedConv, 'spam')}
                  className="text-xs px-2 py-1 rounded bg-neutral-800 hover:bg-red-900/50 text-neutral-400 hover:text-red-400"
                >
                  Spam
                </button>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {messages.length === 0 ? (
                <div className="text-center text-neutral-500 text-sm py-8">No messages yet</div>
              ) : (
                messages.map(msg => (
                  <div
                    key={msg.id}
                    className={`flex ${msg.direction === 'outbound' ? 'justify-end' : 'justify-start'}`}
                  >
                    <div
                      className={`max-w-[70%] rounded-lg px-3 py-2 text-sm ${
                        msg.direction === 'outbound'
                          ? 'bg-green-600/20 text-green-100 border border-green-600/30'
                          : 'bg-neutral-800 text-neutral-200'
                      }`}
                    >
                      <div>{msg.body}</div>
                      <div className="text-[10px] text-neutral-500 mt-1 flex items-center gap-2">
                        {new Date(msg.timestamp).toLocaleTimeString('id-ID', { hour: '2-digit', minute: '2-digit' })}
                        {msg.direction === 'outbound' && (
                          <span className="text-neutral-600">
                            {msg.status === 'sent' ? '✓' : msg.status === 'delivered' ? '✓✓' : msg.status === 'read' ? '✓✓' : ''}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Reply Box */}
            <div className="p-3 border-t border-neutral-800 bg-neutral-900/50">
              <div className="flex gap-2">
                <input
                  type="text"
                  value={replyText}
                  onChange={e => setReplyText(e.target.value)}
                  onKeyDown={e => e.key === 'Enter' && sendReply()}
                  placeholder={`Reply via ${selectedConv.channel}...`}
                  className="flex-1 bg-neutral-800 border border-neutral-700 rounded px-3 py-2 text-sm text-neutral-200 placeholder-neutral-500 focus:outline-none focus:border-green-600"
                />
                <button
                  onClick={sendReply}
                  disabled={!replyText.trim()}
                  className="px-4 py-2 bg-green-600 hover:bg-green-500 disabled:bg-neutral-700 disabled:text-neutral-500 text-white rounded text-sm font-medium transition-colors"
                >
                  Send
                </button>
              </div>
            </div>
          </>
        ) : (
          <div className="flex-1 flex items-center justify-center">
            <div className="text-center">
              <div className="text-6xl mb-4">💬</div>
              <div className="text-lg text-neutral-400 font-medium mb-2">Unified Inbox</div>
              <div className="text-sm text-neutral-600 max-w-md">
                All your conversations in one place. Select a chat to start replying.
              </div>

              {/* Quick Stats */}
              {stats && (
                <div className="mt-6 grid grid-cols-3 gap-4 max-w-md mx-auto">
                  {Object.entries(stats.by_channel).map(([ch, info]) => (
                    <div key={ch} className="bg-neutral-900 rounded-lg p-3 text-center border border-neutral-800">
                      <div className="text-2xl">{CHANNEL_ICONS[ch]}</div>
                      <div className="text-lg font-bold mt-1 text-neutral-200">{info.total}</div>
                      <div className="text-[10px] text-neutral-500 capitalize">{ch}</div>
                      {info.unread > 0 && (
                        <div className="text-xs text-green-400 mt-1">{info.unread} unread</div>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
