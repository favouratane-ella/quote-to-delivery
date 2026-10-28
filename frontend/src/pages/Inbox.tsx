import { Fragment, useState } from 'react';
import { api, Run } from '../api';
import { useAuth } from '../auth';
import { CheckForm } from '../components/Trace';
import { fmtDate, Icon, toast, typeLabel, usePoll } from '../lib';
import { useApp } from '../meta';
import { Mailbox } from './World';

const dot = (s: string) => (s === 'Not processed' ? 'acc' : s.startsWith('Applied') ? 'good' : s.startsWith('Waiting') ? 'warn' : '');
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);
const label = (s: string) => (s === 'Not processed' ? 'New' : s);
const when = (iso: string) => `${fmtDate(iso.slice(0, 10))}, ${iso.slice(11, 16)}`;

function Found({ runId }: { runId: number }) {
  const { go, refresh } = useApp();
  const { user } = useAuth();
  const [run, reload] = usePoll<Run | null>(() => api.get(`/runs/${runId}`), 1500, [runId]);
  if (!run) return <span className="thinking">Loading</span>;
  const read = run.steps?.find((s) => s.payload?.fields);
  const f = read?.payload.fields;
  const guard = [...(run.steps || [])].reverse().find((s) => s.kind === 'guard' && s.payload?.checks);
  const checks: { ok: boolean; label: string }[] = guard?.payload.checks || [];
  const affected: string[] = run.result?.affected || [];
  const role = user?.role;
  const waiting = run.status === 'waiting_person';
  const working = run.status === 'running';
  return (
    <div className="found">
      <div className="fh"><Icon n="check" />What we found {working && <span className="thinking" style={{ fontWeight: 400 }}>Working</span>}</div>
      <div className="fb">
        {f && f.type === 'stock_note' ? (<>
          <div className="facts">
            <div className="fact"><span>Type</span><b>Stock count</b></div>
            <div className="fact"><span>Item</span><b>{f.sku}</b></div>
            <div className="fact"><span>On hand becomes</span><b>{f.new_on_hand?.toLocaleString()}{f.change != null && <span className="muted" style={{ fontWeight: 400 }}> ({f.change > 0 ? '+' : ''}{f.change.toLocaleString()})</span>}</b></div>
            <div className="fact"><span>Confidence</span><b>{Math.round((f.confidence || 0) * 100)}%</b><div className="conf"><i style={{ width: `${Math.round((f.confidence || 0) * 100)}%`, background: (f.confidence || 0) >= 0.9 ? 'var(--good)' : 'var(--warn)' }} /></div></div>
          </div>
          {f.reasons?.length > 0 && <details><summary>How it was read ({f.reasons.length})</summary><ul className="reasons">{f.reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></details>}
        </>) : f ? (<>
          <div className="facts">
            <div className="fact"><span>Type</span><b>{cap(typeLabel(f.type))}</b></div>
            <div className="fact"><span>Purchase order</span><b className="mono">{f.po || 'None found'}</b></div>
            <div className="fact"><span>New date</span><b>{f.new_date ? fmtDate(f.new_date) : 'None'}</b></div>
            <div className="fact"><span>Confidence</span><b>{Math.round((f.confidence || 0) * 100)}%</b><div className="conf"><i style={{ width: `${Math.round((f.confidence || 0) * 100)}%`, background: (f.confidence || 0) >= 0.9 ? 'var(--good)' : 'var(--warn)' }} /></div></div>
          </div>
          {f.reasons?.length > 0 && <details><summary>How it was read ({f.reasons.length})</summary><ul className="reasons">{f.reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></details>}
        </>) : <span className="muted">Nothing to read: this email is not about a delivery date.</span>}
        {checks.length > 0 && <div className="section"><h3>Checks before the ERP changes</h3>
          <ul className="chk">{checks.map((c, i) => <li key={i} className={c.ok ? 'ok' : 'no'}><Icon n={c.ok ? 'check' : 'x'} /><span>{c.label}</span></li>)}</ul></div>}
        <div className="section"><h3>Outcome</h3>
          {run.status === 'no_action' && <span>Filed. No change was needed.</span>}
          {waiting && run.pending?.stock && <><span>Stopped for a person to check. The count changes stock by more than the agent will accept alone.</span><StockForm run={run} onDone={() => { reload(); refresh(); }} /></>}
          {waiting && !run.pending?.stock && <><span>Stopped for a person to check. Correct anything wrong, then confirm.</span><CheckForm run={run} onDone={() => { reload(); refresh(); }} /></>}
          {(run.status === 'waiting_approval' || run.status === 'done') && f?.type === 'stock_note' && <>
            <span>Stock was updated to {f.new_on_hand?.toLocaleString()}. {run.status === 'waiting_approval' ? 'Some orders lost stock; a replan is waiting for the planner.' : 'Every order is still covered.'}</span>
            <div className="actions">{run.status === 'waiting_approval' && <button className="btn sm" onClick={() => go('approvals')}>Review the replan</button>}<button className="btn sm" onClick={() => go('inventory')}>See inventory</button></div></>}
          {(run.status === 'waiting_approval' || run.status === 'done') && f?.type !== 'stock_note' && <>
            <span>The ERP was updated{affected.length ? `. ${affected.length} ${affected.length === 1 ? 'order is' : 'orders are'} now late: ${affected.join(', ')}.` : '. No order is affected.'}</span>
            <div className="actions">
              {affected.length > 0 && <button className="btn sm" onClick={() => go('orders')}>See orders at risk</button>}
              {run.status === 'waiting_approval' && (role === 'manager' || role === 'admin') && <button className="btn sm" onClick={() => go('approvals')}>Review customer updates</button>}
              {(role === 'planner' || role === 'manager' || role === 'admin') && <button className="btn sm ghost" onClick={() => go('runs', run.id)}>Full activity</button>}
            </div></>}
        </div>
      </div>
    </div>
  );
}

function StockForm({ run, onDone }: { run: Run; onDone: () => void }) {
  const st = run.pending?.stock || {};
  const [n, setN] = useState<string>(String(st.new_on_hand ?? ''));
  const send = async (dismiss: boolean) => {
    try { await api.post(`/runs/${run.id}/resolve`, dismiss ? { dismiss: true } : { sku: st.sku, on_hand: Number(n) }); toast(dismiss ? 'Dismissed. Stock is unchanged.' : 'Confirmed. The agent is continuing.'); onDone(); } catch (e: any) { toast(e.message); }
  };
  return (
    <div className="human"><b>Check the count for {st.sku}</b>
      <span className="muted">The note says {st.new_on_hand}. Enter the quantity you trust, or dismiss it.</span>
      <div className="field" style={{ maxWidth: 200 }}><label htmlFor="sf">On hand</label><input id="sf" type="number" min={0} value={n} onChange={(e) => setN(e.target.value)} /></div>
      <div className="row"><button className="btn pri" disabled={n === ''} onClick={() => send(false)}>Confirm and continue</button><button className="btn" onClick={() => send(true)}>Dismiss: no change</button></div>
    </div>
  );
}

export default function Inbox({ selected }: { selected?: string }) {
  const { go, refresh } = useApp();
  const admin = useAuth().user?.role === 'admin';
  const [mail, reload] = usePoll<any[]>(() => api.get('/mailbox'), 2000);
  if (selected === 'compose' && admin) return <Mailbox selected="compose" />;
  const cur = mail?.find((e) => String(e.id) === selected) || mail?.[0];
  const np = mail?.filter((e) => e.status === 'Not processed').length || 0;
  const process = async (id: number) => { try { await api.post(`/mailbox/${id}/process`); refresh(); reload(); } catch (e: any) { toast(e.message); } };
  const processAll = async () => { try { const r = await api.post('/mailbox/process-all'); toast(`Processing ${r.queued} ${r.queued === 1 ? 'email' : 'emails'}.`); refresh(); reload(); } catch (e: any) { toast(e.message); } };

  return (
    <>
      <div className="ph"><div className="grow"><h1>Supplier emails</h1></div>
        {admin && <button className="btn" onClick={() => go('mailbox', 'compose')}><Icon n="plus" />Simulate a supplier email</button>}</div>
      <div className="md">
        <div className="pane-l">
          <div className="pane-h"><h2>Inbox</h2><span className="muted">{mail?.length ?? ''}</span><span className="spacer" />
            {np > 0 && <button className="btn sm pri" onClick={processAll}><Icon n="play" />Process all {np}</button>}</div>
          {(mail || []).map((e) => (
            <button key={e.id} className={'mrow ' + (cur?.id === e.id ? 'on' : '')} onClick={() => go('mailbox', e.id)}>
              <span className="t1"><b>{e.sender}</b><span className="when">{e.received_at.slice(11, 16)}</span></span>
              <span className="t2">{e.subject}</span>
              <span className="t3"><span className={'st ' + dot(e.status)}>{label(e.status)}</span></span>
            </button>))}
        </div>
        <div className="pane-r">
          {cur ? (<>
            <div className="detail">
              <div><h2 className="dt">{cur.subject}</h2>
                <div className="dmeta" style={{ marginTop: 4 }}><span>From <b>{cur.sender}</b></span><span className="mono">{cur.address}</span><span>{when(cur.received_at)}</span></div></div>
              {cur.run_id ? <Found runId={cur.run_id} /> : (
                <div className="found"><div className="fh">Not read yet</div><div className="fb"><span className="muted">Processing reads the email and attachment, checks them against the ERP, and only then changes anything.</span></div></div>
              )}
              <div className="section"><h3>Email</h3><div className="mailbody">{cur.body}</div></div>
              {cur.attachment && (
                <div className="doc"><div className="dh"><span className="ext">PDF</span>{cur.attachment.name}</div>
                  <div className="db"><h4>{cur.attachment.title}</h4><dl>{cur.attachment.rows.map((r: string[]) => <Fragment key={r[0]}><dt>{r[0]}</dt><dd>{r[1]}</dd></Fragment>)}</dl></div></div>)}
            </div>
            {!cur.run_id && <div className="stickybar"><button className="btn pri" onClick={() => process(cur.id)}><Icon n="play" />Process this email</button><span className="muted">The ERP is not changed until every check passes.</span></div>}
          </>) : <div className="empty"><Icon n="mail" /><b>No emails</b></div>}
        </div>
      </div>
    </>
  );
}
