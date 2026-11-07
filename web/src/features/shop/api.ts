import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@/api/client";

export type Scheme = "regular" | "composition" | "unregistered";

export interface TaxProfile {
  gst_scheme: Scheme; gstin: string | null; legal_name: string | null; trade_name: string | null;
  composition_rate: string | null; prices_include_tax: boolean; hsn_digits_required: 4 | 6;
  invoice_round_off: boolean; einvoice_applicable: boolean; filing_frequency: "monthly" | "qrmp";
}

export interface Shop {
  id: string; name: string; business_type: string; phone: string | null; email: string | null;
  address_line1: string | null; address_line2: string | null; city: string | null; pincode: string | null;
  state_code: string; state_name: string; logo_url: string | null; upi_vpa: string | null;
  upi_payee_name: string | null; settings: Record<string, unknown>; onboarding_completed_at: string | null;
  tax: TaxProfile;
}

export interface Staff {
  id: string; full_name: string; email: string; phone: string | null; role: "manager" | "salesperson";
  is_active: boolean; last_login_at: string | null; must_change_password: boolean;
}

export const useShop = () => useQuery({ queryKey: ["shop"], queryFn: () => api<Shop>("/shop") });
export const useStaff = () => useQuery({ queryKey: ["staff"], queryFn: () => api<Staff[]>("/shop/staff") });

function useShopMutation<T>(fn: (v: T) => Promise<Shop>) {
  const qc = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: (shop) => qc.setQueryData(["shop"], shop) });
}

export const usePatchShop = () => useShopMutation((v: Partial<Shop>) => api<Shop>("/shop", { method: "PATCH", json: v }));
export const usePutTax = () => useShopMutation((v: Partial<TaxProfile>) => api<Shop>("/shop/tax-profile", { method: "PUT", json: v }));

export function useUploadLogo() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (file: File | null) => {
      if (!file) return api("/shop/logo", { method: "DELETE" });
      const body = new FormData();
      body.append("file", file);
      return api("/shop/logo", { method: "POST", body });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["shop"] }),
  });
}
