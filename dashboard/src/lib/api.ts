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

  const res = await fetch(`${API_BASE}/api/v1/products/${product_id}/images`, {
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
