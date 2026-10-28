import { api, Run } from '../api';
import { Role, useAuth } from '../auth';
import { fmtDate, Icon, KIND_LABEL, money, usePoll } from '../lib';
import { useApp } from '../meta';

type Item = { tone: '' | 'warn' | 'bad'; icon: string; title: string; sub: string; to: string; id?: string | number; meta?: [string, string] };

const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening'; };
// Pipeline stages each role looks after.
const OWNS: Record<Role, string[]> = { planner: ['inbox'], manager: ['actions'], sales: ['replies'], admin: [] };
const REACH: Record<string, string[]> = { planner: ['mailbox', 'orders', 'approvals'], manager: ['approvals', 'orders', 'replies'], sales: ['orders', 'replies'] };
const mayDecide = (role: Role, needs: string) => role === 'admin' || (needs === 'Planner' && role === 'planner') || (needs === 'Ops manager' && role === 'manager') || (needs === 'Account manager' && (role === 'manager' || role === 'sales'));

const START: Record<Role, [string, string, string][]> = {
  planner: [['Process the supplier emails', 'Each email is read and checked. The ERP changes only when every check passes.', 'mailbox'], ['Check anything uncertain', 'Notes and emails the agent cannot confirm come to you.', 'mailbox'], ['Watch the inventory', 'Items at their reorder point get a purchase order proposed for you.', 'inventory']],
  manager: [['Wait for the emails to be processed', 'The planner processes supplier emails. Late orders and draft updates appear here.', 'orders'], ['Approve updates and recovery plans', 'Large orders and anything costing money need your decision.', 'approvals'], ['Follow what customers say', 'Replies are read and turned into recovery plans.', 'replies']],
  sales: [['Check a quote before you promise a date', 'Each quote is checked against stock and inbound purchase orders.', 'quotes'], ['Handle customer replies', 'When a customer answers a delay notice, the agent recommends what to do.', 'replies'], ['Know the customer', 'Contacts, owners and what each customer can take are under Customers.', 'crm']],
  admin: [['Process the supplier emails', 'Read each email and update the ERP when every check passes.', 'mailbox'], ['Approve updates and plans', 'Nothing is sent or changed without a person.', 'approvals'], ['Run the test scenarios', 'Thirty-one situations check the system still behaves.', 'scen']],
};

export default function Home() {
  const { user } = useAuth();
  const { status, go } = useApp();
  const role = user?.role as Role;
  const [orders] = usePoll<any[]>(() => api.get('/erp/sales-orders'), 4000);
  const [quotes] = usePoll<any[]>(() => api.get('/crm/quotes'), 4000);
  const [approvals] = usePoll<any[]>(() => api.get('/approvals'), 3000);
  const [runs] = usePoll<Run[]>(() => api.get('/runs'), 3000);
  const [outbox] = usePoll<any[]>(() => api.get('/outbox'), 6000);
  const [cases] = usePoll<any[]>(() => api.get('/cases'), 3000);
  const [props] = usePoll<any[]>(() => api.get('/proposals'), 3000);
  const [replies] = usePoll<any[]>(() => api.get('/replies'), 3000);
  const [inv] = usePoll<any[]>(() => api.get('/erp/inventory'), 6000);
  if (!user) return null;

  const c = status?.counts;
  const all = orders || [];
  const atRisk = all.filter((o) => o.late || (o.case_status && o.case_status !== 'resolved'));
  const revenueAtRisk = atRisk.filter((o) => o.late).reduce((s, o) => s + o.value, 0);
  const lateCustomers = new Set(atRisk.map((o) => o.customer_id)).size;
  const resolved = (cases || []).filter((x) => x.status === 'resolved');
  const told = (cases || []).filter((x) => x.status === 'notified' || x.status === 'offer_sent');
  const onTime = all.length ? Math.round(((all.length - all.filter((o) => o.late).length) / all.length) * 100) : 100;
  const open = (approvals || []).filter((a) => a.status === 'Needs approval' || a.status === 'Ready');
  const needMgr = open.filter((a) => a.status === 'Needs approval');
  const mine = (props || []).filter((p) => p.status === 'Proposed' && mayDecide(role, p.needs));
  const allActions = (props || []).filter((p) => p.status === 'Proposed');
  const toCheck = (runs || []).filter((r) => r.status === 'waiting_person' && r.trigger?.type === 'email');
  const replyAttn = (replies || []).filter((r) => r.status === 'New' || r.status === 'Needs a person');
  const quotesTodo = (quotes || []).filter((q) => q.status === 'Not checked');
  const quotesChoose = (runs || []).filter((r) => r.status === 'waiting_person' && r.trigger?.type === 'quote');
  const reorder = (inv || []).filter((r) => r.status !== 'Healthy');
  const sent = outbox?.filter((m) => m.kind !== 'supplier').length ?? 0;
  const fresh = !!c && c.runs === 0;
  const waitingYou = (role === 'manager' ? needMgr.length : role === 'sales' ? open.filter((a) => a.status === 'Ready').length : role === 'admin' ? open.length : 0) + mine.length;

  const stats: Record<Role, { l: string; v: string | number; d: string; to: string; tone?: string }[]> = {
    planner: [
      { l: 'Emails to process', v: c?.unprocessed ?? 0, d: 'from suppliers and the warehouse', to: 'mailbox' },
      { l: 'Needs checking', v: toCheck.length, d: 'could not be confirmed', to: 'mailbox', tone: toCheck.length ? 'warn' : '' },
      { l: 'Waiting for you', v: waitingYou, d: 'orders, replans and purchases', to: 'approvals', tone: waitingYou ? 'warn' : '' },
      { l: 'Items to reorder', v: reorder.length, d: reorder.length ? reorder.map((r) => r.sku).slice(0, 2).join(', ') : 'all healthy', to: 'inventory', tone: reorder.length ? 'warn' : '' },
    ],
    manager: [
      { l: 'Waiting for you', v: waitingYou, d: 'updates and recovery plans', to: 'approvals', tone: waitingYou ? 'warn' : '' },
      { l: 'Revenue at risk', v: money(revenueAtRisk), d: `${atRisk.filter((o) => o.late).length} late orders`, to: 'orders', tone: revenueAtRisk ? 'bad' : '' },
      { l: 'Recovered', v: resolved.length, d: 'orders back to low risk', to: 'orders' },
      { l: 'On time', v: `${onTime}%`, d: `${all.length - all.filter((o) => o.late).length} of ${all.length} orders`, to: 'orders' },
    ],
    sales: [
      { l: 'Quotes to check', v: quotesTodo.length, d: 'waiting', to: 'quotes', tone: quotesTodo.length ? 'warn' : '' },
      { l: 'Replies to read', v: replyAttn.length, d: 'from customers', to: 'replies', tone: replyAttn.length ? 'warn' : '' },
      { l: 'Customers affected', v: lateCustomers, d: money(revenueAtRisk) + ' at risk', to: 'orders', tone: lateCustomers ? 'bad' : '' },
      { l: 'Recovered', v: resolved.length, d: 'orders back to low risk', to: 'orders' },
    ],
    admin: [
      { l: 'Emails to process', v: c?.unprocessed ?? 0, d: 'from suppliers and the warehouse', to: 'mailbox' },
      { l: 'Waiting for approval', v: open.length + allActions.length, d: `${allActions.length} recovery and supply actions`, to: 'approvals', tone: open.length + allActions.length ? 'warn' : '' },
      { l: 'Orders at risk', v: atRisk.length, d: atRisk.length ? money(revenueAtRisk) + ' late' : 'none late', to: 'orders', tone: atRisk.length ? 'bad' : '' },
      { l: 'Recovered', v: resolved.length, d: `${onTime}% of orders on time`, to: 'orders' },
    ],
  };

  const items: Item[] = [];
  const planner = () => {
    if (c?.unprocessed) items.push({ tone: '', icon: 'mail', title: `${c.unprocessed} ${c.unprocessed === 1 ? 'email' : 'emails'} to process`, sub: 'Read and checked before the ERP changes', to: 'mailbox' });
    toCheck.forEach((r) => items.push({ tone: 'warn', icon: 'warn', title: r.title.replace(/^Supplier email: /, ''), sub: 'Could not be confirmed. Confirm, correct or dismiss', to: 'mailbox', id: r.trigger.email_id }));
    mine.filter((p) => p.needs === 'Planner').forEach((p) => items.push({ tone: 'warn', icon: 'box', title: p.title, sub: p.summary, to: 'approvals', id: 'p' + p.id }));
  };
  const manager = () => {
    needMgr.forEach((a) => items.push({ tone: 'warn', icon: 'approve', title: `${a.customer}: update for ${a.so}`, sub: a.reason, to: 'approvals', id: a.id, meta: [money(a.value), 'Needs approval'] }));
    mine.filter((p) => p.needs === 'Ops manager').forEach((p) => items.push({ tone: p.kind === 'escalate' ? 'bad' : 'warn', icon: 'warn', title: `${KIND_LABEL[p.kind]}: ${p.customer || ''} ${p.so}`.trim(), sub: p.title, to: 'approvals', id: 'p' + p.id, meta: p.value ? [money(p.value), p.needs] : undefined }));
    (replies || []).filter((r) => r.status === 'Needs a person').forEach((r) => items.push({ tone: 'warn', icon: 'agent', title: `${r.customer} replied on ${r.so}`, sub: 'The agent could not read it. Tell it what the customer means', to: 'replies', id: r.id }));
  };
  const sales = () => {
    quotesTodo.forEach((q) => items.push({ tone: '', icon: 'quote', title: `Quote ${q.q} for ${q.customer}`, sub: `${q.qty.toLocaleString()} x ${q.sku}, wanted by ${fmtDate(q.requested)}`, to: 'quotes', id: q.q }));
    quotesChoose.forEach((r) => items.push({ tone: 'warn', icon: 'quote', title: `Choose a date for ${r.trigger.q}`, sub: 'Options are ready', to: 'quotes', id: r.trigger.q }));
    (replies || []).filter((r) => r.status === 'Needs a person').forEach((r) => items.push({ tone: 'warn', icon: 'agent', title: `${r.customer} replied on ${r.so}`, sub: 'The agent could not read it. Tell it what the customer means', to: 'replies', id: r.id }));
    mine.filter((p) => p.needs === 'Account manager').forEach((p) => items.push({ tone: '', icon: 'approve', title: `${KIND_LABEL[p.kind]}: ${p.customer || ''} ${p.so}`.trim(), sub: p.title, to: 'approvals', id: 'p' + p.id }));
  };
  if (role === 'planner') planner(); else if (role === 'manager') manager(); else if (role === 'sales') sales(); else { planner(); manager(); sales(); }

  const stages = [
    { k: 'inbox', t: 'Supplier emails', n: c?.unprocessed ?? 0, to: 'mailbox', h: 'to process' },
    { k: 'risk', t: 'Orders at risk', n: atRisk.length, to: 'orders', h: atRisk.length ? money(revenueAtRisk) + ' late' : 'none late' },
    { k: 'told', t: 'Customer told', n: told.length, to: 'orders', h: 'waiting for a reply' },
    { k: 'replies', t: 'Replies to read', n: replyAttn.length, to: 'replies', h: `${replies?.length ?? 0} so far` },
    { k: 'actions', t: 'Recovery actions', n: allActions.length, to: 'approvals', h: 'waiting for approval' },
    { k: 'done', t: 'Back to low risk', n: resolved.length, to: 'orders', h: `${sent} updates sent` },
  ];
  const canOpen = (to: string) => role === 'admin' || (REACH[role] || []).includes(to);

  return (
    <>
      <div className="ph">
        <div className="grow"><h1>{greeting()}, {user.name.split(' ')[0]}</h1><p>{status?.today_label}{' '}· {items.length ? `${items.length} ${items.length === 1 ? 'item needs' : 'items need'} your attention` : 'nothing needs you right now'}</p></div>
        {(role === 'planner' || role === 'admin') && !!c?.unprocessed && <button className="btn pri" onClick={() => go('mailbox')}><Icon n="mail" />Process emails</button>}
        {role === 'sales' && !!quotesTodo.length && <button className="btn pri" onClick={() => go('quotes')}><Icon n="quote" />Check quotes</button>}
        {role === 'manager' && !!waitingYou && <button className="btn pri" onClick={() => go('approvals')}><Icon n="approve" />Review approvals</button>}
      </div>

      <div className="stats">{stats[role].map((s) => (
        <button key={s.l} className={'stat ' + (s.tone || '')} onClick={() => go(s.to)}><span className="l">{s.l}</span><b>{s.v}</b><span className="d">{s.d}</span></button>))}</div>

      <div className="ovgrid">
        <div className="card">
          <div className="ch"><h2>Needs your attention</h2><span className="muted">{items.length}</span></div>
          {items.length ? <div className="rows">{items.slice(0, 7).map((t, i) => (
            <button key={i} className={'row2 ' + t.tone} onClick={() => go(t.to, t.id)}>
              <span className="ico"><Icon n={t.icon} /></span>
              <span className="tx"><b>{t.title}</b><span>{t.sub}</span></span>
              {t.meta ? <span className="meta"><b>{t.meta[0]}</b><span>{t.meta[1]}</span></span> : null}
              <span className="go"><Icon n="arrow" /></span>
            </button>))}
            {items.length > 7 && <div className="row2 muted" style={{ cursor: 'default' }}>and {items.length - 7} more</div>}</div>
            : <div className="empty"><Icon n="check" /><b>All caught up</b><span>New supplier emails, customer replies and quotes show up here.</span></div>}
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 16, minWidth: 0 }}>
          <div className="card">
            <div className="ch"><h2>Orders at risk</h2><span className="spacer" /><button className="btn sm ghost" onClick={() => go('orders')}>View all</button></div>
            {atRisk.length ? <div className="rows">{[...atRisk].sort((a, b) => ['Critical', 'High', 'Medium', 'Watch', 'Low'].indexOf(a.risk) - ['Critical', 'High', 'Medium', 'Watch', 'Low'].indexOf(b.risk) || b.value - a.value).slice(0, 4).map((o) => (
              <button key={o.so} className="row2" onClick={() => go('order', o.so)}>
                <span className="tx"><b>{o.customer}</b><span className="mono">{o.so} · {o.case_status === 'escalated' ? 'escalated' : o.po || 'stock'}</span></span>
                <span className="meta"><b>{money(o.value)}</b><span className={'st ' + (o.risk === 'Critical' || o.risk === 'High' ? 'bad' : 'warn')}>{o.risk}{o.days_late ? ` · ${o.days_late}d late` : ''}</span></span></button>))}</div>
              : <div className="empty"><b>No orders at risk</b><span>{fresh ? 'This changes when a supplier moves a delivery date.' : 'Every open order arrives on time.'}</span></div>}
          </div>
          {fresh && (
            <div className="card">
              <div className="ch"><h2>Where to start</h2></div>
              <ol className="checklist">{START[role].map(([t, s, to], i) => (
                <li key={t}><span className="sn">{i + 1}</span><div><b>{canOpen(to) ? <a onClick={() => go(to)}>{t}</a> : t}</b><span className="s">{s}</span></div></li>))}</ol>
            </div>
          )}
        </div>
      </div>

      <div className="card">
        <div className="ch"><h2>Order pipeline</h2><span className="muted">From a supplier email to an order back at low risk. {role === 'admin' ? 'Select a stage to open it.' : 'Your stage is marked.'}</span></div>
        <div className="pipeline flat">{stages.map((s) => (
          <button key={s.k} className={(canOpen(s.to) ? 'can ' : '') + (OWNS[role].includes(s.k) ? 'mine' : '')} disabled={!canOpen(s.to)} onClick={() => go(s.to)}>
            <span className="t">{s.t}</span><span className="n">{s.n}</span><span className="hint">{s.h}</span></button>))}</div>
      </div>
    </>
  );
}
