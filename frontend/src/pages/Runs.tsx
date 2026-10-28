import { api, Run } from '../api';
import { Legend, Trace } from '../components/Trace';
import { Empty, Head, hm, StatusPill, usePoll } from '../lib';
import { useAuth } from '../auth';
import { useApp } from '../meta';

export default function Runs({ selected }: { selected?: string }) {
  const { go } = useApp();
  const admin = useAuth().user?.role === 'admin';
  const [runs] = usePoll<Run[]>(() => api.get('/runs'), 1500);
  const id = selected ? Number(selected) : runs?.[0]?.id;
  const [run, reload] = usePoll<Run | null>(() => (id ? api.get(`/runs/${id}`) : Promise.resolve(null)), 900, [id]);
  if (runs && !runs.length)
    return (<><Head title="Activity" sub="A record of every automatic action: what came in, what was checked, what changed and who approved it." />
      <Empty icon="runs" title="No activity yet" text="Activity appears when a supplier email is processed, a PO date changes or a quote is checked.">
        <div className="row"><button className="btn pri" onClick={() => go('mailbox')}>Open supplier emails</button></div>
      </Empty></>);
  return (
    <>
      <Head title="Activity" sub="Each item step by step: what arrived, what was checked, what changed. Open a step to see the data behind it." />
      {admin && <Legend />}
      <div className="split">
        <div className="card"><div className="ch"><h2>Items</h2><span className="muted">{runs?.length ?? ''}</span></div>
          <div className="list">{(runs || []).map((r) => (
            <button key={r.id} className={'li ' + (r.id === id ? 'on' : '')} onClick={() => go('runs', r.id)}>
              <span className="t"><b className="mono">R{r.id}</b><StatusPill s={r.status} /></span>
              <span className="s">{r.title}</span><span className="s mono">{hm(r.started_at)} · {r.step_count} steps</span>
            </button>))}</div></div>
        <div className="card">
          {run ? (<>
            <div className="ch"><h2>R{run.id} · {run.title}</h2><span className="spacer" /><StatusPill s={run.status} />{admin && <span className={'reader ' + (run.mode === 'ai' ? 'ai' : 'rules')}>{run.mode === 'ai' ? 'AI mode' : 'Rules mode'}</span>}</div>
            <div className="cb"><Trace run={run} interactive onChange={reload} goApprovals={() => go('approvals')} /></div>
          </>) : <div className="cb"><span className="thinking">Loading</span></div>}
        </div>
      </div>
    </>
  );
}
