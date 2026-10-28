import { useState } from 'react';
import { useAuth } from '../auth';
import { Icon } from '../lib';

export default function Login() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [err, setErr] = useState<string | null>(null);
  const submit = (e: React.FormEvent) => { e.preventDefault(); setErr(signIn(email, password)); };

  return (
    <div className="login">
      <section className="login-hero">
        <div className="login-brand"><span className="logo">Q</span><div><b>Quote-to-Delivery</b><span>A JADA accelerator</span></div></div>
        <div className="login-copy">
          <h1>Keep sales and supply promising the same date.</h1>
          <p>When a supplier moves a delivery, see every customer order it puts at risk, who is affected and what to tell them. Nothing reaches a customer until a person approves it.</p>
          <ul>
            <li><Icon n="mail" />Supplier emails are read and checked before the ERP changes</li>
            <li><Icon n="warn" />Late orders are found and ranked by customer and value</li>
            <li><Icon n="approve" />Customer updates are drafted for your approval</li>
          </ul>
        </div>
        <small>Sample data only. All companies, people and figures are made up.</small>
      </section>
      <section className="login-panel">
        <div className="login-stack">
          <form className="login-card" onSubmit={submit}>
            <h2>Sign in</h2>
            <p className="muted" style={{ margin: '-6px 0 0' }}>Use your work email. Your role and workspace are set from your account.</p>
            <label className="lf"><span>Email</span><input type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="you@company.com" required /></label>
            <label className="lf"><span>Password</span><input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></label>
            {err && <div className="lerr" role="alert"><Icon n="warn" />{err}</div>}
            <button className="btn pri lg" type="submit">Sign in</button>
          </form>
        </div>
      </section>
    </div>
  );
}
