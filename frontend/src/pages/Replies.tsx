import { useState } from 'react';
import { api, Run } from '../api';
import { useAuth } from '../auth';
import { fmtDate, hm, Icon, KIND_LABEL, money, toast, typeLabel, usePoll } from '../lib';
import { useApp } from '../meta';

const INTENTS: [string, string][] = [['accept', 'Accepts the new date'], ['hard_deadline', 'Cannot accept: needs the original date'], ['partial_ok', 'Will take part now'], ['expedite', 'Asks for faster shipping'],
  ['credit', 'Wants a credit'], ['cancel', 'Wants to cancel'], ['question', 'Asks a question'], ['reschedule', 'Proposes a date']];
const dot = (s: string) => (s === 'New' || s === 'Reading' ? 'acc' : s === 'Handled' ? 'good' : 'warn');
const snippet = (b: string) => b.replace(/^Hi [^,]*,\s*/i, '').replace(/\s+/g, ' ').slice(0, 78);

function Understood({ reply }: { reply: any }) {
  const { go, refresh } = useApp();
  const [run, reload] = usePoll<Run | null>(() => (reply.run_id ? api.get(`/runs/${reply.run_id}`) : Promise.resolve(null)), 1500, [reply.run_id, reply.status]);
  const [props] = usePoll<any[]>(() => api.get('/proposals'), 2500);
  const [intent, setIntent] = useState('accept');
  const [date, setDate] = useState('');
  if (!reply.run_id) return <div className="found"><div className="fh">Not read yet</div><div className="fb"><span className="muted">The agent reads each reply and checks it against the order, the customer and the case.</span></div></div>;
  if (!run) return <span className="thinking">Loading</span>;
  const read = run.steps?.find((s) => s.payload?.fields);
  const f = read?.payload.fields;
  const guard = [...(run.steps || [])].reverse().find((s) => s.kind === 'guard' && s.payload?.checks);
  const mine = (props || []).filter((p) => p.run_id === run.id);
  const resolve = async () => { try { await api.post(`/replies/${reply.id}/resolve`, { intent, date: date || null }); toast('Thanks. The agent continues.'); refresh(); reload(); } catch (e: any) { toast(e.message); } };
  return (
    <div className="found">
      <div className="fh"><Icon n="check" />What the agent understood</div>
      <div className="fb">
        {f && <div className="facts three">
          <div className="fact"><span>The customer</span><b>{typeLabel(f.type)}</b></div>
          <div className="fact"><span>Date mentioned</span><b>{f.new_date ? fmtDate(f.new_date) : 'None'}</b></div>
          <div className="fact"><span>Confidence</span><b>{Math.round((f.confidence || 0) * 100)}%</b><div className="conf"><i style={{ width: `${Math.round((f.confidence || 0) * 100)}%`, background: (f.confidence || 0) >= 0.9 ? 'var(--good)' : 'var(--warn)' }} /></div></div>
        </div>}
        {f?.reasons?.length > 0 && <details><summary>How it was read ({f.reasons.length})</summary><ul className="reasons">{f.reasons.map((x: string, i: number) => <li key={i}>{x}</li>)}</ul></details>}
        {guard && <ul className="chk">{guard.payload.checks.map((c: any, i: number) => <li key={i} className={c.ok ? 'ok' : 'no'}><Icon n={c.ok ? 'check' : 'x'} /><span>{c.label}</span></li>)}</ul>}
        <div className="section"><h3>What happened</h3>
          {run.status === 'waiting_person' && (
            <>
              <span>The agent was not sure what this customer means, so nothing has changed. Tell it, and it carries on.</span>
              <div className="chips2">{INTENTS.map(([k, l]) => <button key={k} className={intent === k ? 'on' : ''} onClick={() => setIntent(k)}>{l}</button>)}</div>
              {(intent === 'hard_deadline' || intent === 'reschedule') && <div className="field" style={{ maxWidth: 220 }}><label htmlFor="rd">Date they need</label><input id="rd" type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>}
              <div className="actions"><button className="btn pri" onClick={resolve}>Continue</button></div>
            </>)}
          {run.status === 'waiting_approval' && <><span>A recovery action is waiting for approval. Nothing has changed yet.</span>
            <div className="rows">{mine.map((p) => <button key={p.id} className="row2" onClick={() => go('approvals', 'p' + p.id)}><span className="tx"><b>{KIND_LABEL[p.kind]}: {p.title}</b><span>{p.summary}</span></span><span className="meta"><span className={'st ' + (p.status === 'Proposed' ? 'warn' : 'good')}>{p.status === 'Proposed' ? p.needs : p.status}</span>{p.cost > 0 && <span>{money(p.cost)}</span>}</span></button>)}</div></>}
          {run.status === 'done' && <span>{[...(run.steps || [])].reverse().find((s) => s.kind === 'done')?.text || 'Done.'}</span>}
          {run.status === 'running' && <span className="thinking">The agent is working on it</span>}
          <div className="actions"><button className="btn sm ghost" onClick={() => go('runs', run.id)}>Full activity</button><button className="btn sm ghost" onClick={() => go('order', reply.so)}>Open order {reply.so}</button></div>
        </div>
      </div>
    </div>
  );
}

export default function Replies({ selected }: { selected?: string }) {
  const { go, refresh } = useApp();
  const role = useAuth().user?.role;
  const [list, reload] = usePoll<any[]>(() => api.get('/replies'), 2000);
  const [cases] = usePoll<any[]>(() => api.get('/cases'), 4000);
  const [adding, setAdding] = useState(false);
  const [so, setSo] = useState('');
  const [text, setText] = useState('');
  const open = (cases || []).filter((c) => c.status !== 'resolved');
  const cur = list?.find((r) => String(r.id) === selected) || list?.find((r) => r.status === 'Needs a person') || list?.[0];
  const add = async () => {
    try { await api.post('/replies', { so: so || open[0]?.so, body: text }); setText(''); setAdding(false); toast('Reply added. The agent is reading it.'); refresh(); reload(); } catch (e: any) { toast(e.message); }
  };
  const canLog = role === 'sales' || role === 'manager' || role === 'admin';
  return (
    <>
      <div className="ph"><div className="grow"><h1>Customer replies</h1><p>What customers say after they are told about a delay. Each reply is read and turned into a recovery plan.</p></div>
        {canLog && <button className="btn" onClick={() => setAdding((a) => !a)}><Icon n="plus" />Log a reply</button>}</div>
      {adding && (
        <div className="card"><div className="ch"><h2>Log a customer reply</h2><span className="muted">For an order that is at risk</span></div><div className="cb">
          <div className="field" style={{ maxWidth: 360 }}><label htmlFor="lr-o">Order</label>
            <select id="lr-o" value={so || open[0]?.so || ''} onChange={(e) => setSo(e.target.value)}>{open.map((c) => <option key={c.so} value={c.so}>{c.so} · {c.customer}</option>)}</select></div>
          <textarea rows={4} aria-label="Reply" placeholder="Paste or type what the customer wrote." value={text} onChange={(e) => setText(e.target.value)} />
          <div className="actions"><button className="btn pri" disabled={text.trim().length < 2 || !open.length} onClick={add}>Add reply</button><button className="btn" onClick={() => setAdding(false)}>Cancel</button>
            {!open.length && <span className="muted">No order is at risk right now.</span>}</div></div></div>
      )}
      {list && list.length ? (
        <div className="md">
          <div className="pane-l">
            <div className="pane-h"><h2>Replies</h2><span className="muted">{list.length}</span></div>
            {list.map((r) => (
              <button key={r.id} className={'mrow ' + (cur?.id === r.id ? 'on' : '')} onClick={() => go('replies', r.id)}>
                <span className="t1"><b>{r.customer}</b><span className="when">{hm(r.at)}</span></span>
                <span className="t2">{r.so} · {snippet(r.body)}</span>
                <span className="t3"><span className={'st ' + dot(r.status)}>{r.status === 'New' ? 'New' : r.status}</span>{r.intent && <span className="muted">{typeLabel(r.intent)}</span>}</span>
              </button>))}
          </div>
          <div className="pane-r">{cur && (
            <div className="detail" key={cur.id}>
              <div><h2 className="dt">{cur.customer}</h2>
                <div className="dmeta" style={{ marginTop: 4 }}><span>From <b>{cur.contact}</b></span><span><a onClick={() => go('order', cur.so)}>{cur.so}</a></span><span>{fmtDate(cur.at.slice(0, 10))}, {hm(cur.at)}</span>{cur.source === 'typed' && <span className="pill">Logged by a person</span>}</div></div>
              <Understood reply={cur} />
              <div className="section"><h3>Their reply</h3><div className="mailbody">{cur.body}</div></div>
            </div>)}</div>
        </div>
      ) : (
        <div className="card"><div className="empty"><Icon n="agent" /><b>No replies yet</b><span>When an update is sent to a customer, their reply appears here and the agent reads it.</span>
          <button className="btn" onClick={() => go('approvals')}>Open approvals</button></div></div>
      )}
    </>
  );
}
