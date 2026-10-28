import { Banner, Head, Icon, money } from '../lib';
import { useApp } from '../meta';

const JOBS = [
  ['Check a quote', 'A sales rep submits a quote', 'ERP stock and inbound POs, carrier lanes', 'Code', 'Recommendation on the CRM quote', 'The rep picks the final option'],
  ['Read a supplier email', 'An email lands in the supply inbox', 'Email, attachment, open POs', 'Rules engine (Claude optional)', 'Structured fields: PO, type, new date, confidence', 'PO must exist, date must be valid and new, confidence above the pass mark. Otherwise a planner checks.'],
  ['Update the ERP', 'The read passes every check', 'The PO record', 'Code', 'New arrival date on the PO', 'Only after the checks pass, or a planner confirms'],
  ['Find affected orders', 'A PO date changes, by email or in the ERP', 'Sales orders, PO allocations, carrier lanes', 'Code', 'List of orders now late', 'Same input, same answer, every time'],
  ['Rank customers', 'Late orders are found', 'Order value, CRM tier, renewal date', 'Code (score formula)', 'Priority order', 'The formula is shown in every run'],
  ['Write customer updates', 'Customers are ranked', 'CRM contacts and account owners', 'Templates (Claude optional)', 'Drafts in the approval queue, never sent directly', 'Wording check: must state the order and new date. Big orders need a manager.'],
];
const AGENT_STEPS: [string, string, string][] = [
  ['Wake on a trigger', 'New email, ERP change or quote', 'k-event'], ['Read the email', 'Rules engine', 'k-code'], ['Check the guardrails', 'Code', 'k-guard'],
  ['Update the ERP', 'Code', 'k-write'], ['Find and rank late orders', 'Code', 'k-code'], ['Draft and route updates', 'Templates, then code routes', 'k-code'],
];

const Box = ({ i, t, s }: { i: string; t: string; s: string }) => <div className="box"><Icon n={i} /><div><b>{t}</b><span>{s}</span></div></div>;

export default function How() {
  const { go, status } = useApp();
  return (
    <>
      <Head title="How the agent works" sub="The agent sits between your systems and your people. It wakes when something changes, does the reading and the maths, and stops for a person wherever the rules say so. Everything here runs on a simulated world you can change." />
      <div className="arch">
        <div className="col"><span className="sub">1 · Simulated world</span>
          <Box i="mail" t="Supplier mailbox" s="Emails and attachments arrive" /><Box i="erp" t="ERP" s="Stock, purchase orders, sales orders" />
          <Box i="crm" t="CRM" s="Customers, quotes, notes" /><Box i="out" t="Carriers and outbox" s="Transit days; what customers receive" /></div>
        <div className="flowarrow"><Icon n="arrow" /></div>
        <div className="col agentcol"><span className="sub">2 · The agent</span>
          {AGENT_STEPS.map(([t, s, k], i) => <div key={t} className={'box step2 ' + k}><span className="n">{i + 1}</span><div><b>{t}</b><span>{s}</span></div></div>)}</div>
        <div className="flowarrow"><Icon n="arrow" /></div>
        <div className="col"><span className="sub">3 · People</span>
          <Box i="approve" t="Planner" s="Checks emails the agent is unsure about" /><Box i="approve" t="Ops manager" s="Approves updates on big orders" />
          <Box i="quote" t="Sales rep" s="Chooses the quote option" /><Box i="crm" t="Customer" s="Gets only approved updates" /></div>
      </div>
      <div className="card">
        <div className="ch"><h2>Try it in three steps</h2><span className="muted">Right now: {status?.counts.unprocessed ?? 0} supplier emails not processed.</span></div>
        <div className="cb">
          <div className="try">
            <div><span className="n">1</span><b>Make something happen</b><span className="muted">You play the supplier or the planner. Send a supplier email, or change a PO date in the ERP.</span>
              <div className="row"><button className="btn pri" onClick={() => go('mailbox', 'compose')}><Icon n="mail" />Send a delay email</button><button className="btn" onClick={() => go('erp')}>Edit the ERP</button></div></div>
            <div><span className="n">2</span><b>Watch the agent</b><span className="muted">Each step shows what it read, who decided (Claude or code), and what it wrote.</span>
              <div className="row"><button className="btn" onClick={() => go('runs')}>Open agent runs</button></div></div>
            <div><span className="n">3</span><b>Act as the people</b><span className="muted">Check, edit or approve the drafts, then see what the customer received.</span>
              <div className="row"><button className="btn" onClick={() => go('approvals')}>Approvals</button><button className="btn" onClick={() => go('outbox')}>Customer outbox</button></div></div>
          </div>
          <Banner kind="acc" icon="scen"><b>Want proof it works?</b> Test scenarios run the agent on 14 known situations, each in its own copy of the world, and check the result against what should happen. <button className="btn sm" onClick={() => go('scen')}>Open test scenarios</button></Banner>
        </div>
      </div>
      <div className="card">
        <div className="ch"><h2>The agent's jobs</h2><span className="muted">Everything runs on deterministic rules and code: same input, same answer. Add an API key later and Claude can take over reading and writing; the maths and routing stay in code.</span></div>
        <div className="tscroll"><table className="tbl">
          <thead><tr><th>Job</th><th>Wakes when</th><th>Reads</th><th>Who decides</th><th>Writes</th><th>Guardrail</th></tr></thead>
          <tbody>{JOBS.map((j) => <tr key={j[0]}><td><b>{j[0]}</b></td><td>{j[1]}</td><td>{j[2]}</td><td><span className={'tagc ' + (j[3].includes('Claude') ? 'k-ai' : 'k-code')}>{j[3]}</span></td><td>{j[4]}</td><td>{j[5]}</td></tr>)}</tbody>
        </table></div>
      </div>
      <p className="muted" style={{ margin: 0, fontSize: 12.5 }}>Approval limit and pass mark are set in Settings. Default manager approval from {money(25000)}.</p>
    </>
  );
}
