import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

export interface Variant {
  id: string; name: string | null; sku: string; barcode: string | null; mrp: string | null;
  sale_price: string; cost_price: string; reorder_level: string; stock_qty: string; is_active: boolean;
}
export interface Product {
  id: string; name: string; category_id: string | null; category_name: string | null; brand: string | null;
  description: string | null; hsn_code: string | null; is_service: boolean; tax_rate_id: string | null;
  tax_rate: string | null; cess_rate: string; price_includes_tax: boolean; unit_code: string; track_stock: boolean;
  photo_url: string | null; thumb_url: string | null; archived: boolean; missing_tax_info: boolean;
  variants: Variant[]; updated_at: string;
}
export interface Page { items: Product[]; next_cursor: string | null; total: number }
export interface Category { id: string; name: string; sort_order: number; product_count: number }
export interface Unit { code: string; label: string; allows_decimal: boolean }
export interface Rate { id: string; label: string; rate: string; kind: string }
export interface Movement {
  id: number; variant_id: string; product_name: string; variant_name: string | null; kind: string;
  qty: string; unit_cost: string; reason: string | null; created_by_name: string | null; created_at: string;
}

export interface VariantIn {
  id?: string; name?: string | null; sku?: string | null; barcode?: string | null; mrp?: string | null;
  sale_price: string; cost_price?: string; reorder_level?: string; opening_stock?: string;
}
export interface ProductIn {
  name: string; category_id?: string | null; brand?: string | null; description?: string | null; hsn_code?: string | null;
  is_service?: boolean; tax_rate_id?: string | null; price_includes_tax?: boolean | null; unit_code: string;
  track_stock: boolean; variants: VariantIn[];
}

export interface ListParams { q?: string; category_id?: string; low_stock?: boolean; include_archived?: boolean; cursor?: string }
const qs = (p: Record<string, unknown>) =>
  new URLSearchParams(Object.entries(p).filter(([, v]) => v !== undefined && v !== "" && v !== false).map(([k, v]) => [k, String(v)])).toString();

export const useProducts = (p: ListParams) =>
  useQuery({ queryKey: ["products", p], queryFn: () => api<Page>(`/products?limit=50&${qs({ ...p })}`), placeholderData: keepPreviousData });
export const useProduct = (id?: string) =>
  useQuery({ queryKey: ["product", id], queryFn: () => api<Product>(`/products/${id}`), enabled: !!id });
export const useCategories = () => useQuery({ queryKey: ["categories"], queryFn: () => api<Category[]>("/categories") });
export const useUnits = () => useQuery({ queryKey: ["units"], queryFn: () => api<Unit[]>("/units"), staleTime: Infinity });
export const useRates = () => useQuery({ queryKey: ["rates"], queryFn: () => api<Rate[]>("/gst-rates"), staleTime: Infinity });
export const useMovements = (variantId?: string) =>
  useQuery({ queryKey: ["movements", variantId], queryFn: () => api<Movement[]>(`/stock/movements?limit=100&${qs({ variant_id: variantId })}`) });

/** Invalidate everything that shows catalogue data after a write. */
export function useCatalogueRefresh() {
  const qc = useQueryClient();
  return () => Promise.all(["products", "product", "categories", "movements", "valuation", "low"].map((k) => qc.invalidateQueries({ queryKey: [k] })));
}

export function useCreateCategory() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (name: string) => api<Category>("/categories", { method: "POST", json: { name } }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["categories"] }),
  });
}

export const qtyFmt = (q: string) => Number(q).toLocaleString("en-IN", { maximumFractionDigits: 3 });
// Only items with an alert level count as low; otherwise every new item at 0 stock would warn.
export const isLow = (v: Variant) => Number(v.reorder_level) > 0 && Number(v.stock_qty) <= Number(v.reorder_level);
