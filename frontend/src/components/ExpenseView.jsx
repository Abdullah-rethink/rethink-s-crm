import React, { useEffect, useState } from 'react';
import { CreditCard, PlusCircle, Check, X, Mail, Filter, Wallet, Search, ChevronLeft, ChevronRight, LayoutGrid, List, Trash2, AlertTriangle, Settings, Eye, EyeOff, SendHorizonal, ChevronDown, ChevronUp, ShieldCheck, Wifi, WifiOff } from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function ExpenseView({ user }) {
  const [codes, setCodes] = useState([]);
  const [expensesData, setExpensesData] = useState({ summary: {}, expenses: [] });
  const [loading, setLoading] = useState(true);
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [showSubmitModal, setShowSubmitModal] = useState(false);

  // Search & Pagination State for Code Balances
  const [codeSearch, setCodeSearch] = useState('');
  const [viewMode, setViewMode] = useState('table'); // 'table' or 'grid'
  const [codePage, setCodePage] = useState(1);
  const [codePageSize, setCodePageSize] = useState(6);

  // Form State
  const [selectedCode, setSelectedCode] = useState('');
  const [heading, setHeading] = useState('');
  const [subHeading, setSubHeading] = useState('');
  const [country, setCountry] = useState('');
  const [title, setTitle] = useState('');
  const [vendor, setVendor] = useState('');
  const [amount, setAmount] = useState('');
  const [paymentDate, setPaymentDate] = useState(new Date().toISOString().split('T')[0]);
  const [notes, setNotes] = useState('');

  const [formMsg, setFormMsg] = useState('');
  const [reviewMsg, setReviewMsg] = useState('');
  const [submitting, setSubmitting] = useState(false);

  // Delete confirmation state
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // SMTP / Email Settings State (Super Admin only)
  const [showSettings, setShowSettings] = useState(false);
  const [smtpSettings, setSmtpSettings] = useState({
    approval_email: '',
    smtp_host: 'smtp.gmail.com',
    smtp_port: 587,
    smtp_user: '',
    smtp_password: '',
    smtp_from_name: 'Rethink Charity CRM',
    smtp_from_email: '',
  });
  const [smtpPasswordSet, setSmtpPasswordSet] = useState(false);
  const [smtpConfigured, setSmtpConfigured] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [settingsMsg, setSettingsMsg] = useState('');
  const [savingSettings, setSavingSettings] = useState(false);
  const [testingEmail, setTestingEmail] = useState(false);

  const isSuperAdmin = user?.role === 'super_admin' || user?.can_edit_donors === 1;

  const loadSettings = () => {
    fetch(`${API_BASE_URL}/api/expenses/settings`)
      .then(r => r.json())
      .then(data => {
        setSmtpSettings({
          approval_email: data.approval_email || '',
          smtp_host: data.smtp_host || 'smtp.gmail.com',
          smtp_port: data.smtp_port || 587,
          smtp_user: data.smtp_user || '',
          smtp_password: '',  // never pre-fill password
          smtp_from_name: data.smtp_from_name || 'Rethink Charity CRM',
          smtp_from_email: data.smtp_from_email || '',
        });
        setSmtpPasswordSet(data.smtp_password_set || false);
        setSmtpConfigured(data.smtp_configured || false);
      })
      .catch(() => {});
  };

  const handleSaveSettings = (e) => {
    e.preventDefault();
    setSavingSettings(true);
    setSettingsMsg('');
    fetch(`${API_BASE_URL}/api/expenses/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ...smtpSettings, user_role: user?.role })
    })
      .then(r => r.json())
      .then(res => {
        setSavingSettings(false);
        if (res?.status === 'success') {
          setSettingsMsg('✅ ' + res.message);
          loadSettings();
          setTimeout(() => setSettingsMsg(''), 4000);
        } else {
          setSettingsMsg('❌ ' + (res?.detail || 'Failed to save settings.'));
        }
      })
      .catch(err => { setSavingSettings(false); setSettingsMsg('❌ ' + err.message); });
  };

  const handleTestEmail = () => {
    setTestingEmail(true);
    setSettingsMsg('');
    fetch(`${API_BASE_URL}/api/expenses/test-email`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ user_role: user?.role, can_edit_donors: true })
    })
      .then(r => r.json())
      .then(res => {
        setTestingEmail(false);
        if (res?.status === 'success') {
          setSettingsMsg('✅ ' + res.message);
        } else {
          setSettingsMsg('❌ ' + (res?.detail || 'Test email failed.'));
        }
        setTimeout(() => setSettingsMsg(''), 6000);
      })
      .catch(err => { setTestingEmail(false); setSettingsMsg('❌ ' + err.message); });
  };

  const loadCodes = () => {
    fetch(`${API_BASE_URL}/api/expenses/codes`)
      .then(res => res.json())
      .then(data => setCodes(data))
      .catch(err => console.error('Error fetching project codes:', err));
  };

  const loadExpenses = () => {
    setLoading(true);
    fetch(`${API_BASE_URL}/api/expenses/requests?status_filter=${statusFilter}`)
      .then(res => res.json())
      .then(data => {
        setExpensesData(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching expense requests:', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadCodes();
    if (isSuperAdmin) loadSettings();
  }, []);

  useEffect(() => {
    loadExpenses();
  }, [statusFilter]);

  // Handle Code Selection & Auto-Fill Heading, Sub-Heading, Country
  const handleCodeSelect = (e) => {
    const codeVal = e.target.value;
    setSelectedCode(codeVal);
    const matched = codes.find(c => c.code === codeVal);
    if (matched) {
      setHeading(matched.heading || 'Unassigned');
      setSubHeading(matched.sub_heading || 'Unassigned');
      setCountry(matched.country || 'Unassigned');
    } else {
      setHeading('');
      setSubHeading('');
      setCountry('');
    }
  };

  // Submit Expense Request
  const handleSubmitExpense = (e) => {
    e.preventDefault();
    if (!selectedCode || !amount || !title) {
      setFormMsg('❌ Please fill in all required fields (Code, Title, Amount).');
      return;
    }
    setSubmitting(true);
    setFormMsg('');

    fetch(`${API_BASE_URL}/api/expenses/submit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        code: selectedCode,
        title: title,
        vendor: vendor || 'Unassigned Vendor',
        amount: parseFloat(amount),
        payment_date: paymentDate,
        notes: notes,
        requested_by: user?.email || user?.display_name || 'Admin User'
      })
    })
      .then(r => {
        if (r.status === 409) {
          return r.json().then(data => {
            setSubmitting(false);
            setFormMsg(`⚠️ ${data.detail || 'Duplicate expense detected. Please wait or modify the details.'}`);
            return null;
          });
        }
        return r.json();
      })
      .then(res => {
        if (!res) return;
        setSubmitting(false);
        if (res?.status === 'success') {
          let msg = `✅ ${res.message}`;
          if (res.email_warning) {
            msg += ` ⚠️ ${res.email_warning}`;
          }
          setFormMsg(msg);
          setTimeout(() => {
            setShowSubmitModal(false);
            setFormMsg('');
            setSelectedCode('');
            setHeading('');
            setSubHeading('');
            setCountry('');
            setTitle('');
            setVendor('');
            setAmount('');
            setNotes('');
            loadExpenses();
            loadCodes();
          }, 2000);
        } else {
          setFormMsg(`❌ ${res?.detail || 'Failed to submit expense.'}`);
        }
      })
      .catch(err => {
        setSubmitting(false);
        setFormMsg(`❌ Error: ${err.message}`);
      });
  };

  // Review Expense (Approve / Reject)
  const handleReview = (expenseId, action) => {
    if (!isSuperAdmin) return;
    setReviewMsg('');

    fetch(`${API_BASE_URL}/api/expenses/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expense_id: expenseId,
        user_role: user?.role,
        action: action,
        can_edit_donors: true,
        review_notes: `Reviewed via CRM Dashboard by ${user?.email}`
      })
    })
      .then(r => r.json())
      .then(res => {
        if (res?.status === 'success') {
          setReviewMsg(`✅ ${res.message}`);
          loadExpenses();
          loadCodes();
          setTimeout(() => setReviewMsg(''), 3000);
        } else {
          setReviewMsg(`❌ ${res?.detail || 'Review failed.'}`);
        }
      });
  };

  // Delete Expense
  const handleDelete = (expenseId) => {
    if (!isSuperAdmin) return;
    setDeleting(true);

    fetch(`${API_BASE_URL}/api/expenses/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        expense_id: expenseId,
        user_role: user?.role,
        can_edit_donors: true
      })
    })
      .then(r => r.json())
      .then(res => {
        setDeleting(false);
        setDeleteConfirm(null);
        if (res?.status === 'success') {
          setReviewMsg(`🗑️ ${res.message}`);
          loadExpenses();
          loadCodes();
          setTimeout(() => setReviewMsg(''), 4000);
        } else {
          setReviewMsg(`❌ ${res?.detail || 'Delete failed.'}`);
        }
      })
      .catch(err => {
        setDeleting(false);
        setDeleteConfirm(null);
        setReviewMsg(`❌ Error: ${err.message}`);
      });
  };

  // Filter & Paginate Code Balances
  const filteredCodes = codes.filter(c => {
    if (!codeSearch) return true;
    const term = codeSearch.toLowerCase();
    return (
      c.code.toLowerCase().includes(term) ||
      c.heading.toLowerCase().includes(term) ||
      c.sub_heading.toLowerCase().includes(term) ||
      c.country.toLowerCase().includes(term)
    );
  });

  const totalCodePages = Math.ceil(filteredCodes.length / codePageSize) || 1;
  const paginatedCodes = filteredCodes.slice((codePage - 1) * codePageSize, codePage * codePageSize);

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-extrabold flex items-center gap-2" style={{ color: 'var(--text-main)' }}>
            <CreditCard className="w-5 h-5 text-cyan-400" /> Category Expense & Payment Tracker
          </h2>
          <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Approved expenses automatically deduct from total category/code donations in real time (singleton state).</p>
        </div>

        <div className="flex items-center gap-3">
          <button 
            onClick={() => setShowSubmitModal(true)}
            className="btn-primary text-xs flex items-center gap-1.5 shadow-lg shadow-cyan-500/20"
          >
            <PlusCircle className="w-4 h-4" /> Submit Expense Request
          </button>
        </div>
      </div>

      {reviewMsg && <div className="text-xs font-bold text-emerald-400 bg-emerald-500/10 p-3 rounded-lg border border-emerald-500/20">{reviewMsg}</div>}

      {/* ── Super Admin: Email & SMTP Settings Panel ───────────────── */}
      {isSuperAdmin && (
        <div className="glass-panel border-l-4 border-amber-400 overflow-hidden">
          {/* Collapsible Header */}
          <button
            onClick={() => setShowSettings(s => !s)}
            className="w-full flex items-center justify-between p-4 transition-colors hover:bg-amber-500/5"
          >
            <div className="flex items-center gap-3">
              <div className="p-1.5 rounded-lg bg-amber-500/15">
                <Settings className="w-4 h-4 text-amber-400" />
              </div>
              <div className="text-left">
                <div className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--text-main)' }}>
                  Email &amp; SMTP Settings
                  <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-black border ${
                    smtpConfigured
                      ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                      : 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                  }`}>
                    {smtpConfigured ? <><Wifi className="w-2.5 h-2.5" /> SMTP LIVE</> : <><WifiOff className="w-2.5 h-2.5" /> NOT CONFIGURED</>}
                  </span>
                </div>
                <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>Configure SMTP server for approval email delivery</div>
              </div>
            </div>
            {showSettings ? <ChevronUp className="w-4 h-4" style={{ color: 'var(--text-muted)' }} /> : <ChevronDown className="w-4 h-4" style={{ color: 'var(--text-muted)' }} />}
          </button>

          {/* Expanded Settings Form */}
          {showSettings && (
            <div className="p-5 pt-0 border-t" style={{ borderColor: 'var(--border-glass)' }}>
              {settingsMsg && (
                <div className={`mt-4 mb-3 text-xs font-bold p-3 rounded-lg border ${
                  settingsMsg.startsWith('✅') ? 'text-emerald-400 bg-emerald-500/10 border-emerald-500/30' : 'text-rose-400 bg-rose-500/10 border-rose-500/30'
                }`}>
                  {settingsMsg}
                </div>
              )}

              <form onSubmit={handleSaveSettings} className="flex flex-col gap-4 mt-4">
                {/* Row 1: Approval Recipient */}
                <div>
                  <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                    <Mail className="w-3.5 h-3.5 inline mr-1 text-amber-400" />Approval Email Recipient *
                  </label>
                  <input
                    type="email" required
                    placeholder="office@rethinkcharity.org.uk"
                    value={smtpSettings.approval_email}
                    onChange={e => setSmtpSettings(s => ({ ...s, approval_email: e.target.value }))}
                    className="w-full rounded-lg px-3 py-2 text-xs focus:outline-none"
                    style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                  />
                  <p className="text-[10px] mt-1" style={{ color: 'var(--text-sub)' }}>Email address that receives expense approval notifications</p>
                </div>

                <div className="border-t pt-4" style={{ borderColor: 'var(--border-glass)' }}>
                  <div className="text-xs font-bold uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                    <ShieldCheck className="w-3.5 h-3.5 text-amber-400" /> SMTP Server Configuration
                  </div>

                  {/* SMTP Host + Port */}
                  <div className="grid grid-cols-3 gap-3 mb-3">
                    <div className="col-span-2">
                      <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>SMTP Host</label>
                      <input
                        type="text" required
                        placeholder="smtp.gmail.com"
                        value={smtpSettings.smtp_host}
                        onChange={e => setSmtpSettings(s => ({ ...s, smtp_host: e.target.value }))}
                        className="w-full rounded-lg px-3 py-2 text-xs font-mono focus:outline-none"
                        style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>Port</label>
                      <input
                        type="number" required min="1" max="65535"
                        value={smtpSettings.smtp_port}
                        onChange={e => setSmtpSettings(s => ({ ...s, smtp_port: parseInt(e.target.value) || 587 }))}
                        className="w-full rounded-lg px-3 py-2 text-xs font-mono focus:outline-none"
                        style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                      />
                    </div>
                  </div>

                  {/* SMTP User + Password */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-3">
                    <div>
                      <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>SMTP Username / Email</label>
                      <input
                        type="email"
                        placeholder="your@gmail.com"
                        value={smtpSettings.smtp_user}
                        onChange={e => setSmtpSettings(s => ({ ...s, smtp_user: e.target.value }))}
                        className="w-full rounded-lg px-3 py-2 text-xs focus:outline-none"
                        style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                        SMTP Password / App Password
                        {smtpPasswordSet && <span className="ml-2 text-emerald-400 font-bold">● saved</span>}
                      </label>
                      <div className="relative">
                        <input
                          type={showPassword ? 'text' : 'password'}
                          placeholder={smtpPasswordSet ? '••••••••• (leave blank to keep)' : 'Enter App Password'}
                          value={smtpSettings.smtp_password}
                          onChange={e => setSmtpSettings(s => ({ ...s, smtp_password: e.target.value }))}
                          className="w-full rounded-lg px-3 pr-8 py-2 text-xs focus:outline-none"
                          style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                        />
                        <button
                          type="button"
                          onClick={() => setShowPassword(v => !v)}
                          className="absolute right-2.5 top-1/2 -translate-y-1/2"
                          style={{ color: 'var(--text-sub)' }}
                        >
                          {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                        </button>
                      </div>
                      <p className="text-[10px] mt-1" style={{ color: 'var(--text-sub)' }}>
                        Gmail: generate at <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noreferrer" className="text-cyan-400 underline">myaccount.google.com/apppasswords</a>
                      </p>
                    </div>
                  </div>

                  {/* Sender Name + From Email */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                    <div>
                      <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>Sender Display Name</label>
                      <input
                        type="text"
                        placeholder="Rethink Charity CRM"
                        value={smtpSettings.smtp_from_name}
                        onChange={e => setSmtpSettings(s => ({ ...s, smtp_from_name: e.target.value }))}
                        className="w-full rounded-lg px-3 py-2 text-xs focus:outline-none"
                        style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                      />
                    </div>
                    <div>
                      <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>From Email Address</label>
                      <input
                        type="email"
                        placeholder="Same as SMTP user if left blank"
                        value={smtpSettings.smtp_from_email}
                        onChange={e => setSmtpSettings(s => ({ ...s, smtp_from_email: e.target.value }))}
                        className="w-full rounded-lg px-3 py-2 text-xs focus:outline-none"
                        style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                      />
                    </div>
                  </div>
                </div>

                {/* Action Buttons */}
                <div className="flex items-center justify-between gap-3 pt-2 border-t" style={{ borderColor: 'var(--border-glass)' }}>
                  <button
                    type="button"
                    onClick={handleTestEmail}
                    disabled={testingEmail || !smtpConfigured}
                    title={!smtpConfigured ? 'Save SMTP credentials first to enable test' : 'Send a test email to the approval recipient'}
                    className="flex items-center gap-1.5 px-4 py-2 rounded-lg text-xs font-bold border transition-all disabled:opacity-40"
                    style={{
                      color: smtpConfigured ? 'var(--accent-cyan)' : 'var(--text-sub)',
                      borderColor: smtpConfigured ? 'var(--accent-cyan)' : 'var(--border-glass)',
                      backgroundColor: 'transparent'
                    }}
                  >
                    <SendHorizonal className="w-3.5 h-3.5" />
                    {testingEmail ? 'Sending...' : 'Send Test Email'}
                  </button>

                  <button
                    type="submit"
                    disabled={savingSettings}
                    className="btn-primary text-xs flex items-center gap-1.5"
                  >
                    <Settings className="w-3.5 h-3.5" />
                    {savingSettings ? 'Saving...' : 'Save Settings'}
                  </button>
                </div>
              </form>
            </div>
          )}
        </div>
      )}

      {/* KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4">
        <div className="glass-panel p-4 border-l-4 border-cyan-400">
          <div className="text-xs font-bold uppercase" style={{ color: 'var(--text-muted)' }}>Total Requested</div>
          <div className="text-2xl font-black text-cyan-400 mt-1">£{expensesData.summary?.total_requested?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
          <div className="text-[11px] font-medium mt-0.5" style={{ color: 'var(--text-sub)' }}>{expensesData.summary?.total_count || 0} Total Claims Submitted</div>
        </div>

        <div className="glass-panel p-4 border-l-4 border-emerald-400">
          <div className="text-xs font-bold uppercase" style={{ color: 'var(--text-muted)' }}>Approved Amount</div>
          <div className="text-2xl font-black text-emerald-400 mt-1">£{expensesData.summary?.total_approved?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
          <div className="text-[11px] text-emerald-500 font-bold mt-0.5">{expensesData.summary?.count_approved || 0} Approved Expenses</div>
        </div>

        <div className="glass-panel p-4 border-l-4 border-amber-400">
          <div className="text-xs font-bold uppercase" style={{ color: 'var(--text-muted)' }}>Pending Approval</div>
          <div className="text-2xl font-black text-amber-400 mt-1">£{expensesData.summary?.total_pending?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
          <div className="text-[11px] text-amber-500 font-bold mt-0.5">{expensesData.summary?.count_pending || 0} Awaiting Review</div>
        </div>

        <div className="glass-panel p-4 border-l-4 border-rose-400">
          <div className="text-xs font-bold uppercase" style={{ color: 'var(--text-muted)' }}>Rejected Amount</div>
          <div className="text-2xl font-black text-rose-400 mt-1">£{expensesData.summary?.total_rejected?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
          <div className="text-[11px] text-rose-500 font-bold mt-0.5">{expensesData.summary?.count_rejected || 0} Declined Requests</div>
        </div>
      </div>

      {/* Code Net Available Balance Tracker (Paginated & Theme-Safe UX) */}
      <div className="glass-panel p-5 border-l-4 border-purple-400 flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-3">
          <div>
            <h3 className="text-sm font-bold flex items-center gap-2" style={{ color: 'var(--text-main)' }}>
              <Wallet className="w-4 h-4 text-purple-400" /> Project Code Net Balances (Donations - Approved Expenses)
            </h3>
            <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>Live gross donation revenue minus approved category expenses per project code.</p>
          </div>

          {/* Search, View Mode Toggle & Page Controls */}
          <div className="flex items-center gap-3 flex-wrap">
            {/* Instant Search Bar */}
            <div className="relative flex items-center">
              <Search className="w-3.5 h-3.5 absolute left-3" style={{ color: 'var(--text-sub)' }} />
              <input 
                type="text"
                placeholder="Search code, country, heading..."
                value={codeSearch}
                onChange={e => {
                  setCodeSearch(e.target.value);
                  setCodePage(1);
                }}
                className="pl-8 pr-3 py-1.5 rounded-xl text-xs font-medium w-60 transition-all focus:outline-none"
                style={{
                  backgroundColor: 'var(--input-bg)',
                  color: 'var(--input-text)',
                  borderColor: 'var(--input-border)',
                  borderWidth: '1px',
                  borderStyle: 'solid'
                }}
              />
              {codeSearch && (
                <button 
                  onClick={() => setCodeSearch('')}
                  className="absolute right-2.5 text-xs font-bold"
                  style={{ color: 'var(--text-sub)' }}
                >
                  ✕
                </button>
              )}
            </div>

            {/* View Mode Toggle Buttons */}
            <div className="flex items-center p-1 rounded-xl" style={{ backgroundColor: 'var(--bg-card-inner)', border: '1px solid var(--border-glass)' }}>
              <button
                onClick={() => setViewMode('table')}
                className={`p-1.5 rounded-lg text-xs font-bold flex items-center gap-1 transition-all ${
                  viewMode === 'table' ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : ''
                }`}
                style={{ color: viewMode === 'table' ? '' : 'var(--text-muted)' }}
                title="Compact Table View"
              >
                <List className="w-3.5 h-3.5" /> Table
              </button>
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1.5 rounded-lg text-xs font-bold flex items-center gap-1 transition-all ${
                  viewMode === 'grid' ? 'bg-purple-500/20 text-purple-400 border border-purple-500/30' : ''
                }`}
                style={{ color: viewMode === 'grid' ? '' : 'var(--text-muted)' }}
                title="Card Grid View"
              >
                <LayoutGrid className="w-3.5 h-3.5" /> Cards
              </button>
            </div>
          </div>
        </div>

        {/* Paginated Balances Display */}
        {filteredCodes.length === 0 ? (
          <div className="py-8 text-center text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
            No project codes found matching search term '{codeSearch}'.
          </div>
        ) : viewMode === 'table' ? (
          /* Compact Table View */
          <div className="overflow-x-auto rounded-xl border" style={{ borderColor: 'var(--border-glass)' }}>
            <table className="crm-table">
              <thead>
                <tr>
                  <th>Code</th>
                  <th>Country</th>
                  <th>Category Heading</th>
                  <th>Sub-Heading</th>
                  <th className="text-right">Gross Raised</th>
                  <th className="text-right">Approved Deductions</th>
                  <th className="text-right">Net Remaining Balance</th>
                </tr>
              </thead>
              <tbody>
                {paginatedCodes.map(b => (
                  <tr key={b.code} className="hover:bg-cyan-500/5 transition-colors">
                    <td className="font-mono text-xs font-bold text-cyan-400">{b.code}</td>
                    <td>
                      <span className="badge badge-emerald">{b.country}</span>
                    </td>
                    <td className="text-xs font-bold" style={{ color: 'var(--text-main)' }}>{b.heading}</td>
                    <td className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{b.sub_heading}</td>
                    <td className="text-right text-xs font-bold" style={{ color: 'var(--text-main)' }}>
                      £{b.gross_raised?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </td>
                    <td className="text-right text-xs font-medium">
                      <span className={b.approved_expenses > 0 ? 'font-bold text-rose-400' : ''} style={{ color: b.approved_expenses > 0 ? '#F87171' : 'var(--text-muted)' }}>
                        {b.approved_expenses > 0 ? `-£${b.approved_expenses?.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '£0.00'}
                      </span>
                    </td>
                    <td className="text-right text-xs font-black">
                      <span className={b.net_balance >= 0 ? 'text-emerald-400 font-extrabold' : 'text-rose-400 font-extrabold'}>
                        £{b.net_balance?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          /* Card Grid View */
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {paginatedCodes.map(b => (
              <div 
                key={b.code} 
                className="p-4 rounded-xl border flex flex-col gap-2 transition-all shadow-sm hover:border-purple-400"
                style={{
                  backgroundColor: 'var(--bg-card-inner)',
                  borderColor: 'var(--border-glass)'
                }}
              >
                <div className="flex items-center justify-between">
                  <span className="font-mono text-xs font-black text-cyan-400 tracking-wide">{b.code}</span>
                  <span className="badge badge-emerald">{b.country}</span>
                </div>

                <div className="text-xs font-bold truncate mt-0.5" style={{ color: 'var(--text-main)' }} title={b.heading}>{b.heading}</div>
                <div className="text-[11px] truncate" style={{ color: 'var(--text-muted)' }} title={b.sub_heading}>{b.sub_heading}</div>

                <div className="border-t pt-2.5 mt-1 flex flex-col gap-1.5" style={{ borderColor: 'var(--border-glass)' }}>
                  <div className="flex justify-between text-xs">
                    <span style={{ color: 'var(--text-muted)' }}>Gross Raised:</span>
                    <span className="font-bold" style={{ color: 'var(--text-main)' }}>£{b.gross_raised?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                  </div>

                  <div className="flex justify-between text-xs">
                    <span style={{ color: 'var(--text-muted)' }}>Approved Deductions:</span>
                    <span className={b.approved_expenses > 0 ? 'font-bold text-rose-400' : ''} style={{ color: b.approved_expenses > 0 ? '#F87171' : 'var(--text-muted)' }}>
                      {b.approved_expenses > 0 ? `-£${b.approved_expenses?.toLocaleString(undefined, { minimumFractionDigits: 2 })}` : '£0.00'}
                    </span>
                  </div>

                  <div className="flex justify-between text-xs border-t pt-1.5 font-black" style={{ borderColor: 'var(--border-glass)' }}>
                    <span className="text-purple-400 font-bold">Net Remaining:</span>
                    <span className={b.net_balance >= 0 ? 'text-emerald-400 font-extrabold' : 'text-rose-400 font-extrabold'}>
                      £{b.net_balance?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Pagination Bar for Code Balances */}
        <div className="flex items-center justify-between pt-2 flex-wrap gap-3 border-t" style={{ borderColor: 'var(--border-glass)' }}>
          <div className="text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
            Showing {filteredCodes.length === 0 ? 0 : (codePage - 1) * codePageSize + 1} - {Math.min(codePage * codePageSize, filteredCodes.length)} of <span className="font-bold" style={{ color: 'var(--text-main)' }}>{filteredCodes.length}</span> project codes
          </div>

          <div className="flex items-center gap-2">
            <button
              disabled={codePage <= 1}
              onClick={() => setCodePage(prev => Math.max(prev - 1, 1))}
              className="btn-secondary text-xs px-2.5 py-1 rounded-lg flex items-center gap-1 disabled:opacity-40"
            >
              <ChevronLeft className="w-3.5 h-3.5" /> Prev
            </button>
            <span className="text-xs font-bold px-2" style={{ color: 'var(--text-main)' }}>
              Page {codePage} of {totalCodePages}
            </span>
            <button
              disabled={codePage >= totalCodePages}
              onClick={() => setCodePage(prev => Math.min(prev + 1, totalCodePages))}
              className="btn-secondary text-xs px-2.5 py-1 rounded-lg flex items-center gap-1 disabled:opacity-40"
            >
              Next <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b pb-3" style={{ borderColor: 'var(--border-glass)' }}>
        <Filter className="w-4 h-4 ml-1" style={{ color: 'var(--text-muted)' }} />
        <span className="text-xs font-bold mr-2" style={{ color: 'var(--text-muted)' }}>Filter Claims Status:</span>
        {['ALL', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED'].map(st => (
          <button
            key={st}
            onClick={() => setStatusFilter(st)}
            className={`btn-secondary text-xs px-3.5 py-1.5 rounded-lg font-bold transition-all ${
              statusFilter === st 
                ? 'bg-cyan-500/20 text-cyan-400 border-cyan-400 shadow-md shadow-cyan-500/10' 
                : 'border-transparent'
            }`}
            style={{ color: statusFilter === st ? '' : 'var(--text-muted)' }}
          >
            {st === 'ALL' ? 'All Expenses' : st === 'PENDING_APPROVAL' ? '⏳ Pending' : st === 'APPROVED' ? '✓ Approved' : '✗ Rejected'}
          </button>
        ))}
      </div>

      {/* Expense Log Table */}
      {loading ? (
        <div className="py-24 text-center text-xs font-semibold animate-pulse" style={{ color: 'var(--text-muted)' }}>
          ⚡ Loading Expense Records...
        </div>
      ) : (
        <div className="glass-panel overflow-hidden">
          <div className="overflow-x-auto max-h-[580px] custom-scrollbar">
            <table className="crm-table">
              <thead>
                <tr>
                  <th>Expense ID</th>
                  <th>Date</th>
                  <th>Project Code</th>
                  <th>Category Heading</th>
                  <th>Sub-Heading</th>
                  <th>Country</th>
                  <th>Title & Vendor</th>
                  <th>Amount</th>
                  <th>Status</th>
                  {isSuperAdmin && <th className="text-right">Actions</th>}
                </tr>
              </thead>
              <tbody>
                {expensesData.expenses?.length === 0 ? (
                  <tr>
                    <td colSpan={isSuperAdmin ? 10 : 9} className="text-center py-12 text-xs font-semibold" style={{ color: 'var(--text-muted)' }}>
                      No expense claims found matching filter '{statusFilter}'.
                    </td>
                  </tr>
                ) : (
                  expensesData.expenses?.map(exp => (
                    <tr key={exp.id} className="hover:bg-cyan-500/5 transition-colors">
                      <td className="font-mono text-xs font-bold text-cyan-400">{exp.id}</td>
                      <td className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{exp.payment_date}</td>
                      <td className="font-mono text-xs font-bold text-purple-400">{exp.code}</td>
                      <td className="text-xs font-semibold" style={{ color: 'var(--text-main)' }}>{exp.heading}</td>
                      <td className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>{exp.sub_heading}</td>
                      <td className="text-xs font-medium">
                        <span className="badge badge-emerald">{exp.country}</span>
                      </td>
                      <td>
                        <div className="text-xs font-bold" style={{ color: 'var(--text-main)' }}>{exp.title}</div>
                        <div className="text-[11px]" style={{ color: 'var(--text-muted)' }}>{exp.vendor}</div>
                      </td>
                      <td className="font-black text-sm text-cyan-400">
                        £{exp.amount?.toLocaleString(undefined, { minimumFractionDigits: 2 })}
                      </td>
                      <td>
                        <span className={`badge ${
                          exp.status === 'APPROVED' ? 'badge-emerald' : exp.status === 'PENDING_APPROVAL' ? 'badge-amber' : 'badge-pink'
                        }`}>
                          {exp.status === 'APPROVED' ? '✓ APPROVED' : exp.status === 'PENDING_APPROVAL' ? '⏳ PENDING' : '✗ REJECTED'}
                        </span>
                      </td>

                      {isSuperAdmin && (
                        <td className="text-right">
                          <div className="flex items-center justify-end gap-2">
                            {exp.status === 'PENDING_APPROVAL' && (
                              <>
                                <button
                                  onClick={() => handleReview(exp.id, 'APPROVED')}
                                  className="px-2.5 py-1 bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-400 border border-emerald-500/40 rounded text-xs font-bold flex items-center gap-1 transition-all"
                                >
                                  <Check className="w-3.5 h-3.5" /> Approve
                                </button>
                                <button
                                  onClick={() => handleReview(exp.id, 'REJECTED')}
                                  className="px-2.5 py-1 bg-rose-500/20 hover:bg-rose-500/30 text-rose-400 border border-rose-500/40 rounded text-xs font-bold flex items-center gap-1 transition-all"
                                >
                                  <X className="w-3.5 h-3.5" /> Reject
                                </button>
                              </>
                            )}
                            {exp.status !== 'PENDING_APPROVAL' && (
                              <span className="text-[11px] font-semibold italic mr-2" style={{ color: 'var(--text-sub)' }}>
                                {exp.reviewed_by || 'Super Admin'}
                              </span>
                            )}
                            {/* Delete Button */}
                            {deleteConfirm === exp.id ? (
                              <div className="flex items-center gap-1.5">
                                <button
                                  onClick={() => handleDelete(exp.id)}
                                  disabled={deleting}
                                  className="px-2 py-1 bg-red-600/30 hover:bg-red-600/50 text-red-300 border border-red-500/50 rounded text-[11px] font-bold flex items-center gap-1 transition-all"
                                >
                                  <AlertTriangle className="w-3 h-3" /> {deleting ? 'Deleting...' : 'Confirm'}
                                </button>
                                <button
                                  onClick={() => setDeleteConfirm(null)}
                                  className="px-2 py-1 rounded text-[11px] font-bold transition-all"
                                  style={{ color: 'var(--text-muted)' }}
                                >
                                  Cancel
                                </button>
                              </div>
                            ) : (
                              <button
                                onClick={() => setDeleteConfirm(exp.id)}
                                className="px-2 py-1 bg-slate-500/10 hover:bg-red-500/15 hover:text-red-400 border border-transparent hover:border-red-500/30 rounded text-[11px] font-bold flex items-center gap-1 transition-all"
                                style={{ color: 'var(--text-sub)' }}
                                title="Delete this expense"
                              >
                                <Trash2 className="w-3 h-3" />
                              </button>
                            )}
                          </div>
                        </td>
                      )}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Submit Expense Request Modal */}
      {showSubmitModal && (
        <div className="drawer-backdrop flex items-center justify-center p-4">
          <div className="glass-panel p-6 w-full max-w-xl border-l-4 border-cyan-400 flex flex-col gap-5 shadow-2xl animate-in fade-in zoom-in duration-200">
            <div className="flex items-center justify-between border-b pb-3" style={{ borderColor: 'var(--border-glass)' }}>
              <h3 className="text-base font-extrabold flex items-center gap-2" style={{ color: 'var(--text-main)' }}>
                <PlusCircle className="w-5 h-5 text-cyan-400" /> New Category Expense Claim Request
              </h3>
              <button 
                onClick={() => setShowSubmitModal(false)}
                className="text-lg font-bold transition-colors"
                style={{ color: 'var(--text-muted)' }}
              >
                ✕
              </button>
            </div>

            {formMsg && (
              <div className={`text-xs font-bold p-3 rounded-lg border ${
                formMsg.startsWith('⚠️') 
                  ? 'text-amber-400 bg-amber-500/10 border-amber-500/30' 
                  : formMsg.startsWith('❌') 
                    ? 'text-rose-400 bg-rose-500/10 border-rose-500/30'
                    : 'text-cyan-400 bg-cyan-500/10 border-cyan-500/30'
              }`}>
                {formMsg}
              </div>
            )}

            <form onSubmit={handleSubmitExpense} className="flex flex-col gap-4">
              {/* Select Project Code Dropdown */}
              <div>
                <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                  1. Select Project Code * <span className="text-cyan-400 font-normal">(Auto-fills Category Details)</span>
                </label>
                <select
                  required
                  value={selectedCode}
                  onChange={handleCodeSelect}
                  className="w-full rounded-lg px-3 py-2 text-xs font-mono focus:outline-none"
                  style={{
                    backgroundColor: 'var(--input-bg)',
                    color: 'var(--input-text)',
                    borderColor: 'var(--input-border)',
                    borderWidth: '1px',
                    borderStyle: 'solid'
                  }}
                >
                  <option value="">-- Choose Campaign Code --</option>
                  {codes.map(c => (
                    <option key={c.code} value={c.code}>
                      {c.code} — {c.heading} ({c.country})
                    </option>
                  ))}
                </select>
              </div>

              {/* Auto-Filled Details Readonly Group */}
              {selectedCode && (
                <div className="grid grid-cols-3 gap-3 p-3 rounded-lg border" style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}>
                  <div>
                    <span className="block text-[10px] font-bold uppercase" style={{ color: 'var(--text-muted)' }}>Category Heading</span>
                    <span className="text-xs font-extrabold text-cyan-400 truncate block">{heading || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] font-bold uppercase" style={{ color: 'var(--text-muted)' }}>Sub-Heading</span>
                    <span className="text-xs font-extrabold text-purple-400 truncate block">{subHeading || 'N/A'}</span>
                  </div>
                  <div>
                    <span className="block text-[10px] font-bold uppercase" style={{ color: 'var(--text-muted)' }}>Project Country</span>
                    <span className="text-xs font-extrabold text-emerald-400 truncate block">{country || 'N/A'}</span>
                  </div>
                </div>
              )}

              {/* Title & Vendor */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>Expense Title / Purpose *</label>
                  <input 
                    type="text" 
                    required
                    placeholder="e.g. Water Well Drilling Phase 1"
                    value={title}
                    onChange={e => setTitle(e.target.value)}
                    className="w-full rounded-lg px-3 py-2 text-xs focus:outline-none"
                    style={{
                      backgroundColor: 'var(--input-bg)',
                      color: 'var(--input-text)',
                      borderColor: 'var(--input-border)',
                      borderWidth: '1px',
                      borderStyle: 'solid'
                    }}
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>Vendor / Payee Name</label>
                  <input 
                    type="text" 
                    placeholder="e.g. Global Water Logistics"
                    value={vendor}
                    onChange={e => setVendor(e.target.value)}
                    className="w-full rounded-lg px-3 py-2 text-xs focus:outline-none"
                    style={{
                      backgroundColor: 'var(--input-bg)',
                      color: 'var(--input-text)',
                      borderColor: 'var(--input-border)',
                      borderWidth: '1px',
                      borderStyle: 'solid'
                    }}
                  />
                </div>
              </div>

              {/* Amount & Date */}
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>Requested Amount (£) *</label>
                  <input 
                    type="number" 
                    step="0.01"
                    required
                    placeholder="0.00"
                    value={amount}
                    onChange={e => setAmount(e.target.value)}
                    className="w-full rounded-lg px-3 py-2 text-xs text-cyan-400 font-bold focus:outline-none"
                    style={{
                      backgroundColor: 'var(--input-bg)',
                      borderColor: 'var(--input-border)',
                      borderWidth: '1px',
                      borderStyle: 'solid'
                    }}
                  />
                </div>
                <div>
                  <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>Payment Date</label>
                  <input 
                    type="date" 
                    required
                    value={paymentDate}
                    onChange={e => setPaymentDate(e.target.value)}
                    className="w-full rounded-lg px-3 py-2 text-xs focus:outline-none"
                    style={{
                      backgroundColor: 'var(--input-bg)',
                      color: 'var(--input-text)',
                      borderColor: 'var(--input-border)',
                      borderWidth: '1px',
                      borderStyle: 'solid'
                    }}
                  />
                </div>
              </div>

              {/* Notes */}
              <div>
                <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>Additional Notes / Memo</label>
                <textarea 
                  rows="2"
                  placeholder="Provide any additional context or reference invoice number..."
                  value={notes}
                  onChange={e => setNotes(e.target.value)}
                  className="w-full rounded-lg px-3 py-2 text-xs focus:outline-none"
                  style={{
                    backgroundColor: 'var(--input-bg)',
                    color: 'var(--input-text)',
                    borderColor: 'var(--input-border)',
                    borderWidth: '1px',
                    borderStyle: 'solid'
                  }}
                ></textarea>
              </div>

              {/* Form Buttons */}
              <div className="flex items-center justify-end gap-3 mt-2">
                <button
                  type="button"
                  onClick={() => setShowSubmitModal(false)}
                  className="btn-secondary text-xs"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={submitting}
                  className="btn-primary text-xs flex items-center gap-1.5"
                >
                  <PlusCircle className="w-4 h-4" /> {submitting ? 'Submitting Claim...' : 'Submit for Approval'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
