import { useQuery } from "@tanstack/react-query";
import { api } from "@/api/client";

export interface Customer {
  id: string; name: string | null; phone: string | null; email: string | null; gstin: string | null;
  billing_address: string | null; state_code: string | null; credit_limit: string | null; opening_balance: string;
  notes: string | null; tags: string[]; balance: string;
  bills?: number; spent?: string; last_visit?: string | null; first_visit?: string | null;
}
export interface CustomerPage { items: Customer[]; total: number; due_total: string; next_cursor: string | null }
export interface LedgerEntry { at: string; kind: "bill" | "paid_at_bill" | "payment" | "return" | "refund"; ref: string | null; ref_id: string | null; debit: string; credit: string; balance: string }
export interface Ledger { customer: Customer; opening_balance: string; entries: LedgerEntry[]; balance: string }
export interface CollectionReceipt { receipt_no: string; amount: string; method: string; status: string; allocations: { invoice: string | null; amount: string }[]; balance_after: string }
export interface Approval { id: string; kind: "collection" | "return" | "cash_close"; summary: string; amount: string | null; requested_by_name: string | null; created_at: string }
export interface CreditNoteRow { id: string; number: string; issued_at: string; grand_total: string; refund_method: string; refunded: string; due_adjusted: string; invoice_number: string | null }

export interface CashDay {
  date: string; opening_cash: string; cash_in: string; cash_out: string; expected_cash: string; pending_cash: string;
  breakdown: { direction: "in" | "out"; label: string; amount: string }[];
  close: { id: string; counted_cash: string; difference: string; status: string; note: string | null; closed_by_name: string | null } | null;
}
export interface DayBook { opening_cash: string; closing_cash: string; entries: { id: string; at: string; direction: "in" | "out"; method: string; amount: string; label: string; cash_balance: string }[] }
export interface Expense { id: string; category_id: string | null; category_name: string; amount: string; method: string; gst_amount: string | null; note: string | null; occurred_on: string; created_by_name: string | null }
export interface ExpensePage { items: Expense[]; total: string; by_category: { name: string; amount: string }[]; from: string; to: string }
export interface Borrowing { id: string; lender_name: string; lender_phone: string | null; principal: string; received_method: string; interest_note: string | null; borrowed_on: string; status: string; repaid: string; outstanding: string }
export interface Worker {
  id: string; name: string; phone: string | null; aadhaar_last4: string | null; gender: "male" | "female" | "other";
  wage_type: "daily" | "monthly"; daily_wage: string; monthly_wage: string; paid_leaves_per_month: number; joined_on: string; is_active: boolean;
  days_worked: string; earned: string; total_paid: string; balance_to_pay: string; leaves_this_month: string;
  unpaid_leaves_this_month: string; accrued_through: string | null; today?: "present" | "half_day" | "absent" | null;
}

export const useCustomer = (id?: string) => useQuery({ queryKey: ["customer", id], queryFn: () => api<Customer>(`/customers/${id}`), enabled: !!id });
export const useApprovals = (enabled = true) => useQuery({ queryKey: ["approvals"], queryFn: () => api<Approval[]>("/approvals"), enabled, refetchInterval: 60_000 });

export const newKey = () => crypto.randomUUID();
export const day = (iso: string) => new Date(iso).toLocaleDateString("en-IN", { day: "2-digit", month: "short", year: "numeric" });
export const dayTime = (iso: string) => new Date(iso).toLocaleString("en-IN", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
export const todayIso = () => new Date().toLocaleDateString("en-CA");
export const cell = "h-11 rounded-lg border border-border-strong bg-surface px-3";
