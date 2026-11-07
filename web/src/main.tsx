import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { StrictMode, useEffect, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { createBrowserRouter, Navigate, RouterProvider } from "react-router-dom";
import { HomePage } from "@/features/app/HomePage";
import { LoginPage } from "@/features/auth/LoginPage";
import { SignupPage } from "@/features/auth/SignupPage";
import { useAuth } from "@/features/auth/store";
import "@/styles/index.css";

function Gate({ need, children }: { need: "anonymous" | "ready"; children: ReactNode }) {
  const status = useAuth((s) => s.status);
  if (status === "loading")
    return <div className="grid min-h-dvh place-items-center bg-bg"><Loader2 className="h-6 w-6 animate-spin text-brand" aria-label="Loading" /></div>;
  if (status !== need) return <Navigate to={need === "ready" ? "/login" : "/app"} replace />;
  return <>{children}</>;
}

const router = createBrowserRouter([
  { path: "/login", element: <Gate need="anonymous"><LoginPage /></Gate> },
  { path: "/signup", element: <Gate need="anonymous"><SignupPage /></Gate> },
  { path: "/app/*", element: <Gate need="ready"><HomePage /></Gate> },
  { path: "*", element: <Navigate to="/app" replace /> },
]);

function App() {
  const init = useAuth((s) => s.init);
  useEffect(() => { void init(); }, [init]);
  return <RouterProvider router={router} />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false } } })}>
      <App />
    </QueryClientProvider>
  </StrictMode>,
);
