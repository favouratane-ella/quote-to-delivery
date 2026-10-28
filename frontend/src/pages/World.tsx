import { Fragment, useEffect, useState } from 'react';
import { api } from '../api';
import { useAuth } from '../auth';
import { Banner, Empty, FLEX_LABEL, fmtDate, Head, hm, Icon, money, toast, usePoll } from '../lib';
import { useApp } from '../meta';

/* ---------------- Supplier mailbox ---------------- */
export function Mailbox({ selected }: { selected?: string }) {
  const { go, status, refresh } = useApp();
  const admin = useAuth().user?.role === 'admin';
  const [mail, reload] = usePoll<any[]>(() => api.get('/mailbox'), 2000);
  const [tpls] = usePoll<any[]>(() => api.get('/mailbox/templates'), 0);
  const [sups] = usePoll<any[]>(() => api.get('/suppliers'), 0);
  const compose = selected === 'compose';
  const cur = mail?.find((e) => String(e.id) === selected) || (!compose ? mail?.[0] : null);
  const [form, setForm] = useState({ key: 'big', sender: '', subject: '', body: '' });
  useEffect(() => {
    if (tpls && !form.sender) { const t = tpls.find((x) => x.key === 'big') || tpls[0]; setForm({ key: t.key, sender: t.sender, subject: t.subject, body: t.body }); }
  }, [tpls]); // eslint-disable-line react-hooks/exhaustive-deps
  const pick = (k: string) => { const t = tpls!.find((x) => x.key === k); setForm({ key: k, sender: t.sender, subject: t.subject, body: t.body }); };
  const send = async () => {
    try {
      await api.post('/mailbox', { sender: form.sender, subject: form.subject, body: form.body });
      const s = await api.get('/settings');
      toast(s.auto_run ? 'Sent. Processing now.' : 'Sent. Auto-run is off: process it by hand.');
      refresh();
      go(s.auto_run ? 'runs' : 'mailbox');
    } catch (e: any) { toast(e.message); }
  };
  const process = async (id: number) => { try { await api.post(`/mailbox/${id}/process`); refresh(); go('runs'); } catch (e: any) { toast(e.message); } };
  const processAll = async () => { await api.post('/mailbox/process-all'); refresh(); go('runs'); };
  const np = mail?.filter((e) => e.status === 'Not processed').length || 0;
  const pillCls = (s: string) => (s === 'Not processed' ? 'acc' : s.startsWith('Waiting') ? 'warn' : s.startsWith('Applied') ? 'good' : '');
  return (
    <>
      <Head title={admin ? 'Supplier mailbox' : 'Supplier inbox'} sim sub={admin ? 'The shared supply inbox. Play the supplier: send any email and watch what the agent does with it.' : 'New supplier emails. Processing reads each one and updates the ERP only when every check passes; anything uncertain comes to you.'}
        right={<>{np > 0 && <button className="btn pri" onClick={processAll}><Icon n="play" />Process all {np}</button>}{admin && <button className="btn" onClick={() => go('mailbox', 'compose')}><Icon n="plus" />Simulate a supplier email</button>}</>} />
      <div className="split">
        <div className="card"><div className="ch"><h2>Inbox</h2><span className="muted">{mail?.length ?? ''}</span></div>
          <div className="list">{(mail || []).map((e) => (
            <button key={e.id} className={'li ' + (!compose && cur?.id === e.id ? 'on' : '')} onClick={() => go('mailbox', e.id)}>
              <span className="t"><b>{e.sender}</b><span className={'pill ' + pillCls(e.status)}>{e.status}</span></span>
              <span className="s">{e.subject}</span><span className="s mono">{fmtDate(e.received_at.slice(0, 10))} {e.received_at.slice(11, 16)}</span>
            </button>))}</div></div>
        <div style={{ minWidth: 0 }}>
          {compose ? (
            <div className="card"><div className="ch"><h2>Write a supplier email</h2><span className="simtag">Simulated</span><span className="spacer" /><button className="btn sm ghost" onClick={() => go('mailbox')}>Cancel</button></div>
              <div className="cb">
                <div className="field"><label htmlFor="cm-tpl">Start from</label>
                  <select id="cm-tpl" value={form.key} onChange={(e) => pick(e.target.value)}>{(tpls || []).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}</select></div>
                <div className="fields">
                  <div className="field"><label htmlFor="cm-from">From supplier</label>
                    <select id="cm-from" value={form.sender} onChange={(e) => setForm({ ...form, sender: e.target.value })}>{(sups || []).map((s) => <option key={s.name}>{s.name}</option>)}</select></div>
                  <div className="field"><label htmlFor="cm-sub">Subject</label><input id="cm-sub" type="text" value={form.subject} onChange={(e) => setForm({ ...form, subject: e.target.value })} /></div>
                </div>
                <div className="field"><label htmlFor="cm-body">Message</label><textarea id="cm-body" rows={8} value={form.body} onChange={(e) => setForm({ ...form, body: e.target.value })} /></div>
                <div className="row"><button className="btn pri" onClick={send} disabled={!form.body.trim()}><Icon n="mail" />Send to the supply inbox</button>
                  <span className="muted" style={{ fontSize: 12.5 }}>{status?.ai_active ? 'Claude will read it.' : 'The rules engine will read it.'}</span></div>
              </div></div>
          ) : cur ? (
            <div className="card"><div className="ch"><h2>{cur.subject}</h2><span className="spacer" /><span className="muted mono" style={{ fontSize: 12 }}>{cur.address}</span></div>
              <div className="cb">
                <div className="mail">{cur.body}</div>
                {cur.attachment && (
                  <div className="doc"><div className="dh"><span className="ext">PDF</span>{cur.attachment.name}</div>
                    <div className="db"><h4>{cur.attachment.title}</h4><dl>{cur.attachment.rows.map((r: string[]) => <Fragment key={r[0]}><dt>{r[0]}</dt><dd>{r[1]}</dd></Fragment>)}</dl></div></div>)}
                {cur.run_id ? (
                  <Banner kind="acc" icon="runs">Processed: <b>{cur.status}</b>. <button className="btn sm" onClick={() => go('runs', cur.run_id)}>See what happened</button></Banner>
                ) : (
                  <div className="row"><button className="btn pri" onClick={() => process(cur.id)}><Icon n="play" />Process this email</button><span className="muted">Not processed yet.</span></div>
                )}
              </div></div>
          ) : null}
        </div>
      </div>
    </>
  );
}

/* ---------------- ERP ---------------- */
export function Erp({ selected }: { selected?: string }) {
  const { go, meta, refresh } = useApp();
  const admin = useAuth().user?.role === 'admin';
  const tab = selected || 'pos';
  const [pos, reloadPos] = usePoll<any[]>(() => api.get('/erp/purchase-orders'), 3000);
  const [orders, reloadOrders] = usePoll<any[]>(() => api.get('/erp/sales-orders'), 3000);
  const [items, reloadItems] = usePoll<any[]>(() => api.get('/erp/items'), 0);
  const [dates, setDates] = useState<Record<string, string>>({});
  const [stock, setStock] = useState<Record<string, string>>({});
  const [so, setSo] = useState({ customer_id: 'northwind', sku: 'CC-210', qty: '100', value: '15000', promised: '' });
  const saveDate = async (po: string, cur: string) => {
    const d = dates[po] || cur;
    try { const r = await api.put(`/erp/purchase-orders/${po}/arrival`, { date: d }); refresh(); reloadPos(); toast(r.agent_started ? 'Saved. Re-checking affected orders.' : 'Saved. Auto-run is off.'); if (r.agent_started) go('runs'); } catch (e: any) { toast(e.message); }
  };
  const saveStock = async (sku: string) => { try { await api.put(`/erp/items/${sku}`, { on_hand: Number(stock[sku]) }); reloadItems(); toast('Stock saved. Quote checks use it right away.'); } catch (e: any) { toast(e.message); } };
  const addSo = async () => {
    try { const r = await api.post('/erp/sales-orders', { ...so, qty: Number(so.qty), value: Number(so.value), promised: so.promised || meta?.next_week }); toast(`${r.so} added.`); reloadOrders(); reloadItems(); } catch (e: any) { toast(e.message); }
  };
  const tabs = [['pos', 'Purchase orders'], ['orders', 'Sales orders'], ['stock', 'Stock']];
  return (
    <>
      <Head title={admin ? 'ERP' : 'Purchase orders and stock'} sim sub="Stock, purchase orders and sales orders. Change a PO date here and every order that depends on it is re-checked." />
      <div className="card">
        <div className="tabs">{tabs.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => go('erp', k)}>{l}</button>)}</div>
        <div className="tscroll">
          {tab === 'pos' && <table className="tbl"><thead><tr><th>PO</th><th>Supplier</th><th>Item</th><th className="r">Qty</th><th>Arrival</th><th>Original</th><th>Change the arrival date</th></tr></thead>
            <tbody>{(pos || []).map((p) => <tr key={p.po} className={p.changed ? 'hl' : ''}><td className="mono">{p.po}</td><td>{p.supplier}</td><td className="mono">{p.sku}</td><td className="r num">{p.qty}</td>
              <td>{p.deliveries.map((d: any) => `${d.qty} on ${fmtDate(d.date)}`).join(', ')} {p.changed && <span className="pill acc">Changed</span>}</td>
              <td className="muted">{p.original.map((d: any) => fmtDate(d.date)).join(', ')}</td>
              <td><div className="row" style={{ flexWrap: 'nowrap' }}><input type="date" aria-label={'New arrival for ' + p.po} style={{ width: 150 }} value={dates[p.po] ?? p.arrival} onChange={(e) => setDates({ ...dates, [p.po]: e.target.value })} />
                <button className="btn sm" onClick={() => saveDate(p.po, p.arrival)}>Save</button></div></td></tr>)}</tbody></table>}
          {tab === 'orders' && <><table className="tbl"><thead><tr><th>Order</th><th>Customer</th><th>Item</th><th className="r">Qty</th><th className="r">Value</th><th>Supply</th><th>Promised</th><th>Arrives</th><th>Status</th></tr></thead>
            <tbody>{(orders || []).map((o) => <tr key={o.so} className={o.late ? 'hl' : ''}><td className="mono">{o.so}</td><td>{o.customer}</td><td className="mono">{o.sku}</td><td className="r num">{o.qty}</td><td className="r num">{money(o.value)}</td>
              <td className="mono" style={{ fontSize: 12 }}>{[o.stock_qty ? `${o.stock_qty} stock` : '', o.po_qty ? `${o.po_qty} ${o.po}` : ''].filter(Boolean).join(' + ')}</td>
              <td>{fmtDate(o.promised)}</td><td>{fmtDate(o.eta)}</td><td>{o.late ? <span className="pill bad">Late {o.days_late ?? ''}d</span> : <span className="pill good">On time</span>}</td></tr>)}</tbody></table>
            <div className="cb" style={{ borderTop: '1px solid var(--line)' }}><b>Add a sales order</b>
              <div className="fields5">
                <div className="field"><label htmlFor="so-c">Customer</label><select id="so-c" value={so.customer_id} onChange={(e) => setSo({ ...so, customer_id: e.target.value })}>{meta?.customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
                <div className="field"><label htmlFor="so-s">Item</label><select id="so-s" value={so.sku} onChange={(e) => setSo({ ...so, sku: e.target.value })}>{meta?.items.map((i) => <option key={i.sku}>{i.sku}</option>)}</select></div>
                <div className="field"><label htmlFor="so-q">Qty</label><input id="so-q" type="number" min={1} value={so.qty} onChange={(e) => setSo({ ...so, qty: e.target.value })} /></div>
                <div className="field"><label htmlFor="so-v">Value ($)</label><input id="so-v" type="number" min={0} value={so.value} onChange={(e) => setSo({ ...so, value: e.target.value })} /></div>
                <div className="field"><label htmlFor="so-d">Promised</label><input id="so-d" type="date" value={so.promised || meta?.next_week || ''} onChange={(e) => setSo({ ...so, promised: e.target.value })} /></div>
              </div>
              <div className="row"><button className="btn" onClick={addSo}><Icon n="plus" />Add order</button><span className="muted" style={{ fontSize: 12.5 }}>Free stock is used first, then the earliest PO with room.</span></div></div></>}
          {tab === 'stock' && <table className="tbl"><thead><tr><th>SKU</th><th>Item</th><th className="r">Reserved</th><th className="r">Free</th><th>On hand</th></tr></thead>
            <tbody>{(items || []).map((i) => <tr key={i.sku}><td className="mono">{i.sku}</td><td>{i.name}</td><td className="r num">{i.reserved}</td><td className="r num">{i.free}</td>
              <td><div className="row" style={{ flexWrap: 'nowrap' }}><input type="number" min={0} style={{ width: 110 }} aria-label={'On hand ' + i.sku} value={stock[i.sku] ?? String(i.on_hand)} onChange={(e) => setStock({ ...stock, [i.sku]: e.target.value })} />
                <button className="btn sm" onClick={() => saveStock(i.sku)}>Save</button></div></td></tr>)}</tbody></table>}
        </div>
      </div>
    </>
  );
}

/* ---------------- CRM ---------------- */
export function Crm({ selected }: { selected?: string }) {
  const { go } = useApp();
  const admin = useAuth().user?.role === 'admin';
  const tab = selected || 'customers';
  const [cs] = usePoll<any[]>(() => api.get('/crm/customers'), 0);
  const [notes] = usePoll<any[]>(() => api.get('/crm/notes'), 3000);
  const [quotes] = usePoll<any[]>(() => api.get('/crm/quotes'), 3000);
  const [lanes] = usePoll<any[]>(() => api.get('/erp/lanes'), 0);
  const laneDays = (l: string) => lanes?.find((x) => x.name === l)?.days;
  const tabs = [['customers', 'Customers'], ['notes', `Notes (${notes?.length ?? 0})`], ['quotes', 'Quotes']];
  return (
    <>
      <Head title={admin ? 'CRM' : 'Customers'} sim sub="Accounts, contacts, renewal dates and notes." />
      <div className="card">
        <div className="tabs">{tabs.map(([k, l]) => <button key={k} className={tab === k ? 'on' : ''} onClick={() => go('crm', k)}>{l}</button>)}</div>
        <div className="tscroll">
          {tab === 'customers' && <table className="tbl"><thead><tr><th>Customer</th><th>Tier</th><th className="r">Yearly value</th><th>Renewal</th><th>Contact</th><th>Owner</th><th>Lane</th><th>If delayed</th></tr></thead>
            <tbody>{(cs || []).map((c) => <tr key={c.id}><td>{c.name}</td><td>{c.tier}</td><td className="r num">{money(c.arr)}</td><td>{fmtDate(c.renewal)}</td>
              <td>{c.contact}<div className="muted mono" style={{ fontSize: 11.5 }}>{c.email}</div></td><td>{c.owner}</td><td>{c.lane} ({laneDays(c.lane)}d)</td>
              <td><span className={'st ' + (c.flex === 'hard' ? 'bad' : c.flex === 'partial' ? 'warn' : 'good')}>{FLEX_LABEL[c.flex]}</span>
                <div className="muted" style={{ fontSize: 11.5 }}>{c.flex === 'hard' ? c.hard_reason : `Can live with ${c.max_slip} days late`}</div></td></tr>)}</tbody></table>}
          {tab === 'notes' && (notes?.length ? <table className="tbl"><thead><tr><th>Time</th><th>Customer</th><th>Note</th></tr></thead>
            <tbody>{notes.map((n) => <tr key={n.id}><td className="mono muted">{hm(n.at)}</td><td>{n.customer}</td><td>{n.text}</td></tr>)}</tbody></table>
            : <div className="empty">Notes appear here when updates are sent and quotes are decided.</div>)}
          {tab === 'quotes' && <table className="tbl"><thead><tr><th>Quote</th><th>Customer</th><th>Item</th><th className="r">Qty</th><th>Requested</th><th>Status</th></tr></thead>
            <tbody>{(quotes || []).map((q) => <tr key={q.q}><td className="mono">{q.q}</td><td>{q.customer}</td><td className="mono">{q.sku}</td><td className="r num">{q.qty}</td><td>{fmtDate(q.requested)}</td><td>{q.status}</td></tr>)}</tbody></table>}
        </div>
      </div>
    </>
  );
}

/* ---------------- Customer outbox ---------------- */
export function Outbox() {
  const [msgs] = usePoll<any[]>(() => api.get('/outbox'), 3000);
  return (
    <>
      <Head title="Sent to customers" sim sub="What customers actually received. Nothing lands here unless a person approved or checked it." />
      {msgs && !msgs.length && <Empty icon="out" title="No customer emails yet" text="Approve a draft in Approvals and checks to see it arrive here." />}
      {(msgs || []).map((m) => (
        <div className="card" key={m.id}><div className="ch"><b>{m.subject}</b><span className="spacer" /><span className="muted" style={{ fontSize: 12.5 }}>To {m.to} · {hm(m.at)} · sent by {m.sent_by}</span></div>
          <div className="cb"><div className="mail">{m.body}</div></div></div>
      ))}
    </>
  );
}
