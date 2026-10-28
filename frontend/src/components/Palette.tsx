import { useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api';
import { NAV, Role } from '../auth';
import { fmtDate, Icon, money } from '../lib';

type Hit = { g: string; label: string; sub?: string; to: string; id?: string | number; ask?: boolean; icon: string };

export default function Palette({ role, go, onClose }: { role: Role; go: (v: string, id?: string | number) => void; onClose: () => void }) {
  const [q, setQ] = useState('');
  const [sel, setSel] = useState(0);
  const [data, setData] = useState<{ orders: any[]; pos: any[]; custs: any[]; mail: any[] }>({ orders: [], pos: [], custs: [], mail: [] });
  const [answer, setAnswer] = useState<string | null>(null);
  const [asking, setAsking] = useState(false);
  const input = useRef<HTMLInputElement>(null);
  useEffect(() => {
    input.current?.focus();
    Promise.all([api.get('/erp/sales-orders'), api.get('/erp/purchase-orders'), api.get('/crm/customers'), api.get('/mailbox')])
      .then(([orders, pos, custs, mail]) => setData({ orders, pos, custs, mail })).catch(() => {});
  }, []);

  const pages = NAV[role].filter((n) => n[0] !== 'grp' && n[0] !== 'home') as [string, string, string][];
  const hits = useMemo<Hit[]>(() => {
    const s = q.trim().toLowerCase();
    const out: Hit[] = [];
    const has = (v: string) => v.toLowerCase().includes(s);
    if (!s) return pages.map(([k, l, i]) => ({ g: 'Go to', label: l, to: k, icon: i }));
    pages.filter(([, l]) => has(l)).forEach(([k, l, i]) => out.push({ g: 'Go to', label: l, to: k, icon: i }));
    if (role !== 'sales' || true) data.orders.filter((o) => has(o.so + ' ' + o.customer + ' ' + o.sku)).slice(0, 5).forEach((o) => out.push({ g: 'Orders', label: `${o.so} · ${o.customer}`, sub: o.late ? `${o.days_late} days late` : 'On time', to: 'order', id: o.so, icon: 'warn' }));
    data.custs.filter((c) => has(c.name + ' ' + c.contact)).slice(0, 4).forEach((c) => out.push({ g: 'Customers', label: c.name, sub: `Tier ${c.tier} · renews ${fmtDate(c.renewal)}`, to: 'crm', id: c.id, icon: 'crm' }));
    data.pos.filter((p) => has(p.po + ' ' + p.supplier)).slice(0, 4).forEach((p) => out.push({ g: 'Purchase orders', label: `${p.po} · ${p.supplier}`, sub: `arrives ${fmtDate(p.arrival)}`, to: 'erp', id: p.po, icon: 'erp' }));
    data.mail.filter((m) => has(m.subject + ' ' + m.sender)).slice(0, 4).forEach((m) => out.push({ g: 'Supplier emails', label: m.subject, sub: m.sender, to: 'mailbox', id: m.id, icon: 'mail' }));
    return out.filter((h) => NAV[role].some((n) => n[0] === h.to || (h.to === 'order' && n[0] === 'orders'))).concat([{ g: 'Ask', label: `Ask: ${q.trim()}`, sub: 'Answers from live ERP and CRM data', to: '', ask: true, icon: 'agent' }]);
  }, [q, data, role]); // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => { setSel(0); setAnswer(null); }, [q]);
  const run = async (h: Hit) => {
    if (!h.ask) { onClose(); go(h.to, h.id); return; }
    setAsking(true);
    try { const r = await api.post('/chat', { messages: [{ role: 'user', content: q.trim() }] }); setAnswer(r.reply); } catch (e: any) { setAnswer(e.message); }
    setAsking(false);
  };
  const key = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') onClose();
    else if (e.key === 'ArrowDown') { e.preventDefault(); setSel((s) => Math.min(s + 1, hits.length - 1)); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); setSel((s) => Math.max(s - 1, 0)); }
    else if (e.key === 'Enter' && hits[sel]) run(hits[sel]);
  };
  let last = '';
  return (
    <div className="palette-bg" onMouseDown={onClose}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Search" onMouseDown={(e) => e.stopPropagation()}>
        <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} onKeyDown={key} placeholder="Search orders, customers and purchase orders, or ask a question" aria-label="Search" />
        <div className="res">
          {hits.map((h, i) => {
            const head = h.g !== last ? <div className="gh" key={'g' + h.g}>{h.g}</div> : null; last = h.g;
            return <div key={i}>{head}<button className={'it ' + (i === sel ? 'on' : '')} onMouseEnter={() => setSel(i)} onClick={() => run(h)}><Icon n={h.icon} /><span>{h.label}</span>{h.sub && <span className="sub2">{h.sub}</span>}</button></div>;
          })}
          {!hits.length && <div className="gh">No matches</div>}
        </div>
        {(asking || answer) && <div className="ans">{asking ? 'Looking it up' : answer}</div>}
        <div className="ft"><span>↑↓ to move</span><span>Enter to open</span><span>Esc to close</span></div>
      </div>
    </div>
  );
}
