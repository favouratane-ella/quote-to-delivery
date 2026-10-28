import { useCallback, useEffect, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import { useAuth } from './auth';

// ---------- formatting ----------
const DOW = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];
const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
export function fmtDate(s?: string | null): string {
  if (!s) return 'No date';
  const d = new Date(Date.UTC(+s.slice(0, 4), +s.slice(5, 7) - 1, +s.slice(8, 10)));
  return `${DOW[d.getUTCDay()]} ${d.getUTCDate()} ${MON[d.getUTCMonth()]}`;
}
export const money = (n: number) => '$' + Math.round(n).toLocaleString('en-US');
export const hm = (iso?: string | null) => {
  if (!iso) return '';
  if (!iso.endsWith('Z')) return iso.slice(11, 16);
  const d = new Date(iso);
  return String(d.getHours()).padStart(2, '0') + ':' + String(d.getMinutes()).padStart(2, '0');
};
export const typeLabel = (t: string) =>
  ({ stock_note: 'stock count', accept: 'accepts the new date', hard_deadline: 'cannot accept the new date', partial_ok: 'will take part now', expedite: 'asks for faster shipping', credit: 'asks for a credit', cancel: 'wants to cancel', reschedule: 'proposes a date', question: 'asks a question', delay: 'delivery delay', partial: 'split delivery', confirmation: 'confirmation, no change', unclear: 'possible change, no firm date', other: 'not about a delivery date' } as Record<string, string>)[t] || t;

// ---------- risk and case vocabulary ----------
export const RISK_CLS: Record<string, string> = { Critical: 'bad', High: 'bad', Medium: 'warn', Watch: 'acc', Low: 'good' };
export const CASE_LABEL: Record<string, string> = { at_risk: 'At risk', notified: 'Customer told', offer_sent: 'Offer sent', plan_proposed: 'Plan proposed', escalated: 'Escalated', resolved: 'Resolved', lost: 'Lost' };
export const RESOLUTION_LABEL: Record<string, string> = { recovered: 'Date kept', agreed: 'New date agreed', split: 'Split delivery', supply_recovered: 'Supplier recovered', credited: 'Credited', lost: 'Lost' };
export const FLEX_LABEL: Record<string, string> = { hard: 'Hard deadline', partial: 'Takes part deliveries', flexible: 'Flexible on dates' };
export const KIND_LABEL: Record<string, string> = { stock: 'Ship from stock', split: 'Split delivery', reallocate: 'Reallocate stock', expedite: 'Express shipping', substitute: 'Substitute item', new_date: 'New date', credit: 'Credit', supplier: 'Chase supplier', escalate: 'Escalation', reply: 'Answer a question', raise_po: 'Purchase order', resupply: 'Stock replan' };
export function Risk({ tier }: { tier?: string | null }) {
  return tier ? <span className={'st ' + (RISK_CLS[tier] || '')} style={tier === 'Critical' ? { fontWeight: 700 } : undefined}>{tier}</span> : null;
}

// ---------- data hooks ----------
/** Fetch on mount and every `ms` milliseconds. Returns [data, reload, error]. */
export function usePoll<T>(fn: () => Promise<T>, ms: number, deps: unknown[] = []): [T | null, () => void, string | null] {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fnRef = useRef(fn);
  fnRef.current = fn;
  const load = useCallback(() => {
    fnRef.current().then((d) => { setData(d); setErr(null); }).catch((e) => setErr(String(e.message || e)));
  }, []);
  useEffect(() => {
    load();
    if (!ms) return;
    const t = setInterval(load, ms);
    return () => clearInterval(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  return [data, load, err];
}

// ---------- toast ----------
let pushToast: (m: string) => void = () => {};
export const toast = (m: string) => pushToast(m);
export function Toaster() {
  const [msg, setMsg] = useState<string | null>(null);
  useEffect(() => {
    let t: number | undefined;
    pushToast = (m) => { setMsg(m); clearTimeout(t); t = window.setTimeout(() => setMsg(null), 3600); };
  }, []);
  return msg ? <div className="toast" role="status">{msg}</div> : null;
}

// ---------- icons ----------
const P: Record<string, ReactNode> = {
  search: <><circle cx="11" cy="11" r="6" /><path d="M20 20l-4-4" /></>,
  box: <><path d="M3 7.5L12 3l9 4.5v9L12 21l-9-4.5z" /><path d="M3 7.5l9 4.5 9-4.5M12 12v9" /></>,
  home: <path d="M4 11l8-7 8 7v9a1 1 0 01-1 1h-4v-6H9v6H5a1 1 0 01-1-1z" />,
  bell: <><path d="M6 17V11a6 6 0 0112 0v6l1.5 2h-15z" /><path d="M10 21h4" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5L19 19M5 19l1.5-1.5M17.5 6.5L19 5" /></>,
  moon: <path d="M20 14.5A8 8 0 019.5 4 8 8 0 1020 14.5z" />,
  menu: <path d="M4 7h16M4 12h16M4 17h16" />,
  out2: <><path d="M9 4H5a1 1 0 00-1 1v14a1 1 0 001 1h4" /><path d="M16 8l4 4-4 4M20 12H9" /></>,
  swap: <><path d="M7 4L3 8l4 4M3 8h14" /><path d="M17 12l4 4-4 4M21 16H7" /></>,
  how: <><circle cx="12" cy="12" r="9" /><path d="M12 16v-4M12 8h.01" /></>,
  runs: <><path d="M4 6h10M4 12h16M4 18h7" /><circle cx="18" cy="6" r="2" /><circle cx="15" cy="18" r="2" /></>,
  agent: <><path d="M4 5h16v11H9l-5 4z" /><path d="M8 10h.01M12 10h.01M16 10h.01" /></>,
  mail: <><rect x="3" y="5" width="18" height="14" rx="2" /><path d="M3 7l9 6 9-6" /></>,
  erp: <><path d="M4 7l8-4 8 4-8 4z" /><path d="M4 12l8 4 8-4M4 17l8 4 8-4" /></>,
  crm: <><circle cx="9" cy="8" r="3" /><path d="M3 20a6 6 0 0112 0" /><path d="M16 5a3 3 0 010 6M21 20a6 6 0 00-4-5.6" /></>,
  out: <path d="M4 12l16-8-6 16-3-7z" />,
  approve: <><path d="M9 12l2 2 4-4" /><rect x="4" y="4" width="16" height="16" rx="3" /></>,
  quote: <><path d="M6 3h9l4 4v14H6z" /><path d="M14 3v5h5" /><path d="M9 13h7M9 17h5" /></>,
  scen: <path d="M9 3h6M10 3v6l-5 9a2 2 0 002 3h10a2 2 0 002-3l-5-9V3" />,
  test: <path d="M4 19h16M7 16V9M12 16V5M17 16v-4" />,
  log: <><path d="M5 4h14v16H5z" /><path d="M9 8h6M9 12h6M9 16h4" /></>,
  gear: <><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1" /></>,
  warn: <><path d="M12 3l9 16H3z" /><path d="M12 10v4M12 17v.01" /></>,
  check: <path d="M4 12.5l5 5L20 7" />,
  x: <path d="M6 6l12 12M18 6L6 18" />,
  play: <path d="M7 4v16l13-8z" />,
  plus: <path d="M12 5v14M5 12h14" />,
  arrow: <path d="M5 12h14M13 6l6 6-6 6" />,
  undo: <><path d="M8 5L4 9l4 4" /><path d="M4 9h10a6 6 0 010 12h-3" /></>,
};
export const Icon = ({ n }: { n: string }) => <svg className="i" viewBox="0 0 24 24" aria-hidden="true">{P[n]}</svg>;

// ---------- small UI ----------
export function Head({ title, sub, right, sim }: { title: string; sub?: string; right?: ReactNode; sim?: boolean }) {
  const { user } = useAuth();
  return (
    <div className="head">
      <div>
        <div className="row" style={{ gap: 10 }}><h1>{title}</h1>{sim && user?.role === 'admin' && <span className="simtag">Simulated</span>}</div>
        {sub && <p>{sub}</p>}
      </div>
      <div className="row">{right}</div>
    </div>
  );
}
export function Empty({ icon, title, text, children }: { icon: string; title: string; text: string; children?: ReactNode }) {
  return <div className="card"><div className="empty"><Icon n={icon} /><b>{title}</b><span>{text}</span>{children}</div></div>;
}
export function StatusPill({ s }: { s: string }) {
  const map: Record<string, [string, string]> = {
    running: ['acc dot', 'Working'], waiting_person: ['warn dot', 'Waiting for a person'], waiting_approval: ['warn dot', 'Waiting for approvals'],
    done: ['good', 'Finished'], no_action: ['', 'No action needed'],
  };
  const [c, t] = map[s] || ['', s];
  return <span className={'pill ' + c}>{t}</span>;
}
export function Banner({ kind, icon, children }: { kind: string; icon: string; children: ReactNode }) {
  return <div className={'banner ' + kind}><Icon n={icon} /><div>{children}</div></div>;
}
