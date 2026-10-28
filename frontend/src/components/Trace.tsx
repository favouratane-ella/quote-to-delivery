import { useState } from 'react';
import { api, Run } from '../api';
import { fmtDate, Icon, toast, typeLabel } from '../lib';
import { useApp } from '../meta';

export const KIND: Record<string, [string, string]> = {
  event: ['Trigger', 'k-event'], read: ['Looked up', 'k-read'], ai: ['AI wording', 'k-ai'], rules: ['Read by rules', 'k-code'],
  code: ['Calculated', 'k-code'], guard: ['Check', 'k-guard'], write: ['Updated', 'k-write'], person: ['Person', 'k-person'],
  done: ['Finished', 'k-done'], wait: ['Waiting', 'k-guard'],
};

export function Legend() {
  return <div className="legend">{['event', 'read', 'rules', 'ai', 'code', 'guard', 'write', 'person'].map((k) => <span key={k} className={'tagc ' + KIND[k][1]}>{KIND[k][0]}</span>)}</div>;
}

/** The step-by-step record of one item. */
export function Trace({ run, interactive, onChange, goApprovals }: { run: Run; interactive: boolean; onChange?: () => void; goApprovals?: () => void }) {
  const steps = run.steps || [];
  return (
    <>
      <ol className="trace">
        {steps.map((s, i) => {
          const [label, cls] = KIND[s.kind] || [s.kind, ''];
          const p = s.payload || {};
          const spin = s.kind === 'wait' && i === steps.length - 1 && run.status === 'running';
          return (
            <li key={s.seq} className={'tl ' + cls + (spin ? ' spin' : '')}>
              <span className="dot" />
              <div className="tb">
                <div className="row" style={{ gap: 8 }}>
                  <span className="tag">{label}</span><span className="sys">{s.system === 'Agent code' ? 'System' : s.system}</span><span className="spacer" />
                  <span className="muted mono t">{s.at}s</span>
                </div>
                <b className="ttl">{s.title}</b>
                {s.text && <div className="muted">{s.text}</div>}
                {p.fields && (
                  <div className="kv">
                    <span>Type</span><b>{typeLabel(p.fields.type)}</b>
                    <span>PO</span><b className="mono">{p.fields.po || 'none'}</b>
                    <span>New date</span><b>{p.fields.new_date ? fmtDate(p.fields.new_date) : 'none'}</b>
                    {p.fields.split && <><span>Split</span><b>{p.fields.split.map((d: any) => `${d.qty} on ${fmtDate(d.date)}`).join(', ')}</b></>}
                    <span>Confidence</span><b>{Math.round((p.fields.confidence || 0) * 100)}%</b>
                  </div>
                )}
                {p.fields?.reasons?.length > 0 && (
                  <details open={s.kind === 'rules'}>
                    <summary>How it read the email ({p.fields.reasons.length} reasons)</summary>
                    <ul className="reasons">{p.fields.reasons.map((x: string, j: number) => <li key={j}>{x}</li>)}</ul>
                  </details>
                )}
                {p.checks && (
                  <ul className="checks">
                    {p.checks.map((c: any, j: number) => <li key={j} className={c.ok ? 'ok' : 'no'}><Icon n={c.ok ? 'check' : 'x'} /><span>{c.label}</span></li>)}
                  </ul>
                )}
                {p.table && (
                  <div className="tscroll">
                    <table className="tbl mini">
                      <thead><tr>{p.table.head.map((h: string) => <th key={h}>{h}</th>)}</tr></thead>
                      <tbody>{p.table.rows.map((r: string[], j: number) => <tr key={j}>{r.map((c, k) => <td key={k}>{c}</td>)}</tr>)}</tbody>
                    </table>
                  </div>
                )}
                {p.data && (
                  <details>
                    <summary>{s.kind === 'ai' ? "Show the prompt and Claude's raw reply" : 'Show the data'}</summary>
                    <pre>{p.data}</pre>
                  </details>
                )}
              </div>
            </li>
          );
        })}
      </ol>
      {interactive && run.status === 'waiting_person' && run.trigger?.type === 'email' && <CheckForm run={run} onDone={onChange} />}
      {interactive && run.status === 'waiting_person' && run.trigger?.type === 'quote' && <QuoteChoice run={run} onDone={onChange} />}
      {interactive && run.status === 'waiting_approval' && (
        <div className="human"><b>Ops manager: review the drafts</b><div className="row"><button className="btn pri" onClick={goApprovals}>Open approvals</button></div></div>
      )}
    </>
  );
}

export function CheckForm({ run, onDone }: { run: Run; onDone?: () => void }) {
  const { meta } = useApp();
  const ext = run.pending?.ext || {};
  const [type, setType] = useState(ext.type === 'partial' ? 'partial' : 'delay');
  const [po, setPo] = useState<string>(ext.po || '');
  const [date, setDate] = useState<string>(ext.new_date || '');
  const [busy, setBusy] = useState(false);
  const known: string[] = meta?.pos || [];
  const send = async (dismiss: boolean) => {
    setBusy(true);
    try {
      await api.post(`/runs/${run.id}/resolve`, dismiss ? { dismiss: true } : { po, new_date: date, type });
      toast(dismiss ? 'Dismissed. Nothing changed.' : 'Confirmed. Continuing.');
      onDone?.();
    } catch (e: any) { toast(e.message); }
    setBusy(false);
  };
  return (
    <div className="human">
      <b>Check what was read from the email</b>
      <span className="muted">Correct anything wrong, then confirm. Or dismiss if nothing should change.</span>
      <div className="fields3">
        <div className="field"><label htmlFor={'t' + run.id}>Type</label>
          <select id={'t' + run.id} value={type} onChange={(e) => setType(e.target.value)}><option value="delay">delivery delay</option><option value="partial">split delivery</option></select></div>
        <div className="field"><label htmlFor={'p' + run.id}>Purchase order</label>
          <select id={'p' + run.id} value={po} onChange={(e) => setPo(e.target.value)}>
            {!known.includes(po) && <option value="">{po ? po + ' (not in ERP)' : 'Choose a PO'}</option>}
            {known.map((x: string) => <option key={x}>{x}</option>)}
          </select></div>
        <div className="field"><label htmlFor={'d' + run.id}>New arrival date</label><input id={'d' + run.id} type="date" value={date} onChange={(e) => setDate(e.target.value)} /></div>
      </div>
      <div className="row">
        <button className="btn pri" disabled={busy || !po || !date} onClick={() => send(false)}>Confirm and continue</button>
        <button className="btn" disabled={busy} onClick={() => send(true)}>Dismiss: no change</button>
      </div>
    </div>
  );
}

function QuoteChoice({ run, onDone }: { run: Run; onDone?: () => void }) {
  const choose = async (k: string) => {
    try { await api.post(`/crm/quotes/${run.trigger.q}/choose`, { option: k }); toast('Quote updated in the CRM.'); onDone?.(); } catch (e: any) { toast(e.message); }
  };
  return (
    <div className="human"><b>Choose the date to promise</b>
      <div className="row">{(run.options || []).map((o) => <button key={o.k} className="btn pri" onClick={() => choose(o.k)}>{o.label}</button>)}</div>
    </div>
  );
}
