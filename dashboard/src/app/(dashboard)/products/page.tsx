"use client";

import { useState, useEffect } from "react";
import useSWR from "swr";
import {
  fetcher,
  createProduct,
  updateProduct,
  deleteProduct,
  importCSV,
  uploadImage,
  type WANumber,
  type Product,
  type ProductImage,
} from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Plus, Pencil, Trash2, Loader2, Upload, Download, Package, Link, FileImage } from "lucide-react";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

const API_BASE = "/api";

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
    image_url: string;
  }>({
    name: "",
    description: "",
    category: "",
    base_price_cents: 0,
    sku: "",
    status: "active",
    visibility: "public",
    image_url: "",
  });
  const [importing, setImporting] = useState(false);
  const [uploadingImg, setUploadingImg] = useState(false);
  const [imageMode, setImageMode] = useState<"url" | "upload">("url");

  const waId = selectedWA || waData?.numbers[0]?.session_name || "";
  const { data: products, mutate, isLoading: productsLoading } = useSWR<Product[]>(
    waId ? `/api/v1/products?wa_number_id=${waId}` : null,
    fetcher
  );

  const [productImageMap, setProductImageMap] = useState<Record<string, ProductImage[]>>({});

  useEffect(() => {
    if (!products?.length) {
      setProductImageMap({});
      return;
    }
    Promise.all(
      products.map(async (p) => {
        if (!p.id) return [p.id!, []] as const;
        try {
          const res = await fetch(`/api/v1/products/${p.id}/images`);
          const data = res.ok ? await res.json() : [];
          return [p.id!, data] as const;
        } catch {
          return [p.id!, []] as const;
        }
      })
    ).then((pairs) => {
      const imgs: Record<string, ProductImage[]> = {};
      pairs.forEach(([id, arr]) => { if (id) imgs[id!] = arr; });
      setProductImageMap(imgs);
    });
  }, [products]);

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
      image_url: "",
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
      image_url: product.image_url || "",
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

  async function handleImageUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !editId) return;

    setUploadingImg(true);
    try {
      const result = await uploadImage(editId, file);
      setForm({ ...form, image_url: result.image_url });
      mutate();
    } catch (error) {
      alert(`✗ Upload error: ${error}`);
    } finally {
      setUploadingImg(false);
      e.target.value = "";
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
                <Tabs value={imageMode} onValueChange={(v) => setImageMode(v as "url" | "upload")}>
                  <TabsList className="bg-neutral-800">
                    <TabsTrigger value="url" className="flex-1">
                      <Link className="h-4 w-4 mr-1" /> URL
                    </TabsTrigger>
                    <TabsTrigger value="upload" className="flex-1">
                      <FileImage className="h-4 w-4 mr-1" /> Upload
                    </TabsTrigger>
                  </TabsList>
                  <TabsContent value="url">
                    <Input
                      placeholder="Image URL (https://...)"
                      value={form.image_url}
                      onChange={(e) => setForm({ ...form, image_url: e.target.value })}
                      className="bg-neutral-800 border-neutral-700"
                    />
                  </TabsContent>
                  <TabsContent value="upload">
                    {editId ? (
                      <div className="flex items-center gap-2">
                        <input
                          type="file"
                          id="product-image-upload"
                          accept="image/*"
                          onChange={handleImageUpload}
                          className="hidden"
                        />
                        <Button
                          type="button"
                          variant="outline"
                          onClick={() => document.getElementById("product-image-upload")?.click()}
                          disabled={uploadingImg}
                          className="border-neutral-700"
                        >
                          {uploadingImg ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Upload className="h-4 w-4 mr-1" />
                          )}
                          {uploadingImg ? "Uploading..." : "Choose Image"}
                        </Button>
                        {form.image_url && (
                          <img 
                            src={form.image_url.startsWith("http") ? form.image_url : API_BASE + form.image_url} 
                            alt="Preview" 
                            className="h-10 w-10 rounded object-cover border border-neutral-700" 
                          />
                        )}
                      </div>
                    ) : (
                      <p className="text-sm text-neutral-500">Save product first, then upload image</p>
                    )}
                  </TabsContent>
                </Tabs>
                <Textarea
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
                  {products?.map((product) => {
                    const images = productImageMap[product.id!] || [];
                    const hasMultiple = images.length > 1;
                    return (
                    <TableRow key={product.id}>
                      <TableCell>
                        {images.length > 0 ? (
                          <div className="relative group">
                            <img
                              src={images[0].image_url.startsWith("http") ? images[0].image_url : API_BASE + images[0].image_url}
                              alt={product.name}
                              className="w-10 h-10 rounded object-cover border border-neutral-700"
                            />
                            {hasMultiple && (
                              <div className="absolute -bottom-1 -right-1 bg-neutral-900 text-neutral-400 text-[8px] px-1 rounded border border-neutral-700">
                                +{images.length - 1}
                              </div>
                            )}
                            {hasMultiple && (
                              <div className="absolute left-0 top-0 hidden group-hover:flex gap-1 bg-neutral-900 p-1 rounded border border-neutral-700 z-10">
                                {images.slice(0, 4).map((img, i) => (
                                  <img
                                    key={img.id}
                                    src={img.image_url.startsWith("http") ? img.image_url : API_BASE + img.image_url}
                                    alt={i.toString()}
                                    className="w-8 h-8 rounded object-cover border border-neutral-600"
                                  />
                                ))}
                              </div>
                            )}
                          </div>
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
                    )})}
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
