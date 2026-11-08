import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export interface ReceiptLine { id: string; returned_qty: string; name: string; variant_name: string | null; hsn: string | null; qty: string; unit: string; unit_price: string; discount: string; taxable: string; tax_rate: string; line_total: string }
export interface Receipt {
  id: string; number: string; doc_type: string; title: string; composition_note: string | null; status: string;
  cancel_reason: string | null; is_edited: boolean; issued_at: string; handed_over: boolean; customer_id: string | null;
  shop: { name: string; legal_name: string | null; address: string; state: string; phone: string | null; gstin: string | null; logo_url: string | null; upi: string | null };
  buyer: { name: string | null; phone: string | null; gstin: string | null; address: string | null } | null;
  place_of_supply: string; supply_type: string; state_tax_label: string; reverse_charge: string; delivery_address: string | null;
  lines: ReceiptLine[];
  tax_summary: { rate: string; taxable: string; cgst: string; sgst: string; igst: string; cess: string }[];
  totals: Record<"subtotal_gross" | "discount_total" | "taxable_total" | "cgst_total" | "sgst_total" | "igst_total" | "cess_total" | "round_off" | "grand_total" | "paid_total" | "due_total", string>;
  amount_in_words: string; payments: { method: string; amount: string; reference: string | null }[];
  remarks: string | null; created_by_name: string | null; footer: string; public_url: string; upi_due_uri: string | null;
}
export interface InvoiceRow {
  id: string; number: string; doc_type: string; issued_at: string; buyer_name: string | null; buyer_phone: string | null;
  grand_total: string; paid_total: string; due_total: string; status: string; created_by_name: string | null; methods: string[];
}
export interface InvoicePage { items: InvoiceRow[]; next_cursor: string | null; total: number; sales_total: string }
export interface Held { id: string; label: string; payload: unknown; created_by_name: string | null; created_at: string }

export const useInvoice = (id?: string) => useQuery({ queryKey: ["invoice", id], queryFn: () => api<Receipt>(`/invoices/${id}`), enabled: !!id });
export const useHeld = () => useQuery({ queryKey: ["held"], queryFn: () => api<Held[]>("/held-bills") });

/** upi://pay link any UPI app understands; amount and bill number are filled in for the customer. */
export function upiUri(vpa: string, payee: string, amount: string, note: string) {
  const p = new URLSearchParams({ pa: vpa, pn: payee, am: Number(amount).toFixed(2), tn: note, cu: "INR" });
  return `upi://pay?${p.toString().replace(/\+/g, "%20")}`;
}
