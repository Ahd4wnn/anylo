import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useAuth } from "@/features/auth/store";
import { useShop } from "@/features/shop/api";
import { PageHeader } from "@/ui/primitives";
import { BusinessForm, LogoAndUpiForm, TaxForm } from "./forms";
import { SecurityPanel } from "./SecurityPanel";
import { StaffPanel } from "./StaffPanel";

function ShopSettings({ section }: { section: "business" | "tax" }) {
  const { data: shop, isLoading } = useShop();
  if (isLoading || !shop) return <p className="text-text-2">Loading…</p>;
  return section === "business"
    ? <div className="space-y-6"><BusinessForm shop={shop} /><LogoAndUpiForm shop={shop} /></div>
    : <TaxForm shop={shop} />;
}

export function SettingsPage() {
  const can = useAuth((s) => s.can);
  const tabs = [
    ...(can("shop.settings") ? [{ to: "business", label: "Business" }, { to: "tax", label: "GST" }] : []),
    ...(can("staff.salespeople") ? [{ to: "staff", label: "Staff" }] : []),
    { to: "security", label: "Security" },
  ];
  return (
    <>
      <PageHeader title="Settings" />
      <nav className="mb-6 flex gap-1 overflow-x-auto border-b border-border" aria-label="Settings sections">
        {tabs.map((t) => (
          <NavLink key={t.to} to={t.to}
            className={({ isActive }) => `-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 font-medium ${isActive ? "border-primary text-primary" : "border-transparent text-text-2 hover:text-text"}`}>
            {t.label}
          </NavLink>
        ))}
      </nav>
      <Routes>
        <Route index element={<Navigate to={tabs[0].to} replace />} />
        <Route path="business" element={<ShopSettings section="business" />} />
        <Route path="tax" element={<ShopSettings section="tax" />} />
        <Route path="staff" element={<StaffPanel />} />
        <Route path="security" element={<SecurityPanel />} />
      </Routes>
    </>
  );
}
