import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "@/api/queryClient";
import { Loader2 } from "lucide-react";
import { StrictMode, useEffect, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider, useLocation } from "react-router-dom";
import { AppShell } from "@/features/app/AppShell";
import { HomePage } from "@/features/app/HomePage";
import { LoginPage } from "@/features/auth/LoginPage";
import { ForceChangePage, ForgotPage, ResetPage } from "@/features/auth/PasswordPages";
import { SignupPage } from "@/features/auth/SignupPage";
import { useAuth } from "@/features/auth/store";
import { OnboardingPage } from "@/features/onboarding/OnboardingPage";
import { ItemsPage } from "@/features/items/ItemsPage";
import { ProductEditor } from "@/features/items/ProductEditor";
import { ImportPage, LabelsPage, StockPage } from "@/features/items/ToolsPages";
import { PosPage } from "@/features/pos/PosPage";
import { InvoiceDetail, PublicInvoicePage, SalesPage } from "@/features/pos/SalesPages";
import { SettingsPage } from "@/features/settings/SettingsPage";
import "@/styles/index.css";

const Spinner = () => (
  <div className="grid min-h-dvh place-items-center bg-bg"><Loader2 className="h-6 w-6 animate-spin text-brand" aria-label="Loading" /></div>
);

/** One place decides where a user is allowed to be. */
function Gate({ need, children }: { need: "anonymous" | "ready"; children: ReactNode }) {
  const { status, me, can } = useAuth();
  const path = useLocation().pathname;
  if (status === "loading") return <Spinner />;
  if (status !== need) return <Navigate to={need === "ready" ? "/login" : "/app"} replace />;
  if (need === "ready" && me) {
    if (me.user.must_change_password && path !== "/change-password") return <Navigate to="/change-password" replace />;
    const mustOnboard = me.active_shop_id && !me.onboarding_completed && can("shop.settings");
    if (mustOnboard && path !== "/welcome" && path !== "/change-password") return <Navigate to="/welcome" replace />;
  }
  return <>{children}</>;
}

const router = createBrowserRouter([
  { path: "/login", element: <Gate need="anonymous"><LoginPage /></Gate> },
  { path: "/signup", element: <Gate need="anonymous"><SignupPage /></Gate> },
  { path: "/forgot", element: <Gate need="anonymous"><ForgotPage /></Gate> },
  { path: "/reset/:token", element: <ResetPage /> },
  { path: "/i/:token", element: <PublicInvoicePage /> },
  { path: "/pos", element: <Gate need="ready"><PosPage /></Gate> },
  { path: "/change-password", element: <Gate need="ready"><ForceChangePage /></Gate> },
  { path: "/welcome", element: <Gate need="ready"><OnboardingPage /></Gate> },
  {
    path: "/app",
    element: <Gate need="ready"><AppShell /></Gate>,
    children: [
      { index: true, element: <HomePage /> },
      { path: "items", element: <ItemsPage /> },
      { path: "items/new", element: <ProductEditor /> },
      { path: "items/import", element: <ImportPage /> },
      { path: "items/labels", element: <LabelsPage /> },
      { path: "items/stock", element: <StockPage /> },
      { path: "items/:id", element: <ProductEditor /> },
      { path: "sales", element: <SalesPage /> },
      { path: "sales/:id", element: <InvoiceDetail /> },
      { path: "settings/*", element: <SettingsPage /> },
    ],
  },
  { path: "*", element: <Navigate to="/app" replace /> },
]);

function App() {
  const init = useAuth((s) => s.init);
  useEffect(() => { void init(); }, [init]);
  return <RouterProvider router={router} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
