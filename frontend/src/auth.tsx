// Demo sign-in. Accounts and the session live in the browser only: this is for showing the
// role-based flow, not for protecting data. Swap for real auth before a client goes live.
import { createContext, useCallback, useContext, useState } from 'react';
import type { ReactNode } from 'react';

export type Role = 'planner' | 'manager' | 'sales' | 'admin';
export type User = { email: string; name: string; role: Role; title: string; initials: string };

export const DEMO_PASSWORD = 'demo';
export const USERS: User[] = [
  { email: 'priya@jada-demo.com', name: 'Priya Nair', role: 'planner', title: 'Supply planner', initials: 'PN' },
  { email: 'marcus@jada-demo.com', name: 'Marcus Webb', role: 'manager', title: 'Ops manager', initials: 'MW' },
  { email: 'dana@jada-demo.com', name: 'Dana Okafor', role: 'sales', title: 'Sales rep', initials: 'DO' },
  { email: 'admin@jada-demo.com', name: 'Alex Rivera', role: 'admin', title: 'Administrator', initials: 'AR' },
];
export const ROLE_BLURB: Record<Role, string> = {
  planner: 'Processes supplier emails, reviews anything uncertain and keeps purchase order dates right.',
  manager: 'Approves customer updates on large orders and watches which customers are at risk.',
  sales: 'Checks quotes before promising a date and knows which customers are affected.',
  admin: 'Sees everything: the simulated systems, test scenarios, activity log and settings.',
};

const KEY = 'q2d.user';
const ACCOUNT_EVENT = 'q2d-auth';
const read = (): User | null => {
  try { const e = localStorage.getItem(KEY); return USERS.find((u) => u.email === e) ?? null; } catch { return null; }
};

const Ctx = createContext<{ user: User | null; signIn: (email: string, password: string) => string | null; signInAs: (u: User) => void; signOut: () => void }>({
  user: null, signIn: () => 'Not ready', signInAs: () => {}, signOut: () => {},
});
export const useAuth = () => useContext(Ctx);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(read);
  const set = useCallback((u: User | null) => {
    try { u ? localStorage.setItem(KEY, u.email) : localStorage.removeItem(KEY); window.dispatchEvent(new Event(ACCOUNT_EVENT)); } catch { /* private mode */ }
    setUser(u);
  }, []);
  const signIn = useCallback((email: string, password: string) => {
    const u = USERS.find((x) => x.email === email.trim().toLowerCase());
    if (!u || password !== DEMO_PASSWORD) return 'That email or password is not right.';
    set(u); return null;
  }, [set]);
  return <Ctx.Provider value={{ user, signIn, signInAs: set, signOut: () => set(null) }}>{children}</Ctx.Provider>;
}

// Which screens each role can open, in sidebar order. 'grp' entries are section headings.
export type NavItem = [key: string, label: string, icon: string] | [kind: 'grp', label: string];
export const NAV: Record<Role, NavItem[]> = {
  planner: [
    ['home', 'Dashboard', 'home'], ['grp', 'Work'], ['mailbox', 'Supplier emails', 'mail'], ['approvals', 'Approvals', 'approve'], ['orders', 'Orders', 'warn'], ['inventory', 'Inventory', 'box'], ['erp', 'Purchase orders', 'erp'],
    ['grp', 'More'], ['runs', 'Activity', 'runs'], ['agent', 'Quick answers', 'agent'],
  ],
  manager: [
    ['home', 'Dashboard', 'home'], ['grp', 'Work'], ['approvals', 'Approvals', 'approve'], ['replies', 'Customer replies', 'agent'], ['orders', 'Orders', 'warn'], ['inventory', 'Inventory', 'box'], ['outbox', 'Sent to customers', 'out'],
    ['grp', 'More'], ['runs', 'Activity', 'runs'], ['agent', 'Quick answers', 'agent'],
  ],
  sales: [
    ['home', 'Dashboard', 'home'], ['grp', 'Work'], ['quotes', 'Quotes', 'quote'], ['replies', 'Customer replies', 'agent'], ['approvals', 'Approvals', 'approve'], ['orders', 'Orders', 'warn'], ['crm', 'Customers', 'crm'],
    ['grp', 'More'], ['agent', 'Quick answers', 'agent'],
  ],
  admin: [
    ['home', 'Dashboard', 'home'], ['grp', 'Work'], ['mailbox', 'Supplier emails', 'mail'], ['approvals', 'Approvals', 'approve'], ['replies', 'Customer replies', 'agent'], ['quotes', 'Quotes', 'quote'], ['orders', 'Orders', 'warn'], ['inventory', 'Inventory', 'box'],
    ['runs', 'Activity', 'runs'], ['agent', 'Quick answers', 'agent'],
    ['grp', 'Simulated systems'], ['erp', 'ERP', 'erp'], ['crm', 'CRM', 'crm'], ['outbox', 'Customer outbox', 'out'],
    ['grp', 'Quality'], ['scen', 'Test scenarios', 'scen'], ['pack', 'Accuracy test pack', 'test'], ['log', 'Activity log', 'log'],
    ['grp', 'Admin'], ['settings', 'Settings', 'gear'], ['how', 'How it works', 'how'],
  ],
};
export const allowed = (role: Role, view: string) => NAV[role].some((n) => n[0] === (view === 'order' ? 'orders' : view));
