import { api } from '../api';
import { useAuth } from '../auth';
import { fmtDate, Icon, toast, usePoll } from '../lib';
import { useApp } from '../meta';

const TONE: Record<string, string> = { Healthy: 'good', Reorder: 'warn', Short: 'bad' };

export default function Inventory() {
  const { go, refresh } = useApp();
  const role = useAuth().user?.role;
  const [rows, reload] = usePoll<any[]>(() => api.get('/erp/inventory'), 4000);
  const [props] = usePoll<any[]>(() => api.get('/proposals'), 4000);
  const waiting = (props || []).filter((p) => p.status === 'Proposed' && (p.kind === 'raise_po' || p.kind === 'resupply'));
  const flagged = (rows || []).filter((r) => r.status !== 'Healthy');
  const scan = async () => { try { await api.post('/inventory/scan'); toast('Checking every item against its reorder point.'); refresh(); setTimeout(reload, 1200); } catch (e: any) { toast(e.message); } };
  return (
    <>
      <div className="ph"><div className="grow"><h1>Inventory</h1><p>Stock on hand, what orders have reserved, and supply on its way. Items at their reorder point are flagged.</p></div>
        {(role === 'planner' || role === 'admin') && <button className="btn pri" onClick={scan}><Icon n="play" />Run inventory check</button>}</div>
      {waiting.length > 0 && (
        <div className="banner warn"><Icon n="warn" /><div><b>{waiting.length} {waiting.length === 1 ? 'action is' : 'actions are'} waiting for the planner.</b> {waiting.map((p) => p.title).slice(0, 2).join('; ')}.
          {' '}<button className="btn sm" onClick={() => go('approvals', 'p' + waiting[0].id)}>Review</button></div></div>
      )}
      <div className="card">
        <div className="toolbar"><span className="muted">{rows?.length ?? 0} items</span><span className="spacer" />
          {flagged.length > 0 ? <span className="st warn">{flagged.length} need attention</span> : <span className="st good">All items healthy</span>}</div>
        <div className="tscroll"><table className="tbl">
          <thead><tr><th>Item</th><th className="r">On hand</th><th>On hand vs reserved</th><th className="r">Reserved</th><th className="r">Free</th><th className="r">Inbound, not promised</th><th>Next arrival</th><th className="r">Projected free</th><th className="r">Reorder at</th><th>Status</th></tr></thead>
          <tbody>{(rows || []).map((r) => (
            <tr key={r.sku}>
              <td><b className="mono">{r.sku}</b><span className="sub2">{r.name}</span></td>
              <td className="r num">{r.on_hand.toLocaleString()}</td>
              <td><div className="invbar" title={`${r.reserved} reserved of ${r.on_hand} on hand`}><i style={{ width: '100%', opacity: 0.25 }} /><i className="res" style={{ width: `${r.on_hand ? Math.min(100, (r.reserved / r.on_hand) * 100) : 100}%`, background: r.over_reserved ? 'var(--bad)' : undefined, opacity: r.over_reserved ? 0.8 : undefined }} /></div></td>
              <td className="r num">{r.reserved.toLocaleString()}</td>
              <td className="r num">{r.free.toLocaleString()}</td>
              <td className="r num">{r.inbound_free.toLocaleString()}</td>
              <td>{r.next_inbound ? fmtDate(r.next_inbound) : '-'}</td>
              <td className="r num"><b>{r.projected_free.toLocaleString()}</b></td>
              <td className="r num">{r.reorder_point.toLocaleString()}</td>
              <td><span className={'st ' + TONE[r.status]}>{r.status === 'Reorder' ? 'At reorder point' : r.status === 'Short' ? 'Short' : 'Healthy'}</span>{r.over_reserved > 0 && <span className="sub2 bad">{r.over_reserved} more reserved than on hand</span>}</td>
            </tr>))}</tbody>
        </table></div>
      </div>
      <p className="muted" style={{ fontSize: 12.5, margin: 0 }}>Projected free = free stock plus inbound supply that no order has claimed. When it falls to the reorder point, the agent proposes a purchase order for the planner to approve.</p>
    </>
  );
}
