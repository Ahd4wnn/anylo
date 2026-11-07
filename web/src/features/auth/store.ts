import { create } from "zustand";
import { api, onRemoteLogout, restoreSession, session } from "@/api/client";
import { queryClient } from "@/api/queryClient";

export interface Me {
  user: { id: string; email: string; full_name: string; phone: string | null; role: string; preferred_language: string; must_change_password: boolean };
  onboarding_completed: boolean;
  shops: { id: string; name: string }[];
  active_shop_id: string | null;
  subscription: { status: string; trial_ends_at: string; days_left: number | null; read_only: boolean } | null;
  permissions: string[];
}

interface Tokens { access_token: string }

interface AuthState {
  me: Me | null;
  status: "loading" | "anonymous" | "ready";
  init: () => Promise<void>;
  login: (login: string, password: string) => Promise<void>;
  signup: (data: Record<string, string>) => Promise<void>;
  logout: () => Promise<void>;
  can: (permission: string) => boolean;
  switchShop: (id: string) => Promise<void>;
  refreshMe: () => Promise<void>;
  acceptTokens: (accessToken: string) => Promise<void>;
}

export const useAuth = create<AuthState>((set, get) => {
  const SHOP_KEY = "anylo.shop";
  const remembered = () => { try { return localStorage.getItem(SHOP_KEY); } catch { return null; } };
  const remember = (id: string | null) => { try { if (id) localStorage.setItem(SHOP_KEY, id); else localStorage.removeItem(SHOP_KEY); } catch { /* storage blocked */ } };
  const loadMe = async () => {
    session.setShop(remembered());
    let me: Me;
    try {
      me = await api<Me>("/auth/me");
    } catch {
      session.setShop(null); // remembered shop no longer accessible
      me = await api<Me>("/auth/me");
    }
    session.setShop(me.active_shop_id);
    remember(me.active_shop_id);
    set({ me, status: "ready" });
  };
  const clear = () => { queryClient.clear(); session.set(null); session.setShop(null); set({ me: null, status: "anonymous" }); };
  onRemoteLogout(clear);

  return {
    me: null,
    status: "loading",
    async init() {
      // Only a definitive "invalid" logs the user out; network trouble keeps retrying.
      for (let wait = 1000; ; wait = Math.min(wait * 2, 15000)) {
        const r = await restoreSession();
        if (r === "invalid") return clear();
        if (r === "ok") { try { return await loadMe(); } catch { /* retry */ } }
        await new Promise((res) => setTimeout(res, wait));
      }
    },
    async login(login, password) {
      const t = await api<Tokens>("/auth/login", { method: "POST", json: { login, password, platform: "web" } });
      session.set(t.access_token);
      await loadMe();
    },
    async signup(data) {
      const t = await api<Tokens>("/auth/signup", { method: "POST", json: { ...data, platform: "web" } });
      session.set(t.access_token);
      await loadMe();
    },
    async logout() {
      await api("/auth/logout", { method: "POST" }).catch(() => undefined);
      remember(null);
      clear();
    },
    can: (p) => !!get().me?.permissions.includes(p),
    async switchShop(id) {
      remember(id);
      queryClient.clear(); // never show one shop's cached data in another

      await loadMe();
    },
    refreshMe: loadMe,
    async acceptTokens(accessToken) {
      session.set(accessToken);
      await loadMe();
    },
  };
});
