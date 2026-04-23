"use client";

import { useState } from "react";
import useSWR from "swr";
import {
  fetcher,
  createProduct,
  updateProduct,
  deleteProduct,
  importCSV,
  type WANumber,
  type Product,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Plus, Pencil, Trash2, Loader2, Upload, Download, Package } from "lucide-react";

export default function ProductsPage() {
  const { data: waData, isLoading: waLoad } = useSWR<{ numbers: WANumber[] }>("/api/v1/agents/wa/sessions", fetcher);
  const [selectedWA, setSelectedWA] = useState<string>("");
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editId, setEditId] = useState<string | null>(null);
  const [form, setForm] = useState<{
    name: string;
    description: string;
    category: string;
    base_price_cents: number;
    sku: string;
    status: "active" | "inactive" | "discontinued" | "draft";
    visibility: "public" | "private" | "hidden";
  }>({
    name: "",
    description: "",
    category: "",
    base_price_cents: 0,
    sku: "",
    status: "active",
    visibility: "public",
  });
  const [importing, setImporting] = useState(false);

  const waId = selectedWA || waData?.numbers[0]?.id || "";
  const { data: products, mutate, isLoading: productsLoading } = useSWR<Product[]>(
    waId ? `/api/v1/products?wa_number_id=${waId}` : null,
    fetcher
  );

  async function handleImport(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !waId) return;

    setImporting(true);
    try {
      const result = await importCSV(waId, file);
      alert(`✓ Imported ${result.imported} products${result.errors.length > 0 ? `\n\nErrors:\n${result.errors.join("\n")}` : ""}`);
      mutate();
    } catch (error) {
      alert(`✗ Import error: ${error}`);
    } finally {
      setImporting(false);
      e.target.value = "";
    }
  }

  function handleExport() {
    if (!waId) return;
    window.open(`/api/v1/products/export?wa_number_id=${waId}`, "_blank");
  }

  if (waLoad) {
    return (
      <div className="p-6 flex items-center justify-center h-[50vh]">
        <Loader2 className="h-8 w-8 animate-spin text-orange-500" />
      </div>
    );
  }

  function openAdd() {
    setEditId(null);
    setForm({
      name: "",
      description: "",
      category: "",
      base_price_cents: 0,
      sku: "",
      status: "active",
      visibility: "public",
    });
    setDialogOpen(true);
  }

  function openEdit(product: Product) {
    setEditId(product.id!);
    setForm({
      name: product.name,
      description: product.description || "",
      category: product.category,
      base_price_cents: product.base_price_cents,
      sku: product.sku,
      status: product.status,
      visibility: product.visibility,
    });
    setDialogOpen(true);
  }

  async function saveProduct() {
    if (!waId || !form.name || !form.category || !form.sku) return;

    try {
      if (editId) {
        await updateProduct(editId, form);
      } else {
        await createProduct({
          wa_number_id: waId,
          currency: "IDR",
          ...form,
        });
      }
      setDialogOpen(false);
      mutate();
    } catch (error) {
      alert(`✗ Save error: ${error}`);
    }
  }

  async function deleteProductHandler(id: string) {
    if (!confirm("Delete this product?")) return;
    try {
      await deleteProduct(id);
      mutate();
    } catch (error) {
      alert(`✗ Delete error: ${error}`);
    }
  }

  const formatPrice = (cents: number) => {
    return new Intl.NumberFormat("id-ID", {
      style: "currency",
      currency: "IDR",
      minimumFractionDigits: 0,
    }).format(cents / 100);
  };

  return (
    <div className="p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Products</h1>
        <div className="flex gap-2">
          <Select value={selectedWA} onValueChange={(v) => v && setSelectedWA(v)}>
            <SelectTrigger className="w-56 bg-neutral-900 border-neutral-800">
              <SelectValue placeholder="Select WA Number" />
            </SelectTrigger>
            <SelectContent>
              {waData?.numbers.map((n) => (
                <SelectItem key={n.id} value={n.id}>
                  {n.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          <input
            type="file"
            id="product-import"
            accept=".csv"
            onChange={handleImport}
            className="hidden"
          />
          <Button
            onClick={() => document.getElementById("product-import")?.click()}
            disabled={importing || !waId}
            variant="outline"
            className="border-neutral-700"
          >
            <Upload className="h-4 w-4 mr-1" /> {importing ? "Importing..." : "Import CSV"}
          </Button>

          <Button
            onClick={handleExport}
            disabled={!waId || !products || products.length === 0}
            variant="outline"
            className="border-neutral-700"
          >
            <Download className="h-4 w-4 mr-1" /> Export CSV
          </Button>

          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger>
              <Button onClick={openAdd} className="bg-orange-600 hover:bg-orange-700">
                <Plus className="h-4 w-4 mr-1" /> Add Product
              </Button>
            </DialogTrigger>
            <DialogContent className="bg-neutral-900 border-neutral-800 max-w-2xl">
              <DialogHeader>
                <DialogTitle>{editId ? "Edit Product" : "Add Product"}</DialogTitle>
              </DialogHeader>
              <div className="space-y-3">
                <Input
                  placeholder="Product Name"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="bg-neutral-800 border-neutral-700"
                />
                <Textarea
                  placeholder="Description"
                  value={form.description}
                  onChange={(e) => setForm({ ...form, description: e.target.value })}
                  rows={3}
                  className="bg-neutral-800 border-neutral-700"
                />
                <div className="grid grid-cols-2 gap-2">
                  <Input
                    placeholder="Category"
                    value={form.category}
                    onChange={(e) => setForm({ ...form, category: e.target.value })}
                    className="bg-neutral-800 border-neutral-700"
                  />
                  <Input
                    placeholder="SKU"
                    value={form.sku}
                    onChange={(e) => setForm({ ...form, sku: e.target.value })}
                    className="bg-neutral-800 border-neutral-700"
                  />
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <Input
                    type="number"
                    placeholder="Price (cents)"
                    value={form.base_price_cents}
                    onChange={(e) =>
                      setForm({ ...form, base_price_cents: parseInt(e.target.value) || 0 })
                    }
                    className="bg-neutral-800 border-neutral-700"
                  />
                  <Select
                    value={form.status}
                    onValueChange={(v: any) => setForm({ ...form, status: v })}
                  >
                    <SelectTrigger className="bg-neutral-800 border-neutral-700">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="active">Active</SelectItem>
                      <SelectItem value="inactive">Inactive</SelectItem>
                      <SelectItem value="discontinued">Discontinued</SelectItem>
                      <SelectItem value="draft">Draft</SelectItem>
                    </SelectContent>
                  </Select>
                  <Select
                    value={form.visibility}
                    onValueChange={(v: any) => setForm({ ...form, visibility: v })}
                  >
                    <SelectTrigger className="bg-neutral-800 border-neutral-700">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="public">Public</SelectItem>
                      <SelectItem value="private">Private</SelectItem>
                      <SelectItem value="hidden">Hidden</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
                <Button onClick={saveProduct} className="w-full bg-orange-600 hover:bg-orange-700">
                  Save Product
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      <Card className="bg-neutral-900 border-neutral-800">
        <CardHeader>
          <CardTitle className="text-sm">{products?.length || 0} products</CardTitle>
        </CardHeader>
        <CardContent>
          {productsLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-orange-500" />
            </div>
          ) : (
            <>
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead className="w-[60px]">Image</TableHead>
                    <TableHead className="w-[200px]">Name</TableHead>
                    <TableHead className="w-[120px]">Category</TableHead>
                    <TableHead className="w-[100px]">SKU</TableHead>
                    <TableHead className="w-[120px]">Base Price</TableHead>
                    <TableHead className="w-[100px]">Status</TableHead>
                    <TableHead className="w-[100px]">Visibility</TableHead>
                    <TableHead className="w-[80px]">Actions</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {products?.map((product) => (
                    <TableRow key={product.id}>
                      <TableCell>
                        {product.image_url ? (
                          <img
                            src={product.image_url}
                            alt={product.name}
                            className="w-10 h-10 rounded object-cover border border-neutral-700"
                          />
                        ) : (
                          <div className="w-10 h-10 rounded bg-neutral-800 border border-neutral-700 flex items-center justify-center">
                            <Package className="h-4 w-4 text-neutral-600" />
                          </div>
                        )}
                      </TableCell>
                      <TableCell className="font-medium text-sm">{product.name}</TableCell>
                      <TableCell className="text-sm text-neutral-400">{product.category}</TableCell>
                      <TableCell className="text-sm text-neutral-400">{product.sku}</TableCell>
                      <TableCell className="text-sm">{formatPrice(product.base_price_cents)}</TableCell>
                      <TableCell>
                        <Badge
                          variant="secondary"
                          className={
                            product.status === "active"
                              ? "bg-green-900/30 text-green-400"
                              : "bg-neutral-800"
                          }
                        >
                          {product.status}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className="bg-neutral-800">
                          {product.visibility}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <div className="flex gap-1">
                          <Button variant="ghost" size="icon" onClick={() => openEdit(product)}>
                            <Pencil className="h-3 w-3" />
                          </Button>
                          <Button
                            variant="ghost"
                            size="icon"
                            onClick={() => deleteProductHandler(product.id!)}
                          >
                            <Trash2 className="h-3 w-3 text-red-500" />
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              {(!products || products.length === 0) && (
                <div className="text-center py-12 space-y-3">
                  <Package className="h-12 w-12 text-neutral-700 mx-auto" />
                  <p className="text-neutral-400 text-sm">No products yet for this WA number</p>
                  <p className="text-neutral-600 text-xs">Add products manually or import from CSV to get started</p>
                  <div className="flex gap-2 justify-center pt-2">
                    <Button onClick={openAdd} className="bg-orange-600 hover:bg-orange-700 text-sm">
                      <Plus className="h-4 w-4 mr-1" /> Add First Product
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
