import { useState } from 'react';
import { api } from '../api';
import { CASE_LABEL, Empty, fmtDate, FLEX_LABEL, Icon, money, RESOLUTION_LABEL, Risk, usePoll } from '../lib';
import { useApp } from '../meta';

type Order = {
  so: string; customer: string; sku: string; qty: number; value: number; promised: string; eta: string; po: string | null; late: boolean; days_late: number;
  risk: string; case_status: string | null; resolution: string; flex: string; parent: string | null;
};
const RANK: Record<string, number> = { Critical: 0, High: 1, Medium: 2, Watch: 3, Low: 4 };

export default function Orders() {
  const { go } = useApp();
  const [orders] = usePoll<Order[]>(() => api.get('/erp/sales-orders'), 4000);
  const [tab, setTab] = useState<'risk' | 'done' | 'all'>('risk');
  const [q, setQ] = useState('');
  const all = orders || [];
  const atRisk = all.filter((o) => o.late || (o.case_status && o.case_status !== 'resolved'));
  const done = all.filter((o) => o.case_status === 'resolved');
  const rows = (tab === 'risk' ? atRisk : tab === 'done' ? done : all).filter((o) => !q || (o.customer + o.so + o.sku + (o.po || '')).toLowerCase().includes(q.toLowerCase()))
    .sort((a, b) => RANK[a.risk] - RANK[b.risk] || b.days_late - a.days_late || b.value - a.value);
  const stage = (o: Order) => (o.case_status === 'resolved' ? RESOLUTION_LABEL[o.resolution] || 'Resolved' : o.case_status ? CASE_LABEL[o.case_status] : '');
  return (
    <>
      <div className="ph"><div className="grow"><h1>Orders</h1><p>Open customer orders: how risky each one is, and where it stands in recovery.</p></div></div>
      <div className="card">
        <div className="toolbar">
          <div className="seg" role="tablist">
            <button className={tab === 'risk' ? 'on' : ''} onClick={() => setTab('risk')}>At risk<span>{atRisk.length}</span></button>
            <button className={tab === 'done' ? 'on' : ''} onClick={() => setTab('done')}>Recovered<span>{done.length}</span></button>
            <button className={tab === 'all' ? 'on' : ''} onClick={() => setTab('all')}>All open<span>{all.length}</span></button>
          </div>
          <input type="search" className="search" placeholder="Filter by customer, order, item or PO" aria-label="Filter orders" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        {rows.length ? (
          <div className="tscroll"><table className="tbl">
            <thead><tr><th>Order</th><th>Customer</th><th>Item</th><th className="r">Value</th><th>Promised</th><th>Arriving</th><th>Risk</th><th>Recovery</th><th /></tr></thead>
            <tbody>{rows.map((o) => (
              <tr key={o.so} className="click" onClick={() => go('order', o.so)}>
                <td className="mono"><b>{o.so}</b>{o.parent && <span className="sub2">split from {o.parent}</span>}</td>
                <td>{o.customer}<span className="sub2">{FLEX_LABEL[o.flex]}</span></td>
                <td>{o.qty.toLocaleString()} x <span className="mono">{o.sku}</span></td>
                <td className="r num">{money(o.value)}</td><td>{fmtDate(o.promised)}</td>
                <td>{fmtDate(o.eta)}{o.late && <span className="sub2 bad">{o.days_late} {o.days_late === 1 ? 'day' : 'days'} late</span>}</td>
                <td><Risk tier={o.risk} /></td>
                <td>{stage(o) || <span className="muted">{o.late ? 'Not started' : '-'}</span>}</td>
                <td style={{ color: 'var(--faint)' }}><Icon n="arrow" /></td>
              </tr>))}</tbody>
          </table></div>
        ) : <Empty icon="check" title={q ? 'No orders match' : tab === 'done' ? 'Nothing recovered yet' : 'No orders at risk'} text={q ? 'Try a different filter.' : tab === 'done' ? 'Orders appear here once their date is kept, agreed or split.' : 'Every open order arrives by its promised date.'} />}
      </div>
    </>
  );
}
