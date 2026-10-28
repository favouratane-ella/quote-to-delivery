import { useState } from 'react';
import { api } from '../api';
import { useAuth } from '../auth';
import { CASE_LABEL, FLEX_LABEL, fmtDate, hm, Icon, KIND_LABEL, money, RESOLUTION_LABEL, Risk, toast, typeLabel, usePoll } from '../lib';
import { useApp } from '../meta';

const STYLES: [string, string][] = [['accept', 'Accepts the date'], ['hard', 'Hard deadline'], ['partial', 'Wants part now'], ['expedite', 'Asks to expedite'], ['credit', 'Wants a credit'], ['cancel', 'Cancels'], ['question', 'Asks a question']];

function Thread({ d }: { d: any }) {
  const items = [
    ...d.messages.filter((x: any) => x.kind === 'customer').map((x: any) => ({ at: x.at, dir: 'out', title: x.subject, body: x.body, who: x.sent_by })),
    ...d.replies.map((x: any) => ({ at: x.at, dir: 'in', title: x.subject, body: x.body, who: x.contact, intent: x.intent })),
  ].sort((a, b) => a.at.localeCompare(b.at));
  if (!items.length) return <div className="empty"><span>No messages yet. The customer has not been told.</span></div>;
  return (
    <div className="thread">{items.map((m, i) => (
      <div key={i} className={'bubble ' + m.dir}>
        <div className="bh"><b>{m.dir === 'out' ? `From us${m.who ? ` (${m.who})` : ''}` : `${m.who || 'Customer'} replied`}</b>{m.intent && <span className="pill">{typeLabel(m.intent)}</span>}<span className="w">{hm(m.at)}</span></div>
        <div className="bt"><b>{m.title}</b>{'\n'}{m.body}</div>
      </div>))}
    </div>
  );
}

export default function OrderDetail({ id }: { id?: string }) {
  const { go, refresh } = useApp();
  const { user } = useAuth();
  const role = user?.role;
  const [d, reload] = usePoll<any>(() => api.get(`/cases/${id}`), 2500, [id]);
  const [pos] = usePoll<any[]>(() => api.get('/erp/purchase-orders'), 5000);
  const [runs] = usePoll<any[]>(() => api.get('/runs'), 5000);
  const [reply, setReply] = useState('');
  const [style, setStyle] = useState('accept');
  const [open, setOpen] = useState<number | null>(null);
  if (!d) return <span className="thinking">Loading</span>;
  const { order: o, customer: c, case: cs } = d;
  const po = pos?.find((p) => p.po === o.po);
  const run = (runs || []).find((r) => r.result?.affected?.includes(o.so));
  const emailId = run?.trigger?.type === 'email' ? run.trigger.email_id : null;
  const live = cs && cs.status !== 'resolved';
  const pend = d.proposals.filter((p: any) => p.status === 'Proposed');
  const canLog = live && (role === 'manager' || role === 'sales' || role === 'admin');
  const send = async () => { try { await api.post('/replies', { so: o.so, body: reply }); setReply(''); toast('Reply added. The agent is reading it.'); refresh(); setTimeout(reload, 800); } catch (e: any) { toast(e.message); } };
  const sim = async () => { try { await api.post('/replies/simulate', { so: o.so, style }); toast('Customer replied. The agent is reading it.'); refresh(); setTimeout(reload, 800); } catch (e: any) { toast(e.message); } };
  const stage = cs ? (cs.status === 'resolved' ? RESOLUTION_LABEL[cs.resolution] || 'Resolved' : CASE_LABEL[cs.status]) : null;

  return (
    <>
      <div>
        <button className="back" onClick={() => go('orders')}><Icon n="arrow" />Orders</button>
        <div className="ph">
          <div className="grow"><h1>{o.so} · {o.customer}</h1>
            <p>{o.qty.toLocaleString()} x {o.sku} · {money(o.value)} · <Risk tier={o.risk} /> <span className="muted">· {o.risk_why}</span></p></div>
          {pend.length > 0 && <button className="btn pri" onClick={() => go('approvals', 'p' + pend[0].id)}>Review {pend.length === 1 ? 'recovery plan' : `${pend.length} plans`}</button>}
        </div>
      </div>

      <div className="opage">
        <div className="stack">
          <div className="card">
            <div className="hero">
              <div><span>Promised</span><b>{fmtDate(o.promised)}</b>{o.original_promised && <span className="muted">was {fmtDate(o.original_promised)}</span>}</div>
              <div><span>Now arriving</span><b className={o.late ? 'bad' : 'good'}>{fmtDate(o.eta)}</b></div>
              <div><span>Status</span><b className={o.late ? 'bad' : 'good'}>{o.late ? `${o.days_late} ${o.days_late === 1 ? 'day' : 'days'} late` : 'On time'}</b>{stage && <span className="muted">{stage}</span>}</div>
            </div>
          </div>

          {d.lines.length > 1 && (
            <div className="card"><div className="ch"><h2>Order lines</h2><span className="muted">This order was split with the customer's agreement</span></div>
              <table className="tbl"><thead><tr><th>Line</th><th>Item</th><th className="r">Qty</th><th>Promised</th><th>Note</th></tr></thead>
                <tbody>{d.lines.map((l: any) => <tr key={l.so} className="click" onClick={() => l.so !== o.so && go('order', l.so)}><td className="mono"><b>{l.so}</b></td><td className="mono">{l.sku}</td><td className="r num">{l.qty.toLocaleString()}</td><td>{fmtDate(l.promised)}</td><td className="muted">{l.note}</td></tr>)}</tbody></table></div>
          )}

          {d.options && (
            <div className="card">
              <div className="ch"><h2>Ways to rescue this order</h2><span className="muted">Live: recalculated from current stock and supply</span></div>
              <div className="tscroll"><table className="tbl">
                <thead><tr><th>Option</th><th>Arrives</th><th>Keeps the date</th><th className="r">Cost</th><th>Who decides</th></tr></thead>
                <tbody>{d.options.options.map((x: any, i: number) => (<>
                  <tr key={x.kind} className="click" onClick={() => setOpen(open === i ? null : i)}>
                    <td><b>{x.title}</b>{x.recommended && <span className="pill acc" style={{ marginLeft: 8 }}>Recommended</span>}{x.needs_customer_ok && <span className="sub2">Customer must agree</span>}</td>
                    <td>{x.new_eta ? fmtDate(x.new_eta) : '-'}</td>
                    <td>{x.meets_promised ? <span className="st good">Yes</span> : <span className="st">No</span>}</td>
                    <td className="r num">{x.cost ? money(x.cost) : '-'}</td><td>{x.needs}</td>
                  </tr>
                  {open === i && <tr key={x.kind + 'd'}><td colSpan={5} style={{ background: 'var(--bg)' }}><div style={{ padding: '2px 4px' }}>{x.summary}<ul className="reasons">{x.side_effects.map((s: string, j: number) => <li key={j}>{s}</li>)}</ul></div></td></tr>}
                </>))}</tbody>
              </table></div>
              {d.options.escalate && <div className="banner warn" style={{ margin: 16 }}><Icon n="warn" /><div><b>No option keeps {fmtDate(d.options.promised)}.</b> {c.flex === 'hard' ? `${c.hard_reason} ` : ''}A person has to decide how to handle this customer.</div></div>}
            </div>
          )}

          <div className="card">
            <div className="ch"><h2>Conversation</h2></div>
            <div className="cb"><Thread d={d} />
              {canLog && (
                <div className="section" style={{ borderTop: '1px solid var(--line)', paddingTop: 12 }}>
                  <h3>Log what the customer said</h3>
                  <textarea rows={3} aria-label="Customer reply" placeholder="Paste or type the customer's reply. The agent reads it and recommends what to do." value={reply} onChange={(e) => setReply(e.target.value)} />
                  <div className="actions"><button className="btn pri" disabled={reply.trim().length < 2} onClick={send}>Add reply</button>
                    {role === 'admin' && <><span className="muted">or simulate</span><select style={{ width: 'auto' }} aria-label="Customer style" value={style} onChange={(e) => setStyle(e.target.value)}>{STYLES.map(([k, l]) => <option key={k} value={k}>{l}</option>)}</select><button className="btn" onClick={sim}>Simulate reply</button></>}</div>
                </div>)}
            </div>
          </div>

          <div className="card">
            <div className="ch"><h2>Timeline</h2></div>
            {d.events.length ? <ol className="tline">{d.events.map((e: any, i: number) => (
              <li key={i} className={i === d.events.length - 1 && live ? 'now' : 'done'}><span className="pt" /><div><b>{e.text}</b><span className="s">{e.actor}</span></div><span className="w">{hm(e.at)}</span></li>))}</ol>
              : <div className="empty"><span>No changes yet. This order is on its original plan.</span></div>}
          </div>
        </div>

        <div className="stack">
          <div className="card">
            <div className="ch"><h2>What this customer can take</h2></div>
            <div className="cb" style={{ gap: 8 }}>
              <span className={'st ' + (c.flex === 'hard' ? 'bad' : c.flex === 'partial' ? 'warn' : 'good')} style={{ fontWeight: 600 }}>{FLEX_LABEL[c.flex]}</span>
              <span className="muted" style={{ fontSize: 13 }}>{c.flex === 'hard' ? c.hard_reason : c.flex === 'partial' ? `Will take a part delivery. Can live with the rest up to ${c.max_slip} days late.` : `Can live with up to ${c.max_slip} days late.`}</span>
            </div>
          </div>
          <div className="card">
            <div className="ch"><h2>Supply</h2></div>
            {po ? (
              <div className="props">
                <div><span>Purchase order</span><b><a onClick={() => go('erp', po.po)}>{po.po}</a></b></div>
                <div><span>Supplier</span><b>{po.supplier}</b></div>
                <div><span>Supplier date</span><b>{po.changed ? `${fmtDate(po.original[0]?.date)} to ${fmtDate(po.arrival)}` : fmtDate(po.arrival)}</b></div>
                {emailId && <div><span>Caused by</span><b><a onClick={() => go('mailbox', emailId)}>Supplier email</a></b></div>}
              </div>
            ) : <div className="props"><div><span>Source</span><b>Ships from stock</b></div></div>}
          </div>
          <div className="card">
            <div className="ch"><h2>Customer</h2></div>
            <div className="props">
              <div><span>Account</span><b><a onClick={() => go('crm', o.customer_id)}>{o.customer}</a></b></div>
              <div><span>Contact</span><b>{c.contact}</b></div><div><span>Account owner</span><b>{c.owner}</b></div>
              <div><span>Tier</span><b>{c.tier}</b></div><div><span>Yearly value</span><b>{money(c.arr)}</b></div><div><span>Renewal</span><b>{fmtDate(c.renewal)}</b></div>
            </div>
          </div>
          {d.proposals.length > 0 && (
            <div className="card">
              <div className="ch"><h2>Recovery actions</h2></div>
              <div className="rows">{d.proposals.map((p: any) => (
                <button key={p.id} className="row2" onClick={() => go('approvals', 'p' + p.id)}>
                  <span className="tx"><b>{KIND_LABEL[p.kind] || p.kind}</b><span>{p.title}</span></span>
                  <span className="meta"><span className={'st ' + (p.status === 'Applied' ? 'good' : p.status === 'Rejected' ? 'bad' : p.status === 'Offered' ? 'acc' : 'warn')}>{p.status}</span></span>
                </button>))}</div>
            </div>
          )}
        </div>
      </div>
    </>
  );
}
