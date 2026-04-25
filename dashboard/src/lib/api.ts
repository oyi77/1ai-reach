export const API_BASE = "";

export interface AnalyticsData {
  kpis: {
    total_leads: number;
    full_funnel_conversion: number;
    reply_rate: number;
    avg_lead_score: number;
    leads_this_week: number;
    pipeline_active: number;
  };
  conversion_rates: {
    new_to_enriched: number;
    enriched_to_draft: number;
    draft_to_reviewed: number;
    reviewed_to_contacted: number;
    contacted_to_replied: number;
    replied_to_meeting: number;
    meeting_to_won: number;
    full_funnel: number;
  };
  funnel_counts: Record<string, number>;
  channel_email: {
    sent: number;
    delivered: number;
    opened: number;
    clicked: number;
    bounced: number;
    delivery_rate: number;
    open_rate: number;
    click_rate: number;
    bounce_rate: number;
  };
  channel_wa: {
    sent: number;
    replied: number;
    reply_rate: number;
  };
  velocity: {
    leads_this_week: number;
    leads_this_month: number;
    avg_days_to_contact: number | null;
  };
  industry_performance: Array<{
    industry: string;
    leads: number;
    contacted: number;
    replied: number;
    converted: number;
    reply_rate: number;
    conversion_rate: number;
  }>;
  tier_stats: Record<string, { count: number; replied: number; reply_rate: number }>;
  score_histogram: Record<string, number>;
  service_performance: Array<{
    service: string;
    total: number;
    contacted: number;
    replied: number;
    reply_rate: number;
  }>;
}

export interface FunnelData {
  counts: Record<string, number>;
  total: number;
}

export interface Lead {
  id: string;
  displayName?: string;
  company_name?: string;
  contact_name?: string;
  email?: string;
  phone?: string;
  website?: string;
  websiteUri?: string;
  status: string;
  vertical?: string;
  primaryType?: string;
  formattedAddress?: string;
  created_at?: string;
  updated_at?: string;
  [key: string]: unknown;
}

export interface Contact {
  id: number;
  wa_number_id?: string;
  name: string;
  phone: string;
  email?: string;
  company?: string;
  notes?: string;
  tags?: string;
  source?: string;
  created_at?: string;
  updated_at?: string;
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
  voice_enabled?: number;
  voice_reply_mode?: string;
  voice_language?: string;
}

export interface VoiceConfig {
  voice_enabled: boolean;
  voice_reply_mode: string;
  voice_language: string;
}

export interface KBEntry {
  id: number;
  wa_number_id: string;
  question: string;
  answer: string;
  category: string;
  tags?: string;
  content?: string;
  priority?: number;
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
  last_message_text?: string;
  last_message_at?: string;
  created_at?: string;
  updated_at?: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  message_text: string;
  direction: "in" | "out";
  message_type?: string;
  timestamp?: string;
  waha_message_id?: string;
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

// Product Management Types
export type ProductStatus = "active" | "inactive" | "discontinued" | "draft";
export type VisibilityStatus = "public" | "private" | "hidden";
export type InventoryReason = "purchase" | "sale" | "return" | "adjustment" | "damage" | "restock";

export interface Product {
  id?: string;
  wa_number_id: string;
  name: string;
  description?: string;
  category: string;
  base_price_cents: number;
  currency: string;
  sku: string;
  status: ProductStatus;
  visibility: VisibilityStatus;
  image_url?: string;
  created_at?: string;
  updated_at?: string;
}

export interface ProductVariant {
  id?: string;
  product_id: string;
  sku: string;
  variant_name: string;
  price_cents: number;
  weight_grams?: number;
  dimensions_json?: string;
  status: ProductStatus;
  created_at?: string;
  updated_at?: string;
}

export interface Inventory {
  id?: string;
  variant_id: string;
  on_hand: number;
  reserved: number;
  sold: number;
  reorder_level: number;
  created_at?: string;
  updated_at?: string;
}

export interface ProductOverride {
  id?: string;
  wa_number_id: string;
  product_id: string;
  override_price_cents?: number;
  override_stock_quantity?: number;
  is_hidden: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface ProductImage {
  id?: string;
  product_id: string;
  image_url: string;
  alt_text?: string;
  display_order: number;
  is_primary: boolean;
  created_at?: string;
  updated_at?: string;
}

export interface VariantOption {
  id?: string;
  variant_id: string;
  option_name: string;
  option_value: string;
  created_at?: string;
  updated_at?: string;
}

// Product API Functions
export async function fetchProducts(wa_number_id: string): Promise<Product[]> {
  return fetcher<Product[]>(`/api/v1/products?wa_number_id=${wa_number_id}`);
}

export async function createProduct(product: Omit<Product, "id" | "created_at" | "updated_at">): Promise<Product> {
  return postJSON<Product>("/api/v1/products", product);
}

export async function updateProduct(id: string, updates: Partial<Product>): Promise<Product> {
  return patchJSON<Product>(`/api/v1/products/${id}`, updates);
}

export async function deleteProduct(id: string): Promise<void> {
  await deleteJSON(`/api/v1/products/${id}`);
}

export async function fetchProductVariants(product_id: string): Promise<ProductVariant[]> {
  return fetcher<ProductVariant[]>(`/api/v1/products/${product_id}/variants`);
}

export async function createProductVariant(variant: Omit<ProductVariant, "id" | "created_at" | "updated_at">): Promise<ProductVariant> {
  return postJSON<ProductVariant>("/api/v1/variants", variant);
}

export async function fetchInventory(variant_id: string): Promise<Inventory> {
  return fetcher<Inventory>(`/api/v1/inventory/${variant_id}`);
}

export async function updateInventory(variant_id: string, updates: Partial<Inventory>): Promise<Inventory> {
  return patchJSON<Inventory>(`/api/v1/inventory/${variant_id}`, updates);
}

export async function uploadImage(product_id: string, file: File, alt_text?: string): Promise<ProductImage> {
  const formData = new FormData();
  formData.append("file", file);
  if (alt_text) formData.append("alt_text", alt_text);

  const res = await fetch(`/api/v1/products/${product_id}/images`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function importCSV(wa_number_id: string, file: File): Promise<{ imported: number; errors: string[] }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("wa_number_id", wa_number_id);

  const res = await fetch(`${API_BASE}/api/v1/products/import`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function fetcher<T>(url: string): Promise<T> {
  const res = await fetch(`${API_BASE}${url}`);
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  const json = await res.json();
  // Unwrap standardized API responses with {status, message, data} structure
  if (json.status && json.data !== undefined) {
    return json.data;
  }
  return json;
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

export interface MessageLog {
  timestamp: string;
  message: string;
  priority: string;
}

export async function fetchMessageLogs(limit = 50, direction?: string, session?: string): Promise<{ logs: MessageLog[]; count: number }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (direction) params.set("direction", direction);
  if (session) params.set("session", session);
  return fetcher(`/api/v1/conversations/logs?${params}`);
}

export async function fetchContacts(search?: string, limit = 50, offset = 0): Promise<{ contacts: Contact[]; total: number }> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  if (search) params.set("search", search);
  return fetcher<{ contacts: Contact[]; total: number }>(`/api/v1/contacts?${params}`);
}

export async function createContact(contact: Omit<Contact, "id">): Promise<{ contact: Contact }> {
  return postJSON<{ contact: Contact }>("/api/v1/contacts", contact);
}

export async function updateContact(id: number, updates: Partial<Contact>): Promise<{ contact: Contact }> {
  return patchJSON<{ contact: Contact }>(`/api/v1/contacts/${id}`, updates);
}

export async function deleteContact(id: number): Promise<void> {
  await deleteJSON(`/api/v1/contacts/${id}`);
}

export async function importContacts(file: File): Promise<{ imported: number; duplicates: number; errors: string[] }> {
  const formData = new FormData();
  formData.append("file", file);
  const res = await fetch(`${API_BASE}/api/v1/contacts/import-csv`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export interface WAHAServer {
  id: number;
  label: string;
  url: string;
  api_key: string;
  is_default: number;
  created_at?: string;
  updated_at?: string;
}

export interface TestResult {
  success: boolean;
  message: string;
  sessions_count: number;
}

export async function fetchWAHAServers(): Promise<WAHAServer[]> {
  const data = await fetcher<{ servers: WAHAServer[] }>("/api/v1/settings/waha-servers");
  return data.servers;
}

export async function createWAHAServer(server: Omit<WAHAServer, "id" | "created_at" | "updated_at">): Promise<WAHAServer> {
  const data = await postJSON<{ server: WAHAServer }>("/api/v1/settings/waha-servers", server);
  return data.server;
}

export async function updateWAHAServer(id: number, updates: Partial<WAHAServer>): Promise<WAHAServer> {
  const data = await patchJSON<{ server: WAHAServer }>(`/api/v1/settings/waha-servers/${id}`, updates);
  return data.server;
}

export async function deleteWAHAServer(id: number): Promise<void> {
  await deleteJSON(`/api/v1/settings/waha-servers/${id}`);
}

export async function testWAHAServer(id: number): Promise<TestResult> {
  const data = await postJSON<TestResult>(`/api/v1/settings/waha-servers/${id}/test`, {});
   return data;
}

// CRM Phase A types and API functions

export interface WahaMessage {
  id: string;
  direction: "in" | "out";
  text: string;
  timestamp: number;
  from_waha: boolean;
  type: string;
}

export interface Template {
  id: number;
  wa_number_id: string | null;
  name: string;
  content: string;
  category: string;
  created_at?: string;
  updated_at?: string;
}

export interface Tag {
  id: number;
  tag: string;
  created_at?: string;
}

export interface PresenceInfo {
  contact_phone: string;
  status: string;
  last_seen_at: string | null;
  updated_at?: string;
}

export async function fetchWahaHistory(conversationId: number, limit = 50, before?: string): Promise<{ messages: WahaMessage[]; count: number }> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (before) params.set("before", before);
  return fetcher(`/api/v1/conversations/${conversationId}/waha-history?${params}`);
}

export async function sendMedia(conversationId: number, file: File, type: string, caption?: string): Promise<{ message_id: string; media_type: string; file_name: string }> {
  const formData = new FormData();
  formData.append("file", file);
  formData.append("type", type);
  if (caption) formData.append("caption", caption);
  const res = await fetch(`${API_BASE}/api/v1/conversations/${conversationId}/send-media`, {
    method: "POST",
    body: formData,
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  const json = await res.json();
  return json.data || json;
}

export async function fetchPresence(session: string): Promise<{ presences: PresenceInfo[] }> {
  return fetcher(`/api/v1/presence/${session}`);
}

export async function fetchTemplates(waNumberId?: string): Promise<{ templates: Template[] }> {
  const params = waNumberId ? `?wa_number_id=${waNumberId}` : "";
  return fetcher(`/api/v1/templates${params}`);
}

export async function fetchTags(conversationId: number): Promise<{ tags: Tag[] }> {
  return fetcher(`/api/v1/conversations/${conversationId}/tags`);
}

export async function addTags(conversationId: number, tags: string[]): Promise<{ added: string[] }> {
  return postJSON(`/api/v1/conversations/${conversationId}/tags`, { tags });
}

export async function removeTag(conversationId: number, tag: string): Promise<{ removed: string }> {
  const res = await fetch(`${API_BASE}/api/v1/conversations/${conversationId}/tags/${encodeURIComponent(tag)}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}



export interface ContactProfile {
  id: number;
  contact_id: number;
  wa_number_id: string;
  profile_photo_url: string | null;
  status: string | null;
  is_business: boolean;
  business_name: string | null;
  business_description: string | null;
  address: string | null;
  website: string | null;
  birthday: string | null;
  custom_fields: string | null;
  created_at: string;
  updated_at: string;
}

export interface ContactWithProfile {
  contact: Contact;
  profile: ContactProfile | null;
}

export async function fetchContactProfile(contactId: number): Promise<ContactWithProfile> {
  return fetcher(`/api/v1/contacts/${contactId}/profile`);
}

export async function updateContactProfile(contactId: number, data: Partial<ContactProfile>): Promise<ContactWithProfile> {
  return putJSON(`/api/v1/contacts/${contactId}/profile`, data);
}

export interface Proposal {
  id: number;
  contact_id: number;
  conversation_id: number | null;
  wa_number_id: string | null;
  lead_id: string | null;
  title: string;
  content: string;
  status: string;
  score: number | null;
  reviewed: boolean;
  reviewed_at: string | null;
  review_notes: string | null;
  sent_at: string | null;
  accepted_at: string | null;
  rejected_at: string | null;
  expires_at: string | null;
  sent_count: number;
  opened_count: number;
  clicked_count: number;
  value_cents: number | null;
  currency: string;
  created_at: string;
  updated_at: string;
}

export async function fetchContactProposals(contactId: number, status?: string): Promise<{ proposals: Proposal[]; total: number }> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  return fetcher(`/api/v1/contacts/${contactId}/proposals${params}`);
}

export async function fetchConversationProposals(conversationId: number, status?: string): Promise<{ proposals: Proposal[]; total: number }> {
  const params = status ? `?status=${encodeURIComponent(status)}` : "";
  return fetcher(`/api/v1/conversations/${conversationId}/proposals${params}`);
}

export async function createProposal(contactId: number, data: { title: string; content: string; conversation_id?: number; lead_id?: string; value_cents?: number; currency?: string }): Promise<{ proposal: Proposal }> {
  return postJSON(`/api/v1/contacts/${contactId}/proposals`, data);
}

export async function updateProposal(proposalId: number, data: Partial<Proposal>): Promise<{ proposal: Proposal }> {
  return patchJSON(`/api/v1/proposals/${proposalId}`, data);
}

export async function deleteProposal(proposalId: number): Promise<{ status: string; proposal_id: number }> {
  const res = await fetch(`${API_BASE}/api/v1/proposals/${proposalId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export interface EmailEvent {
  id: number;
  contact_id: number | null;
  conversation_id: number | null;
  lead_id: string | null;
  wa_number_id: string | null;
  event_type: string;
  email: string;
  subject: string | null;
  message_id: string | null;
  provider: string;
  provider_event_id: string | null;
  ip_address: string | null;
  user_agent: string | null;
  link_clicked: string | null;
  bounce_reason: string | null;
  timestamp: string;
  created_at: string;
}

export interface EmailStats {
  total_sent: number;
  total_delivered: number;
  total_opened: number;
  total_clicked: number;
  total_bounced: number;
  open_rate: number;
  click_rate: number;
  delivery_rate: number;
  last_event_at: string | null;
}

export async function fetchConversationEmails(conversationId: number): Promise<{ events: EmailEvent[]; total: number }> {
  return fetcher(`/api/v1/conversations/${conversationId}/emails`);
}

export async function fetchConversationEmailStats(conversationId: number): Promise<EmailStats> {
  return fetcher(`/api/v1/conversations/${conversationId}/emails/stats`);
}

export interface WahaLabel {
  id: number;
  wa_number_id: string;
  waha_label_id: string;
  name: string;
  color: string | null;
  is_predefined: boolean;
  is_active: boolean;
}

export async function fetchWahaLabels(waNumberId: string): Promise<{ labels: WahaLabel[] }> {
  return fetcher(`/api/v1/waha/${waNumberId}/labels`);
}

export async function createWahaLabel(waNumberId: string, data: { name: string; color?: string }): Promise<{ label: WahaLabel }> {
  return postJSON(`/api/v1/waha/${waNumberId}/labels`, data);
}

export async function updateWahaLabel(waNumberId: string, labelId: number, data: Partial<WahaLabel>): Promise<{ label: WahaLabel }> {
  return patchJSON(`/api/v1/waha/${waNumberId}/labels/${labelId}`, data);
}

export async function deleteWahaLabel(waNumberId: string, labelId: number): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/v1/waha/${waNumberId}/labels/${labelId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

export async function fetchConversationLabels(conversationId: number): Promise<{ labels: WahaLabel[] }> {
  return fetcher(`/api/v1/conversations/${conversationId}/labels`);
}

export async function assignLabelToConversation(conversationId: number, labelId: number, assignedBy?: string): Promise<{ status: string }> {
  return postJSON(`/api/v1/conversations/${conversationId}/labels/${labelId}`, { assigned_by: assignedBy });
}

export async function removeLabelFromConversation(conversationId: number, labelId: number): Promise<{ status: string }> {
  const res = await fetch(`${API_BASE}/api/v1/conversations/${conversationId}/labels/${labelId}`, { method: "DELETE" });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}

async function putJSON(url: string, body: object) {
  const res = await fetch(`${API_BASE}${url}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`API ${res.status}: ${res.statusText}`);
  return res.json();
}
