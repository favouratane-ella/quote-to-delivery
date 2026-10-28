import { useEffect, useRef, useState } from 'react';
import { api } from '../api';
import { Head, Icon } from '../lib';
import { useApp } from '../meta';

type Msg = { role: 'user' | 'assistant'; content: string; tools?: string[]; mode?: string };
const SUGGEST = ['Which orders are late right now, and why?', 'What happens if PO-8850 slips by 3 days?', 'Can we promise 300 CC-210 crates to Kestrel Hotels by 20 Nov?', 'What is waiting for a person right now?'];

export default function Chat() {
  const { status } = useApp();
  const [msgs, setMsgs] = useState<Msg[]>(() => { try { return JSON.parse(sessionStorage.getItem('q2d-chat') || '[]'); } catch { return []; } });
  const [busy, setBusy] = useState(false);
  const [text, setText] = useState('');
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => { try { sessionStorage.setItem('q2d-chat', JSON.stringify(msgs)); } catch { /* ignore */ } box.current?.scrollTo(0, 1e6); }, [msgs, busy]);
  const off = false;
  const ask = async (q: string) => {
    q = q.trim(); if (!q || busy) return;
    const next: Msg[] = [...msgs, { role: 'user', content: q }];
    setMsgs(next); setText(''); setBusy(true);
    try {
      const r = await api.post('/chat', { messages: next.map(({ role, content }) => ({ role, content })) });
      setMsgs([...next, { role: 'assistant', content: r.reply, tools: r.tools, mode: r.mode }]);
    } catch (e: any) { setMsgs([...next, { role: 'assistant', content: e.message }]); }
    setBusy(false);
  };
  return (
    <>
      <Head title="Quick answers" sub="Ask about an order, purchase order, customer or quote, or test a what-if. Answers are looked up live in the ERP and CRM. Nothing here changes data." right={msgs.length ? <button className="btn sm ghost" onClick={() => setMsgs([])}>Clear</button> : null} />
      <div className="card"><div className="cb">
        
        <div className="chat" ref={box}>
          {!msgs.length && !busy && <div className="empty" style={{ padding: 12 }}><Icon n="agent" /><span>Try one of these questions.</span></div>}
          {msgs.map((m, i) => <div key={i} className={'msg ' + (m.role === 'user' ? 'u' : 'a')}>{m.content}{m.tools?.length ? <div className="tools">Looked up: {m.tools.map((t) => <span key={t}>{t}</span>)}</div> : null}</div>)}
          {busy && <div className="msg a"><span className="thinking">Looking it up</span></div>}
        </div>
        <div className="chips">{SUGGEST.map((s) => <button key={s} className="chip" disabled={off || busy} onClick={() => ask(s)}>{s}</button>)}</div>
        <form className="row" style={{ flexWrap: 'nowrap' }} onSubmit={(e) => { e.preventDefault(); ask(text); }}>
          <input type="text" aria-label="Question" placeholder="Ask about an order, customer or supplier" value={text} disabled={off} onChange={(e) => setText(e.target.value)} />
          <button className="btn pri" type="submit" disabled={off || busy}>Ask</button>
        </form>
      </div></div>
    </>
  );
}
