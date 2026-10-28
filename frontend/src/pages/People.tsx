import { useEffect, useState } from 'react';
import { api, Run } from '../api';
import { CheckForm, Trace } from '../components/Trace';
import { Empty, fmtDate, Head, hm, Icon, money, toast, usePoll } from '../lib';
import { useApp } from '../meta';

/* ---------------- Approvals and checks ---------------- */
function ApprovalCard({ a, onDone }: { a: any; onDone: () => void }) {
  const { go } = useApp();
  const open = a.status === 'Needs approval' || a.status === 'Ready';
  const [subject, setSubject] = useState(a.subject);
  const [body, setBody] = useState(a.body);
  const [note, setNote] = useState(a.note);
  const [busy, setBusy] = useState(false);
  const act = async (send: boolean) => {
    setBusy(true);
    try {
      await api.post(`/approvals/${a.id}/${send ? 'send' : 'reject'}`, send ? { subject, body, note } : {});
      toast(send ? 'Sent. See it in the customer outbox.' : 'Rejected. Not sent.');
      onDone();
    } catch (e: any) { toast(e.message); }
    setBusy(false);
  };
  const cls = a.status === 'Needs approval' ? 'warn' : a.status === 'Sent' ? 'good' : a.status === 'Rejected' ? 'bad' : '';
  return (
    <div className="upd">
      <div className="top"><b>{a.customer}</b><span className="mono muted">{a.so}</span><span className="num">{money(a.value)}</span>
        <span className={'reader ' + (a.reader === 'ai' ? 'ai' : 'rules')}>{a.reader === 'ai' ? 'AI DRAFT' : 'TEMPLATE'}</span>
        <button className="btn sm ghost" onClick={() => go('runs', a.run_id)}>From R{a.run_id}</button><span className="spacer" /><span className={'pill ' + cls}>{a.status}</span></div>
      <div className="muted" style={{ fontSize: 12.5 }}>Why: {a.reason} · To {a.contact}</div>
      {open ? (<>
        <input type="text" aria-label="Subject" value={subject} onChange={(e) => setSubject(e.target.value)} />
        <textarea rows={9} aria-label="Message" value={body} onChange={(e) => setBody(e.target.value)} />
        <div className="field"><label htmlFor={'n' + a.id}>CRM note</label><input id={'n' + a.id} type="text" value={note} onChange={(e) => setNote(e.target.value)} /></div>
        <div className="row"><button className="btn pri" disabled={busy} onClick={() => act(true)}>{a.status === 'Needs approval' ? 'Approve and send' : 'Checked: send'}</button>
          <button className="btn ghost" disabled={busy} onClick={() => act(false)}>Reject</button></div>
      </>) : <div className="muted" style={{ fontSize: 12.5 }}>{a.status === 'Sent' ? `Sent by ${a.decided_by} at ${hm(a.decided_at)}` : `Rejected by ${a.decided_by}`}</div>}
    </div>
  );
}

export function Approvals() {
  const { go, refresh, status } = useApp();
  const [aps, reloadA] = usePoll<any[]>(() => api.get('/approvals'), 2500);
  const [runs, reloadR] = usePoll<Run[]>(() => api.get('/runs'), 2500);
  const waiting = (runs || []).filter((r) => r.status === 'waiting_person');
  const checks = waiting.filter((r) => r.trigger?.type === 'email');
  const qwait = waiting.filter((r) => r.trigger?.type === 'quote');
  const [details, setDetails] = useState<Record<number, Run>>({});
  const checkIds = checks.map((r) => r.id).join(',');
  useEffect(() => {
    for (const r of checks) if (!details[r.id]) api.get(`/runs/${r.id}`).then((d) => setDetails((x) => ({ ...x, [r.id]: d })));
  }, [checkIds]); // eslint-disable-line react-hooks/exhaustive-deps
  const done = () => { reloadA(); reloadR(); refresh(); };
  const pending = (aps || []).filter((a) => a.status === 'Needs approval' || a.status === 'Ready');
  const closed = (aps || []).filter((a) => a.status === 'Sent' || a.status === 'Rejected');
  return (
    <>
      <Head title="Approvals" sub="Customer updates drafted for you. Read each one, edit it if needed, then send or reject. Orders at or above the approval limit need the ops manager." />
      {checks.length > 0 && <div className="card"><div className="ch"><h2>Supplier emails to check</h2><span className="pill warn">{checks.length}</span></div>
        <div className="cb">{checks.map((r) => {
          const d = details[r.id];
          const g = d?.steps?.filter((s) => s.kind === 'guard' && s.payload?.checks).pop();
          const failed = (g?.payload.checks || []).filter((c: any) => !c.ok).map((c: any) => c.label);
          return <div key={r.id} className="upd" style={{ padding: '0 0 14px' }}><div className="top"><b>{r.title}</b><button className="btn sm ghost" onClick={() => go('runs', r.id)}>R{r.id}</button></div>
            {d ? <><div className="muted">Stopped because: {failed.join('; ')}</div><CheckForm run={d} onDone={done} /></> : <span className="thinking">Loading</span>}</div>;
        })}</div></div>}
      {qwait.length > 0 && <div className="card"><div className="ch"><h2>Sales rep: quotes to decide</h2><span className="pill warn">{qwait.length}</span></div>
        <div className="cb">{qwait.map((r) => <div key={r.id} className="row"><b>{r.title}</b><button className="btn sm" onClick={() => go('quotes', r.trigger.q)}>Open on the quote desk</button></div>)}</div></div>}
      {pending.length > 0 && <div className="card"><div className="ch"><h2>Customer updates</h2><span className="pill warn">{pending.length}</span></div>{pending.map((a) => <ApprovalCard key={a.id} a={a} onDone={done} />)}</div>}
      {aps && runs && !checks.length && !pending.length && !qwait.length && (
        <Empty icon="approve" title="Nothing waiting for a person" text={status?.counts.running ? 'Work is in progress. Results will land here.' : 'Process the supplier emails and anything that needs a person will land here.'}>
          <button className="btn pri" onClick={() => go('mailbox')}>Open supplier emails</button></Empty>)}
      {closed.length > 0 && <div className="card"><div className="ch"><h2>Done</h2><span className="pill">{closed.length}</span></div>{closed.map((a) => <ApprovalCard key={a.id} a={a} onDone={done} />)}</div>}
    </>
  );
}

/* ---------------- Quote desk ---------------- */
export function Quotes({ selected }: { selected?: string }) {
  const { go, meta, refresh } = useApp();
  const [quotes, reloadQ] = usePoll<any[]>(() => api.get('/crm/quotes'), 2000);
  const q = quotes?.find((x) => x.q === selected) || quotes?.[0];
  const [run, reloadRun] = usePoll<Run | null>(() => (q?.run_id ? api.get(`/runs/${q.run_id}`) : Promise.resolve(null)), 1000, [q?.run_id]);
  const [f, setF] = useState({ customer_id: 'kestrel', sku: 'CC-210', qty: '300', requested: '' });
  const submit = async (code: string) => { try { await api.post(`/crm/quotes/${code}/check`); reloadQ(); refresh(); } catch (e: any) { toast(e.message); } };
  const create = async () => {
    try { const r = await api.post('/crm/quotes', { ...f, qty: Number(f.qty), requested: f.requested || meta?.next_week }); reloadQ(); go('quotes', r.q); } catch (e: any) { toast(e.message); }
  };
  const [adding, setAdding] = useState(false);
  const st = (x: any) => (x.final ? ['good', 'Decided'] : x.run_id ? ['warn', x.status] : ['', 'Not checked']);
  return (
    <>
      <div className="ph"><div className="grow"><h1>Quotes</h1><p>Check stock, inbound purchase orders and transit time before you promise a date to a customer.</p></div>
        <button className="btn pri" onClick={() => setAdding((a) => !a)}><Icon n="plus" />New quote</button></div>
      {adding && (
        <div className="card"><div className="ch"><h2>New quote</h2></div><div className="cb">
          <div className="fields3" style={{ gridTemplateColumns: 'repeat(4,minmax(0,1fr))' }}>
            <div className="field"><label htmlFor="nq-c">Customer</label><select id="nq-c" value={f.customer_id} onChange={(e) => setF({ ...f, customer_id: e.target.value })}>{meta?.customers.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></div>
            <div className="field"><label htmlFor="nq-s">Item</label><select id="nq-s" value={f.sku} onChange={(e) => setF({ ...f, sku: e.target.value })}>{meta?.items.map((i) => <option key={i.sku} value={i.sku}>{i.sku} {i.name}</option>)}</select></div>
            <div className="field"><label htmlFor="nq-q">Quantity</label><input id="nq-q" type="number" min={1} value={f.qty} onChange={(e) => setF({ ...f, qty: e.target.value })} /></div>
            <div className="field"><label htmlFor="nq-d">Wanted by</label><input id="nq-d" type="date" value={f.requested || meta?.next_week || ''} onChange={(e) => setF({ ...f, requested: e.target.value })} /></div>
          </div>
          <div className="row"><button className="btn pri" onClick={async () => { await create(); setAdding(false); }}>Create and check</button><button className="btn" onClick={() => setAdding(false)}>Cancel</button></div></div></div>
      )}
      <div className="md">
        <div className="pane-l">
          <div className="pane-h"><h2>Quotes</h2><span className="muted">{quotes?.length ?? ''}</span></div>
          {(quotes || []).map((x) => { const [tone, label] = st(x); return (
            <button key={x.q} className={'mrow ' + (x.q === q?.q ? 'on' : '')} onClick={() => go('quotes', x.q)}>
              <span className="t1"><b>{x.customer}</b><span className="when">{x.q}</span></span>
              <span className="t2">{x.qty.toLocaleString()} x {x.sku} · wanted by {fmtDate(x.requested)}</span>
              <span className="t3"><span className={'st ' + tone}>{label}</span></span>
            </button>); })}
        </div>
        <div className="pane-r">{q ? (
          <div className="detail">
            <div><h2 className="dt">{q.customer}</h2>
              <div className="dmeta" style={{ marginTop: 4 }}><span>{q.q}</span><span><b>{q.qty.toLocaleString()}</b> x {q.sku}</span><span>Wanted by <b>{fmtDate(q.requested)}</b></span></div></div>
            {run ? <Trace run={run} interactive onChange={() => { reloadRun(); reloadQ(); refresh(); }} /> :
              <div className="found"><div className="fh">Not checked yet</div><div className="fb"><span className="muted">Checks free stock and every inbound purchase order against the date, then offers the earliest full delivery and a split where stock allows.</span>
                <div className="actions"><button className="btn pri" onClick={() => submit(q.q)}><Icon n="play" />Check this quote</button></div></div></div>}
          </div>) : <div className="empty"><b>No quotes</b></div>}</div>
      </div>
    </>
  );
}
