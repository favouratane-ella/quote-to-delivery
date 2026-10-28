import { useCallback, useEffect, useRef, useState } from 'react';
import { api, Status } from './api';
import { allowed, NAV, useAuth } from './auth';
import { Icon, toast, Toaster, usePoll } from './lib';
import { Meta, MetaCtx } from './meta';
import Palette from './components/Palette';
import Chat from './pages/Chat';
import Home from './pages/Home';
import How from './pages/How';
import Approvals from './pages/Approvals';
import Inbox from './pages/Inbox';
import Inventory from './pages/Inventory';
import Login from './pages/Login';
import OrderDetail from './pages/OrderDetail';
import Orders from './pages/Orders';
import Replies from './pages/Replies';
import { Quotes } from './pages/People';
import Runs from './pages/Runs';
import { Log, Scenarios, SettingsPage, TestPack } from './pages/Testing';
import { Crm, Erp, Outbox } from './pages/World';

// Routes are #view or #view/id, so every screen can be bookmarked.
function parseHash(): [string, string | undefined] {
  const [v, id] = window.location.hash.replace(/^#\/?/, '').split('/');
  return [v || 'home', id || undefined];
}

const THEME = 'q2d.theme';
function useTheme(): [string, () => void] {
  const [t, setT] = useState<string>(() => { try { return localStorage.getItem(THEME) || ''; } catch { return ''; } });
  useEffect(() => {
    if (t) document.documentElement.setAttribute('data-theme', t); else document.documentElement.removeAttribute('data-theme');
  }, [t]);
  const dark = t ? t === 'dark' : window.matchMedia('(prefers-color-scheme: dark)').matches;
  return [dark ? 'dark' : 'light', () => { const n = dark ? 'light' : 'dark'; setT(n); try { localStorage.setItem(THEME, n); } catch { /* ignore */ } }];
}

export default function App() {
  const { user } = useAuth();
  return user ? <Shell /> : <><Login /><Toaster /></>;
}

function Shell() {
  const { user, signOut } = useAuth();
  const role = user!.role;
  const [[rawView, sel], setRoute] = useState(parseHash());
  useEffect(() => { const f = () => setRoute(parseHash()); window.addEventListener('hashchange', f); return () => window.removeEventListener('hashchange', f); }, []);
  const view = allowed(role, rawView) ? rawView : 'home';
  const [navOpen, setNavOpen] = useState(false);
  const go = useCallback((v: string, id?: string | number) => { window.location.hash = id !== undefined ? `${v}/${id}` : v; window.scrollTo(0, 0); setNavOpen(false); }, []);
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchOpen, setSearchOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [resetting, setResetting] = useState(false);
  const doReset = async () => {
    setResetting(true);
    try { await api.post('/world/reset'); setResetOpen(false); toast('Demo data reset. Everything is back to the start.'); window.location.hash = 'home'; window.setTimeout(() => window.location.reload(), 400); }
    catch (e: any) { toast(e.message); setResetting(false); }
  };
  const menuRef = useRef<HTMLDivElement>(null);
  const [theme, toggleTheme] = useTheme();
  useEffect(() => {
    if (!menuOpen) return;
    const f = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setMenuOpen(false); };
    document.addEventListener('mousedown', f); return () => document.removeEventListener('mousedown', f);
  }, [menuOpen]);

  useEffect(() => {
    const f = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement;
      const typing = /INPUT|TEXTAREA|SELECT/.test(t.tagName);
      if ((e.key === 'k' && (e.metaKey || e.ctrlKey)) || (e.key === '/' && !typing)) { e.preventDefault(); setSearchOpen(true); }
    };
    window.addEventListener('keydown', f); return () => window.removeEventListener('keydown', f);
  }, []);
  const [status, refresh, err] = usePoll<Status>(() => api.get('/status'), 2500);
  const [meta, reloadMeta] = usePoll<Meta>(() => api.get('/meta'), 0);
  useEffect(() => { reloadMeta(); }, [status?.counts.runs]); // eslint-disable-line react-hooks/exhaustive-deps

  const c = status?.counts;
  const badge = (v: string) => (!c ? 0 : v === 'mailbox' ? c.unprocessed : v === 'approvals' ? c.approvals + c.proposals : v === 'replies' ? c.replies : 0);
  const items = NAV[role].filter((n) => n[0] !== 'grp' && n[0] !== 'home');
  const attention = items.reduce((s, n) => s + badge(n[0]), 0);
  const current = NAV[role].find((n) => n[0] === (view === 'order' ? 'orders' : view));
  const bellTo = role === 'planner' ? 'mailbox' : role === 'sales' ? 'quotes' : 'approvals';
  const signOutNow = () => { setMenuOpen(false); signOut(); window.location.hash = 'home'; };

  const page = (() => {
    switch (view) {
      case 'runs': return <Runs selected={sel} />;
      case 'agent': return <Chat />;
      case 'mailbox': return <Inbox selected={sel} />;
      case 'erp': return <Erp selected={sel} />;
      case 'crm': return <Crm selected={sel} />;
      case 'outbox': return <Outbox />;
      case 'approvals': return <Approvals selected={sel} />;
      case 'quotes': return <Quotes selected={sel} />;
      case 'orders': return <Orders />;
      case 'replies': return <Replies selected={sel} />;
      case 'inventory': return <Inventory />;
      case 'order': return <OrderDetail id={sel} />;
      case 'scen': return <Scenarios selected={sel} />;
      case 'pack': return <TestPack />;
      case 'log': return <Log />;
      case 'settings': return <SettingsPage />;
      case 'how': return <How />;
      default: return <Home />;
    }
  })();
  const aiLabel = !status ? 'Connecting' : status.ai_active ? 'Claude + rules engine' : 'Rules engine';

  return (
    <MetaCtx.Provider value={{ meta, status, go, refresh }}>
      <div className={'app' + (navOpen ? ' navopen' : '')}>
        <aside className="side" aria-label="Main navigation">
          <div className="brand"><span className="logo">Q</span><div><b>Quote-to-Delivery</b><span>JADA accelerator</span></div></div>
          <nav className="nav">{NAV[role].map((n) => n[0] === 'grp' ? <div key={n[1]} className="grp">{n[1]}</div> :
            <button key={n[0]} className={current?.[0] === n[0] ? 'on' : ''} aria-current={current?.[0] === n[0] ? 'page' : undefined} onClick={() => go(n[0])}>
              <Icon n={(n as any)[2]} /><span>{n[1]}</span>{badge(n[0]) ? <span className="badge">{badge(n[0])}</span> : null}</button>)}</nav>
          <div className="foot">
            <div className="envbox">
              <b>Demo workspace</b>
              <span>Sample data. All names and figures are made up. Demo date {status?.today_label ?? ''}.</span>
              {role === 'admin' && <span className="pill good dot">{aiLabel}</span>}
              <button className="btn sm" onClick={() => setResetOpen(true)}><Icon n="undo" />Start over</button>
            </div>
          </div>
        </aside>
        {navOpen && <button className="scrim" aria-label="Close menu" onClick={() => setNavOpen(false)} />}
        <div className="col">
          <header className="topbar">
            <button className="icon-btn navtoggle" aria-label="Open menu" onClick={() => setNavOpen(true)}><Icon n="menu" /></button>
            <div className="crumb"><b>{current?.[1] ?? 'Dashboard'}</b>{view === 'order' && sel && <><span className="sep">/</span><span className="muted mono">{sel}</span></>}</div>
            <button className="searchbtn" onClick={() => setSearchOpen(true)} aria-label="Search"><Icon n="search" /><span>Search or ask a question</span><kbd>Ctrl K</kbd></button>
            <span className="spacer" />
            {status?.running && <button className="pill acc dot busy-pill" onClick={() => go(role === 'sales' ? 'home' : 'runs', status.running!.id)}>Processing</button>}
            <button className="icon-btn" aria-label={attention ? `${attention} items need attention` : 'Nothing needs attention'} title="Needs attention" onClick={() => go(bellTo)}>
              <Icon n="bell" />{attention ? <span className="dotbadge">{attention}</span> : null}</button>
            <button className="icon-btn" aria-label={theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode'} onClick={toggleTheme}><Icon n={theme === 'dark' ? 'sun' : 'moon'} /></button>
            <div className="usermenu" ref={menuRef}>
              <button className="userbtn" aria-haspopup="menu" aria-expanded={menuOpen} onClick={() => setMenuOpen((o) => !o)}>
                <span className="av">{user!.initials}</span><span className="un"><b>{user!.name}</b><span>{user!.title}</span></span></button>
              {menuOpen && <div className="menu" role="menu">
                <div className="mh"><b>{user!.name}</b><span>{user!.email}</span></div>
                <button role="menuitem" onClick={() => { setMenuOpen(false); setResetOpen(true); }}><Icon n="undo" />Reset demo data</button>
                <button role="menuitem" onClick={signOutNow}><Icon n="swap" />Switch user</button>
                <button role="menuitem" onClick={signOutNow}><Icon n="out2" />Sign out</button>
              </div>}
            </div>
          </header>
          <main className="main"><div className="wrap">
            {err && <div className="banner bad"><Icon n="warn" /><div>Cannot reach the API: {err}</div></div>}
            {page}
          </div></main>
        </div>
      </div>
      {searchOpen && <Palette role={role} go={go} onClose={() => setSearchOpen(false)} />}
      {resetOpen && (
        <div className="overlay" role="dialog" aria-modal="true" aria-labelledby="rs-t" onClick={() => !resetting && setResetOpen(false)}>
          <div className="card" onClick={(e) => e.stopPropagation()}>
            <h2 id="rs-t" style={{ margin: 0 }}>Start over?</h2>
            <p className="muted" style={{ margin: 0 }}>This puts the demo back to the beginning for everyone: supplier emails unprocessed, the ERP and CRM as they were, and all activity, approvals and sent messages cleared. Your settings are kept.</p>
            <div className="row" style={{ justifyContent: 'flex-end' }}>
              <button className="btn" disabled={resetting} onClick={() => setResetOpen(false)}>Cancel</button>
              <button className="btn pri" disabled={resetting} onClick={doReset}>{resetting ? 'Resetting' : 'Reset demo data'}</button>
            </div>
          </div>
        </div>
      )}
      <Toaster />
    </MetaCtx.Provider>
  );
}
