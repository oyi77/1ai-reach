export const API_BASE = "";

export interface FunnelData {
  counts: Record<string, number>;
  total: number;
}

export interface Lead {
  id: string;
  company_name?: string;
  contact_name?: string;
  email?: string;
  phone?: string;
  website?: string;
  status: string;
  vertical?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface WANumber {
  id: string;
  session_name: string;
  label: string;
  phone: string;
  mode: string;
  status: string;
  persona?: string;
  auto_reply: number;
  kb_enabled: number;
  webhook_url?: string;
  created_at?: string;
  updated_at?: string;
}

export interface KBEntry {
  id: number;
  wa_number_id: string;
  question: string;
  answer: string;
  category: string;
  keywords?: string;
  enabled?: number;
  created_at?: string;
  updated_at?: string;
}

export interface Conversation {
  id: number;
  wa_number_id: string;
  contact_phone: string;
  contact_name?: string;
  stage: string;
  status?: string;
  manual_mode?: number;
  created_at?: string;
  updated_at?: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  message_text: string;
  direction: "inbound" | "outbound";
  source?: string;
  created_at?: string;
}

export interface ServiceStatus {
  key: string;
  label: string;
  running: boolean;
  pid: number | null;
  port?: number;
}

export interface EventLog {
  id: number;
  lead_id?: string;
  event_type: string;
  details?: string;
  timestamp?: string;
  created_at?: string;
}

export interface PipelineScript {
  key: string;
  script: string;
}

export async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function postJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function patchJSON<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function deleteJSON<T>(url: string): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}
