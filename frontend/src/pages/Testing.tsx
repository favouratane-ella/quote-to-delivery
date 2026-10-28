import { Fragment, useEffect, useState } from 'react';
import { api } from '../api';
import { Trace } from '../components/Trace';
import { Banner, fmtDate, Head, hm, Icon, toast, usePoll } from '../lib';
import { useApp } from '../meta';

/* ---------------- Test scenarios ---------------- */
export function Scenarios({ selected }: { selected?: string }) {
  const { go, status } = useApp();
  const [list, reload] = usePoll<any[]>(() => api.get('/scenarios'), 0);
  const [busy, setBusy] = useState<string | null>(null);
  const sc = list?.find((x) => x.id === selected) || list?.[0];
  const runOne = async (id: string) => {
    setBusy(id);
    try { await api.post(`/scenarios/${id}/run`); } catch (e: any) { toast(e.message); }
    setBusy(null); reload();
  };
  const runAll = async () => { for (const s of list || []) { go('scen', s.id); await runOne(s.id); } };
  const ran = (list || []).filter((s) => s.result).length, passed = (list || []).filter((s) => s.result?.passed).length;
  const res = sc?.result;
  return (
    <>
      <Head title="Test scenarios" sub="Thirty-one known situations: supplier emails, quotes, customer replies and inventory. Each has the result it should produce. Each runs in a fresh copy of the world, so tests never touch your main world. Switch between AI and rules mode in Settings to compare."
        right={<><span className={'pill ' + (ran && passed === ran ? 'good' : ran ? 'warn' : '')}>{passed} of {list?.length ?? 31} passing</span><button className="btn" disabled={!!busy} onClick={runAll}><Icon n="play" />Run all</button></>} />
      <div className="split">
        <div className="card"><div className="ch"><h2>Scenarios</h2><span className="muted">{status?.ai_active ? 'Claude mode' : 'Rules engine'}</span></div>
          <div className="list">{(list || []).map((x, i) => (<Fragment key={x.id}>
            {(i === 0 || list![i - 1].group !== x.group) && <div className="grouph">{x.group}</div>}
            <button className={'li ' + (x.id === sc?.id ? 'on' : '')} onClick={() => go('scen', x.id)}>
              <span className="t"><b>{x.title}</b>{busy === x.id ? <span className="pill acc dot">Running</span> : !x.result ? <span className="pill">Not run</span> : x.result.passed ? <span className="pill good">Pass</span> : <span className="pill bad">Fail</span>}</span>
              <span className="s">{x.what}</span></button></Fragment>))}</div></div>
        <div style={{ minWidth: 0 }}>{sc && (
          <div className="card"><div className="ch"><h2>{sc.title}</h2><span className="spacer" /><button className="btn pri" disabled={!!busy} onClick={() => runOne(sc.id)}><Icon n="play" />{busy === sc.id ? 'Running' : res ? 'Run again' : 'Run this scenario'}</button></div>
            <div className="cb">
              <p style={{ margin: 0 }}>{sc.what}</p>
              {sc.kind === 'story' && <ol className="checklist" style={{ padding: 0 }}>{sc.input.steps.map((t: string, i: number) => <li key={i} style={{ padding: '4px 0' }}><span className="sn">{i + 1}</span><div><span>{t}</span></div></li>)}</ol>}
              {sc.kind !== 'story' && <div className="mail" style={{ fontSize: 13 }}>{sc.kind === 'email' ? `From: ${sc.input.sender}\nSubject: ${sc.input.subject}\n\n${sc.input.body}` : `Quote: ${sc.input.qty} × ${sc.input.sku} for ${sc.input.customer_id}, wanted by ${fmtDate(sc.input.requested)}`}</div>}
              <div><span className="sub">What should happen</span>
                <ul className="checks big">{sc.expect.map((label: string, i: number) => { const c = res?.checks?.[i]; return <li key={i} className={!c ? '' : c.ok ? 'ok' : 'no'}>{c ? <Icon n={c.ok ? 'check' : 'x'} /> : <span className="pend" />}<span>{label}</span></li>; })}</ul></div>
              {busy === sc.id && <span className="thinking">The agent is running this scenario{status?.ai_active ? ' with Claude' : ''}</span>}
              {res && <Banner kind={res.passed ? 'good' : 'bad'} icon={res.passed ? 'check' : 'warn'}><b>{res.passed ? 'Pass' : 'Fail'}</b> · ran with {res.mode === 'ai' ? 'Claude' : 'the rules engine'} at {hm(res.at)}. Ran in its own copy of the world; your main world was not touched.</Banner>}
              {res?.run && <div><span className="sub">The agent's run</span><Trace run={res.run} interactive={false} /></div>}
            </div></div>)}</div>
      </div>
    </>
  );
}

/* ---------------- Accuracy test pack ---------------- */
export function TestPack() {
  const { status } = useApp();
  const [data, reload] = usePoll<any>(() => api.get('/testpack'), 0);
  const [busy, setBusy] = useState(false);
  const [pm, setPm] = useState(0.9);
  useEffect(() => { api.get('/settings').then((s) => setPm(s.pass_mark)); }, []);
  const run = async (mode: string) => { setBusy(true); try { await api.post(`/testpack/run/${mode}`); } catch (e: any) { toast(e.message); } setBusy(false); reload(); };
  const box = (k: string, label: string) => {
    const r = data?.results?.[k]?.results; const s = r ? r.filter((x: any) => x.pass).length : null; const pct = r ? Math.round((s! / r.length) * 100) : null;
    return <div className="card kpi"><span className="l">{label}</span><span className="v num" style={{ color: pct == null ? 'var(--mut)' : pct >= pm * 100 ? 'var(--good)' : 'var(--bad)' }}>{pct == null ? 'Not run' : `${s}/${r.length}`}</span>
      <span className="l">{pct == null ? `Pass mark ${Math.round(pm * 100)}%` : `${pct}% · ${pct >= pm * 100 ? 'passes' : 'below'} the ${Math.round(pm * 100)}% pass mark`}</span></div>;
  };
  const cell = (x: any) => !x ? <span className="muted">Not run</span> : <><span className={'pill ' + (x.pass ? 'good' : 'bad')}>{x.pass ? 'Pass' : 'Fail'}</span><div className="muted" style={{ fontSize: 12 }}>{x.type}{x.date ? ' · ' + fmtDate(x.date) : ''}</div></>;
  return (
    <>
      <Head title="Accuracy test pack" sub="Tests only the email-reading step: 65 supplier messages with known answers. T41 to T65 were written after the rules engine was built, as a held-out check."
        right={<><button className="btn pri" disabled={busy || !status?.ai_available} onClick={() => run('ai')}>{busy ? 'Running' : 'Run with Claude'}</button><button className="btn" disabled={busy} onClick={() => run('rules')}>Run with rules</button></>} />
      {!status?.ai_available && <Banner kind="acc" icon="how">No API key is set, so only the rules engine runs. Add ANTHROPIC_API_KEY later to compare Claude.</Banner>}
      <div className="grid2">{box('rules', 'Rules engine')}{box('ai', 'Claude (needs API key)')}</div>
      <div className="card"><div className="tscroll"><table className="tbl"><thead><tr><th>Case</th><th>Message</th><th>Expected</th><th>Rules engine</th><th>Claude</th></tr></thead>
        <tbody>{(data?.cases || []).map((c: any) => <tr key={c.id}><td className="mono">{c.id}</td><td>{c.text}</td><td>{c.type}{c.date && <div className="muted" style={{ fontSize: 12 }}>{fmtDate(c.date)}</div>}</td>
          <td>{cell(data?.results?.rules?.results.find((x: any) => x.id === c.id))}</td><td>{cell(data?.results?.ai?.results.find((x: any) => x.id === c.id))}</td></tr>)}</tbody></table></div></div>
    </>
  );
}

/* ---------------- Activity log ---------------- */
export function Log() {
  const [rows] = usePoll<any[]>(() => api.get('/log'), 3000);
  return (
    <>
      <Head title="Activity log" sub="Every action in the main world, by the agent or a person, with the system it touched." />
      <div className="card"><div className="tscroll"><table className="tbl"><thead><tr><th>Time</th><th>Who</th><th>System</th><th>What happened</th></tr></thead>
        <tbody>{(rows || []).map((l, i) => <tr key={i}><td className="mono muted">{hm(l.at)}</td>
          <td>{l.actor === 'Agent' ? <span className="tagc k-ai">Agent</span> : l.actor === 'System' ? <span className="pill">System</span> : <span className="tagc k-person">{l.actor}</span>}</td>
          <td>{l.system}</td><td>{l.text}</td></tr>)}</tbody></table></div></div>
    </>
  );
}

/* ---------------- Settings ---------------- */
export function SettingsPage() {
  const { refresh, status } = useApp();
  const [s, setS] = useState<any>(null);
  const [arm, setArm] = useState(false);
  useEffect(() => { api.get('/settings').then(setS); }, []);
  if (!s) return <span className="thinking">Loading</span>;
  const save = async () => { try { setS(await api.put('/settings', { ...s, approval_limit: Number(s.approval_limit), pass_mark: Number(s.pass_mark) })); toast('Settings saved.'); refresh(); } catch (e: any) { toast(e.message); } };
  const reset = async () => { await api.post('/world/reset'); setArm(false); toast('World reset.'); refresh(); };
  return (
    <>
      <Head title="Settings" sub="The rules a client configures, and how the agent runs." />
      <div className="grid2">
        <div className="card"><div className="ch"><h2>Agent</h2></div><div className="cb">
          <div className="field"><label htmlFor="st-mode">Reading and writing</label>
            <select id="st-mode" value={s.ai_mode} onChange={(e) => setS({ ...s, ai_mode: e.target.value })}><option value="auto">Use Claude when an API key is set</option><option value="rules">Rules engine only</option></select></div>
          <label className="row" style={{ gap: 8 }}><input type="checkbox" checked={s.auto_run} onChange={(e) => setS({ ...s, auto_run: e.target.checked })} /> Wake the agent automatically when an email arrives or the ERP changes</label>
          <label className="row" style={{ gap: 8 }}><input type="checkbox" checked={s.sim_customers} onChange={(e) => setS({ ...s, sim_customers: e.target.checked })} /> Simulated customers reply by themselves after an update is sent (for demos and tests)</label>
          <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>{status?.ai_available ? `Claude is configured (${status.model}).` : 'No API key is set, so the deterministic rules engine does all reading and writing. Add ANTHROPIC_API_KEY later to switch Claude on.'}</p>
        </div></div>
        <div className="card"><div className="ch"><h2>Client rules</h2></div><div className="cb"><div className="fields">
          <div className="field"><label htmlFor="st-limit">Manager approval from ($)</label><input id="st-limit" type="number" min={0} step={1000} value={s.approval_limit} onChange={(e) => setS({ ...s, approval_limit: e.target.value })} /></div>
          <div className="field"><label htmlFor="st-pass">Confidence pass mark (0.5 to 1)</label><input id="st-pass" type="number" min={0.5} max={1} step={0.01} value={s.pass_mark} onChange={(e) => setS({ ...s, pass_mark: e.target.value })} /></div>
          <div className="field"><label htmlFor="st-tone">Tone of customer updates</label><select id="st-tone" value={s.tone} onChange={(e) => setS({ ...s, tone: e.target.value })}>{['Warm and clear', 'Short and direct', 'Formal'].map((t) => <option key={t}>{t}</option>)}</select></div>
        </div></div></div>
      </div>
      <div className="row"><button className="btn pri" onClick={save}>Save settings</button></div>
      <div className="card"><div className="ch"><h2>Simulated world</h2></div><div className="cb">
        <p className="muted" style={{ margin: 0 }}>All companies, people, orders and figures are made up. Reset to put every system back to the start.</p>
        <div className="row">{arm ? <><button className="btn pri" onClick={reset}>Yes, reset the world</button><button className="btn" onClick={() => setArm(false)}>Keep it</button></> : <button className="btn" onClick={() => setArm(true)}><Icon n="undo" />Reset the world</button>}</div>
      </div></div>
    </>
  );
}
