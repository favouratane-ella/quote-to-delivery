import { useState } from 'react';
import { api } from '../api';
import { Role, useAuth } from '../auth';
import { fmtDate, hm, Icon, KIND_LABEL, money, toast, usePoll } from '../lib';
import { useApp } from '../meta';

const isOpen = (a: any) => a.status === 'Needs approval' || a.status === 'Ready';
const mayDecide = (role: Role | undefined, needs: string) =>
  role === 'admin' || (needs === 'Planner' && role === 'planner') || (needs === 'Ops manager' && role === 'manager') || (needs === 'Account manager' && (role === 'manager' || role === 'sales'));
const tone = (s: string) => (s === 'Sent' || s === 'Applied' ? 'good' : s === 'Rejected' ? 'bad' : s === 'Offered' ? 'acc' : 'warn');

/* ---- a customer update drafted after a supplier delay ---- */
function UpdatePane({ a, onDone }: { a: any; onDone: () => void }) {
  const { go } = useApp();
  const open = isOpen(a);
  const [subject, setSubject] = useState(a.subject);
  const [body, setBody] = useState(a.body);
  const [note, setNote] = useState(a.note);
  const [busy, setBusy] = useState(false);
  const act = async (send: boolean) => {
    setBusy(true);
    try {
      await api.post(`/approvals/${a.id}/${send ? 'send' : 'reject'}`, send ? { subject, body, note } : {});
      toast(send ? `Sent to ${a.contact} at ${a.customer}. The customer will reply.` : 'Rejected. Nothing was sent.');
      onDone();
    } catch (e: any) { toast(e.message); }
    setBusy(false);
  };
  return (
    <>
      <div className="detail">
        <div>
          <div className="dmeta" style={{ marginBottom: 4 }}><span className="pill">Customer update</span><span className={'st ' + tone(a.status === 'Needs approval' ? 'x' : a.status)}>{a.status}</span>
            <span><a onClick={() => go('order', a.so)}>{a.so}</a></span><span><b>{money(a.value)}</b> order</span></div>
          <h2 className="dt">{a.customer}</h2>
          <div className="dmeta" style={{ marginTop: 4 }}><span>To <b>{a.contact}</b></span><span>{a.email}</span><span>New date <b>{fmtDate(a.new_date)}</b></span></div>
        </div>
        <div className="banner acc"><Icon n={a.status === 'Needs approval' ? 'warn' : 'check'} /><div><b>Why this is here.</b> {a.reason}.{a.wording_ok ? ' The wording check passed: it states the order and the new date.' : ' The wording check failed, so please read it carefully.'}</div></div>
        {open ? (<>
          <div className="section"><h3>Subject</h3><input type="text" aria-label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} /></div>
          <div className="section"><h3>Message</h3><textarea rows={11} aria-label="Message" value={body} onChange={(e) => setBody(e.target.value)} /></div>
          <details><summary>Note saved to the CRM</summary><div className="section" style={{ marginTop: 8 }}><input type="text" aria-label="CRM note" value={note} onChange={(e) => setNote(e.target.value)} /></div></details>
        </>) : (<>
          <div className="section"><h3>Subject</h3><div>{a.subject}</div></div>
          <pre className="draft">{a.body}</pre>
          <div className="muted">{a.status} by {a.decided_by || 'a person'}{a.decided_at ? ` at ${hm(a.decided_at)}` : ''}.</div>
        </>)}
      </div>
      {open && <div className="stickybar">
        <button className="btn pri" disabled={busy} onClick={() => act(true)}>{a.status === 'Needs approval' ? 'Approve and send' : 'Send'}</button>
        <button className="btn" disabled={busy} onClick={() => act(false)}>Reject</button>
        <span className="spacer" /><button className="btn ghost" onClick={() => go('order', a.so)}>View order</button>
      </div>}
    </>
  );
}

/* ---- a recovery action the agent recommends ---- */
function ProposalPane({ p, onDone }: { p: any; onDone: () => void }) {
  const { go } = useApp();
  const open = p.status === 'Proposed';
  const d = p.detail || {};
  const [subject, setSubject] = useState(p.subject);
  const [body, setBody] = useState(p.body);
  const [busy, setBusy] = useState(false);
  const internal = p.kind === 'escalate' || p.kind === 'resupply';
  const toSupplier = p.kind === 'supplier' || p.kind === 'raise_po';
  const act = async (ok: boolean) => {
    setBusy(true);
    try {
      const r = await api.post(`/proposals/${p.id}/${ok ? 'approve' : 'reject'}`, ok ? { subject, body } : {});
      toast(!ok ? 'Rejected. Nothing changed.' : r.status === 'Offered' ? 'Offer sent. Nothing changes until the customer says yes.' : 'Approved and applied.');
      onDone();
    } catch (e: any) { toast(e.message); }
    setBusy(false);
  };
  const cta = p.needs_customer_ok ? 'Send offer to the customer' : p.kind === 'raise_po' ? 'Approve and order' : p.kind === 'escalate' ? 'I will take this' : p.kind === 'credit' ? 'Approve credit' : p.kind === 'resupply' ? 'Approve replan' : p.kind === 'reply' ? 'Send answer' : 'Approve and apply';
  return (
    <>
      <div className="detail">
        <div>
          <div className="dmeta" style={{ marginBottom: 4 }}><span className="pill acc">{KIND_LABEL[p.kind] || p.kind}</span><span className={'st ' + tone(p.status)}>{p.status}</span>
            {p.so && <span><a onClick={() => go('order', p.so)}>{p.so}</a></span>}{p.value > 0 && <span><b>{money(p.value)}</b> order</span>}</div>
          <h2 className="dt">{p.title}</h2>
          {p.customer && <div className="dmeta" style={{ marginTop: 4 }}><span>{p.customer}</span></div>}
        </div>
        <div className="banner acc"><Icon n="check" /><div>{p.summary}</div></div>
        <div className="facts three">
          <div className="fact"><span>Keeps the promised date</span><b>{p.meets_promised ? 'Yes' : 'No'}</b></div>
          <div className="fact"><span>{p.kind === 'raise_po' ? 'Expected' : 'Arrives'}</span><b>{d.new_eta || d.date ? fmtDate(d.new_eta || d.date) : '-'}</b></div>
          <div className="fact"><span>Cost</span><b>{p.cost ? money(p.cost) : 'None'}</b></div>
          <div className="fact"><span>Who decides</span><b>{p.needs}</b></div>
          <div className="fact"><span>Why it is with them</span><b style={{ fontWeight: 500 }}>{p.reason}</b></div>
          <div className="fact"><span>Customer must agree</span><b>{p.needs_customer_ok ? 'Yes, sent as an offer' : 'No'}</b></div>
        </div>
        {(d.side_effects || []).length > 0 && <div className="section"><h3>What it does</h3><ul className="chk">{d.side_effects.map((x: string, i: number) => <li key={i} className="ok"><Icon n="arrow" /><span>{x}</span></li>)}</ul></div>}
        {(d.fallbacks || []).length > 0 && <div className="section"><h3>Best fallbacks, none keeps the date</h3><ul className="chk">{d.fallbacks.map((x: any, i: number) => <li key={i} className="no"><Icon n="x" /><span>{x.title}{x.new_eta ? `, arrives ${fmtDate(x.new_eta)}` : ''}{x.cost ? `, ${money(x.cost)}` : ''}</span></li>)}</ul></div>}
        {p.subject && (open ? (<>
          <div className="section"><h3>{toSupplier ? `Email to the supplier` : 'Message to the customer'}</h3><div className="muted" style={{ fontSize: 12.5 }}>To {p.to}</div><input type="text" aria-label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} /></div>
          <textarea rows={9} aria-label="Message" value={body} onChange={(e) => setBody(e.target.value)} />
        </>) : <div className="section"><h3>{toSupplier ? 'Email to the supplier' : 'Message'}</h3><b>{p.subject}</b><pre className="draft">{p.body}</pre></div>)}
        {!open && <div className="muted">{p.status} by {p.decided_by || 'a person'}{p.decided_at ? ` at ${hm(p.decided_at)}` : ''}.</div>}
        {internal && open && <div className="muted" style={{ fontSize: 12.5 }}>This one changes our own plan; no message goes to a customer.</div>}
      </div>
      {open && <div className="stickybar">
        <button className="btn pri" disabled={busy} onClick={() => act(true)}>{cta}</button>
        <button className="btn" disabled={busy} onClick={() => act(false)}>Reject</button>
        <span className="spacer" />{p.so && <button className="btn ghost" onClick={() => go('order', p.so)}>View order</button>}
      </div>}
    </>
  );
}

export default function Approvals({ selected }: { selected?: string }) {
  const { refresh, go } = useApp();
  const role = useAuth().user?.role;
  const [aps, reloadA] = usePoll<any[]>(() => api.get('/approvals'), 2500);
  const [props, reloadP] = usePoll<any[]>(() => api.get('/proposals'), 2500);
  const A = (aps || []).filter((a) => (isOpen(a) ? mayDecide(role, a.status === 'Needs approval' ? 'Ops manager' : 'Account manager') : true));
  const P = (props || []).filter((p) => (p.status === 'Proposed' ? mayDecide(role, p.needs) : true));
  const actions = P.filter((p) => p.status === 'Proposed');
  const need = A.filter((a) => a.status === 'Needs approval');
  const ready = A.filter((a) => a.status === 'Ready');
  const doneA = A.filter((a) => !isOpen(a)), doneP = P.filter((p) => p.status !== 'Proposed');
  const isP = !!selected && selected.startsWith('p');
  const curP = isP ? P.find((p) => 'p' + p.id === selected) : undefined;
  const curA = !isP ? A.find((a) => String(a.id) === selected) : undefined;
  const first = actions[0] ? { p: actions[0] } : need[0] ? { a: need[0] } : ready[0] ? { a: ready[0] } : doneA[0] ? { a: doneA[0] } : doneP[0] ? { p: doneP[0] } : null;
  const cp = curP || (!curA && first && 'p' in first ? first.p : undefined);
  const ca = curA || (!curP && !cp && first && 'a' in first ? first.a : undefined);
  const total = actions.length + need.length + ready.length;
  const onDone = () => {
    reloadA(); reloadP(); refresh();
    const nxt = actions.find((p) => p.id !== cp?.id) ? 'p' + actions.find((p) => p.id !== cp?.id)!.id : [...need, ...ready].find((a) => a.id !== ca?.id)?.id;
    go('approvals', nxt);
  };
  const PRow = ({ p }: { p: any }) => (
    <button className={'mrow ' + (cp?.id === p.id ? 'on' : '')} onClick={() => go('approvals', 'p' + p.id)}>
      <span className="t1"><b>{p.customer || p.title}</b>{p.value > 0 && <span className="num" style={{ fontWeight: 600 }}>{money(p.value)}</span>}</span>
      <span className="t2">{KIND_LABEL[p.kind]}{p.so ? ` · ${p.so}` : ''} · {p.title}</span>
      <span className="t3"><span className={'st ' + tone(p.status)}>{p.status === 'Proposed' ? p.needs : p.status}</span></span>
    </button>);
  const ARow = ({ a }: { a: any }) => (
    <button className={'mrow ' + (ca?.id === a.id ? 'on' : '')} onClick={() => go('approvals', a.id)}>
      <span className="t1"><b>{a.customer}</b><span className="num" style={{ fontWeight: 600 }}>{money(a.value)}</span></span>
      <span className="t2">{a.so} · {a.subject.replace(/^Order SO-\d+: /, '')}</span>
    </button>);
  return (
    <>
      <div className="ph"><div className="grow"><h1>Approvals</h1><p>Customer updates, recovery plans and purchase orders waiting for you. Nothing changes or is sent until you approve it.</p></div></div>
      {A.length || P.length ? (
        <div className="md">
          <div className="pane-l">
            <div className="pane-h"><h2>Queue</h2><span className="muted">{total} open</span></div>
            {actions.length > 0 && <><div className="grouph">Recovery actions · {actions.length}</div>{actions.map((p) => <PRow key={p.id} p={p} />)}</>}
            {need.length > 0 && <><div className="grouph">Customer updates, ops manager · {need.length}</div>{need.map((a) => <ARow key={a.id} a={a} />)}</>}
            {ready.length > 0 && <><div className="grouph">Customer updates, one check · {ready.length}</div>{ready.map((a) => <ARow key={a.id} a={a} />)}</>}
            {(doneA.length > 0 || doneP.length > 0) && <><div className="grouph">Done · {doneA.length + doneP.length}</div>{doneP.map((p) => <PRow key={'p' + p.id} p={p} />)}{doneA.map((a) => <ARow key={a.id} a={a} />)}</>}
          </div>
          <div className="pane-r">{cp ? <ProposalPane key={'p' + cp.id + cp.status} p={cp} onDone={onDone} /> : ca ? <UpdatePane key={ca.id} a={ca} onDone={onDone} /> : <div className="empty"><b>Select an item</b></div>}</div>
        </div>
      ) : (
        <div className="card"><div className="empty"><Icon n="approve" /><b>Nothing to approve</b><span>Drafts and recovery plans appear here after supplier emails and customer replies are processed.</span>
          <button className="btn" onClick={() => go(role === 'sales' ? 'replies' : 'mailbox')}>{role === 'sales' ? 'Open customer replies' : 'Open supplier emails'}</button></div></div>
      )}
    </>
  );
}
