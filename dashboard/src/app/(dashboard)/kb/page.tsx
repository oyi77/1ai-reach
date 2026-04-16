"use client";

import { useState } from "react";
import useSWR from "swr";
import { fetcher, postJSON, patchJSON, deleteJSON, type WANumber, type KBEntry } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Plus, Pencil, Trash2, Loader2, Upload } from "lucide-react";

export default function KBPage() {
  const { data: waData, isLoading: waLoad } = useSWR<{ numbers: WANumber[] }>("/api/wa-numbers", fetcher);
  const [selectedWA, setSelectedWA] = useState<string>("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState({ question: "", answer: "", category: "faq", tags: "" });
  const [importing, setImporting] = useState(false);

  const waId = selectedWA || waData?.numbers[0]?.id || "";
  const { data: kbData, mutate } = useSWR<{ entries: KBEntry[]; count: number }>(
    waId ? `/api/kb/${waId}` : null, fetcher
  );
  const entries = kbData?.entries ?? [];

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !waId) return;
    
    setImporting(true);
    const formData = new FormData();
    formData.append("file", file);
    formData.append("wa_number_id", waId);
    
    try {
      const res = await fetch("/api/kb/import", { method: "POST", body: formData });
      const data = await res.json();
      if (data.success) {
        alert(`✓ Imported ${data.count} entries`);
        mutate();
      } else {
        alert(`✗ Import failed: ${data.error}`);
      }
    } catch (error) {
      alert(`✗ Import error: ${error}`);
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  }

  function handleExport(format: string | null) {
    if (!waId || !format) return;
    window.open(`/api/kb/export?wa_number_id=${waId}&format=${format}`, "_blank");
  }

  if (waLoad) {
    return <div className="p-6 flex items-center justify-center h-[50vh]"><Loader2 className="h-8 w-8 animate-spin text-orange-500" /></div>;
  }

  function openAdd() {
    setEditId(null);
    setForm({ question: "", answer: "", category: "faq", tags: "" });
    setDialogOpen(true);
  }

  function openEdit(entry: KBEntry) {
    setEditId(entry.id);
    setForm({ question: entry.question, answer: entry.answer, category: entry.category, tags: entry.tags || "" });
    setDialogOpen(true);
  }

  async function saveEntry() {
    if (!waId || !form.question || !form.answer) return;
    if (editId) {
      await patchJSON(`/api/kb/entry/${editId}`, form);
    } else {
      await postJSON(`/api/kb/${waId}`, form);
    }
    setDialogOpen(false);
    mutate();
  }

  async function deleteEntry(id: number) {
    await deleteJSON(`/api/kb/entry/${id}`);
    mutate();
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Knowledge Base</h1>
        <div className="flex gap-2">
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
          
          <input type="file" id="kb-import" accept=".txt,.csv,.json,.md,.markdown,.docx,.pdf" onChange={handleImport} className="hidden" />
          <Button onClick={() => document.getElementById("kb-import")?.click()} disabled={importing || !waId} variant="outline" className="border-neutral-700">
            <Upload className="h-4 w-4 mr-1" /> {importing ? "Importing..." : "Import"}
          </Button>
          
          <Select onValueChange={handleExport}>
            <SelectTrigger className="w-32 bg-neutral-900 border-neutral-800">
              <SelectValue placeholder="Export" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="json">JSON</SelectItem>
              <SelectItem value="csv">CSV</SelectItem>
              <SelectItem value="markdown">Markdown</SelectItem>
              <SelectItem value="text">Text</SelectItem>
            </SelectContent>
          </Select>
          
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger >
              <Button onClick={openAdd} className="bg-orange-600 hover:bg-orange-700"><Plus className="h-4 w-4 mr-1" /> Add</Button>
            </DialogTrigger>
            <DialogContent className="bg-neutral-900 border-neutral-800">
              <DialogHeader><DialogTitle>{editId ? "Edit Entry" : "Add Entry"}</DialogTitle></DialogHeader>
              <div className="space-y-3">
                <Input placeholder="Question" value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} className="bg-neutral-800 border-neutral-700" />
                <Textarea placeholder="Answer" value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })} rows={4} className="bg-neutral-800 border-neutral-700" />
                <div className="grid grid-cols-2 gap-2">
                  <Input placeholder="Category" value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })} className="bg-neutral-800 border-neutral-700" />
                  <Input placeholder="Tags (comma separated)" value={form.tags} onChange={(e) => setForm({ ...form, tags: e.target.value })} className="bg-neutral-800 border-neutral-700" />
                </div>
                <Button onClick={saveEntry} className="w-full bg-orange-600 hover:bg-orange-700">Save</Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader><CardTitle className="text-sm">{entries.length} entries</CardTitle></CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-[200px]">Question</TableHead>
                <TableHead>Answer</TableHead>
                <TableHead className="w-[100px]">Category</TableHead>
                <TableHead className="w-[80px]">Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {entries.map((entry) => (
                <TableRow key={entry.id}>
                  <TableCell className="font-medium text-sm">{entry.question}</TableCell>
                  <TableCell className="text-sm text-neutral-400 max-w-md truncate">{entry.answer}</TableCell>
                  <TableCell><Badge variant="secondary" className="bg-neutral-800">{entry.category}</Badge></TableCell>
                  <TableCell>
                    <div className="flex gap-1">
                      <Button variant="ghost" size="icon" onClick={() => openEdit(entry)}><Pencil className="h-3 w-3" /></Button>
                      <Button variant="ghost" size="icon" onClick={() => deleteEntry(entry.id)}><Trash2 className="h-3 w-3 text-red-500" /></Button>
                    </div>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {entries.length === 0 && <p className="text-neutral-500 text-center py-8 text-sm">No KB entries for this number</p>}
        </CardContent>
      </Card>
    </div>
  );
}
