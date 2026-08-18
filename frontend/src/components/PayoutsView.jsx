import React, { useEffect, useState } from 'react';
import { 
  CreditCard, 
  DollarSign, 
  Layers, 
  CheckCircle, 
  Search, 
  RefreshCw, 
  TrendingUp, 
  Building, 
  Trash2,
  AlertCircle,
  X,
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Folder,
  FolderOpen,
  Maximize2,
  Minimize2,
  Tag
} from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function PayoutsView({ user, accentColor }) {
  const [currency, setCurrency] = useState('ALL'); // 'ALL', 'GBP', or 'USD'
  const [summary, setSummary] = useState({
    total_gross: 0,
    total_fees: 0,
    total_reserves: 0,
    net_payout: 0,
    total_transactions: 0,
    settled_donations_count: 0,
    disbursement_summary: {},
    ledger_breakdown: []
  });
  
  const [batchesData, setBatchesData] = useState({ total_batches: 0, page: 1, page_size: 25, total_pages: 1, batches: [] });
  const [campaignData, setCampaignData] = useState([]);
  const [codeGroups, setCodeGroups] = useState([]);
  const [expandedCodes, setExpandedCodes] = useState({});
  const [breakdownViewMode, setBreakdownViewMode] = useState('code_groups'); // 'code_groups' or 'flat'
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('disbursement'); // 'disbursement', 'batches', 'campaigns', 'ledger'
  
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Code Breakdown Pagination State
  const [codePage, setCodePage] = useState(1);
  const [codePageSize, setCodePageSize] = useState(25);

  // Flat Campaign Breakdown Pagination State
  const [campPage, setCampPage] = useState(1);
  const [campPageSize, setCampPageSize] = useState(25);

  // Purge Payout Modal State
  const [showPurgeModal, setShowPurgeModal] = useState(false);
  const [purgeConfirm, setPurgeConfirm] = useState(false);
  const [purging, setPurging] = useState(false);
  const [purgeMsg, setPurgeMsg] = useState('');

  const isSuperAdmin = user?.role === 'super_admin';
  const currSymbol = currency === 'USD' ? '$' : '£';

  const fetchPayoutData = () => {
    setLoading(true);
    const searchParam = search ? `&search=${encodeURIComponent(search)}` : '';
    
    Promise.all([
      fetch(`${API_BASE_URL}/api/payouts/summary?currency=${currency}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/payouts/batches?currency=${currency}&page=${currentPage}&page_size=${pageSize}${searchParam}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/payouts/campaign-breakdown?currency=${currency}${searchParam}`).then(r => r.json())
    ])
      .then(([sumRes, batchRes, campRes]) => {
        setSummary(sumRes);
        setBatchesData(batchRes);
        setCampaignData(campRes.campaigns || []);
        setCodeGroups(campRes.code_groups || []);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error loading payout reconciliation data:', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchPayoutData();
  }, [currency, currentPage, pageSize, search]);

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= batchesData.total_pages) {
      setCurrentPage(newPage);
    }
  };

  const toggleCodeExpand = (code) => {
    setExpandedCodes(prev => ({
      ...prev,
      [code]: !prev[code]
    }));
  };

  const expandAllCodes = () => {
    const allExp = {};
    codeGroups.forEach(cg => { allExp[cg.code] = true; });
    setExpandedCodes(allExp);
  };

  const collapseAllCodes = () => {
    setExpandedCodes({});
  };

  const handlePurgePayouts = () => {
    if (!isSuperAdmin) return;
    if (!purgeConfirm) {
      setPurgeMsg('❌ Please check the confirmation box before purging payout data.');
      return;
    }

    setPurging(true);
    setPurgeMsg('');

    fetch(`${API_BASE_URL}/api/admin/purge-payouts`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role,
        confirm: true
      })
    })
      .then(r => r.json())
      .then(res => {
        setPurging(false);
        if (res?.status === 'success') {
          setPurgeMsg(`✅ ${res.message}`);
          setTimeout(() => {
            setShowPurgeModal(false);
            setPurgeConfirm(false);
            setPurgeMsg('');
            fetchPayoutData();
          }, 1500);
        } else {
          setPurgeMsg(`❌ ${res?.detail || 'Failed to purge payout data.'}`);
        }
      })
      .catch(err => {
        setPurging(false);
        setPurgeMsg(`❌ Error purging payout data: ${err.message}`);
      });
  };

  // Code Breakdown Pagination Calculations
  const effectiveCodePageSize = codePageSize === 'All' ? Math.max(1, codeGroups.length) : Number(codePageSize);
  const totalCodePages = Math.max(1, Math.ceil(codeGroups.length / effectiveCodePageSize));
  const safeCodePage = Math.min(Math.max(1, codePage), totalCodePages);

  const paginatedCodes = codePageSize === 'All' 
    ? codeGroups 
    : codeGroups.slice((safeCodePage - 1) * effectiveCodePageSize, safeCodePage * effectiveCodePageSize);

  // Campaign Breakdown Pagination Calculations
  const effectiveCampPageSize = campPageSize === 'All' ? Math.max(1, campaignData.length) : Number(campPageSize);
  const totalCampPages = Math.max(1, Math.ceil(campaignData.length / effectiveCampPageSize));
  const safeCampPage = Math.min(Math.max(1, campPage), totalCampPages);

  const paginatedCampaigns = campPageSize === 'All' 
    ? campaignData 
    : campaignData.slice((safeCampPage - 1) * effectiveCampPageSize, safeCampPage * effectiveCampPageSize);

  const disb = summary.disbursement_summary || {};

  return (
    <div className="flex flex-col gap-6 animate-fade-in pb-16">
      {/* Header & Control Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-gradient-to-tr from-emerald-600 to-teal-500 rounded-2xl shadow-lg shadow-teal-500/20 text-white">
            <CreditCard className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
              Payout Reconciliation Center
              <span className="text-xs px-2.5 py-0.5 rounded-full font-bold uppercase bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-400">
                LaunchGood Payouts
              </span>
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 font-medium">
              Gross settlement tracking, processing fee audits, reserve withholdings, and bank payout batch reconciliation
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Currency Switcher Toggle */}
          <div className="flex items-center p-1 bg-slate-100 dark:bg-slate-800 rounded-2xl border border-slate-200 dark:border-white/10 shadow-inner">
            <button
              onClick={() => {
                setCurrency('ALL');
                setCurrentPage(1);
                setCodePage(1);
                setCampPage(1);
              }}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                currency === 'ALL'
                  ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-emerald-500/20'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
              }`}
            >
              <span>🌐 Combined</span>
            </button>
            <button
              onClick={() => {
                setCurrency('GBP');
                setCurrentPage(1);
                setCodePage(1);
                setCampPage(1);
              }}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                currency === 'GBP'
                  ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-emerald-500/20'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
              }`}
            >
              <span>🇬🇧 GBP (£) Primary</span>
            </button>
            <button
              onClick={() => {
                setCurrency('USD');
                setCurrentPage(1);
                setCodePage(1);
                setCampPage(1);
              }}
              className={`px-3.5 py-1.5 rounded-xl text-xs font-bold transition-all flex items-center gap-1.5 cursor-pointer ${
                currency === 'USD'
                  ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-emerald-500/20'
                  : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
              }`}
            >
              <span>🇺🇸 USD ($) Foreign FX</span>
            </button>
          </div>

          {/* Super Admin Purge Payout Button */}
          {isSuperAdmin && (
            <button
              onClick={() => setShowPurgeModal(true)}
              className="px-3.5 py-2 text-xs font-bold text-rose-700 dark:text-rose-300 bg-rose-50 dark:bg-rose-950/40 hover:bg-rose-100 dark:hover:bg-rose-900/60 rounded-xl border border-rose-500/30 transition-all flex items-center gap-1.5 cursor-pointer shadow-sm"
              title="Delete all LaunchGood payout settlement data from the system"
            >
              <Trash2 className="w-3.5 h-3.5 text-rose-500" />
              <span>Purge Payout Data</span>
            </button>
          )}

          <button 
            onClick={fetchPayoutData}
            disabled={loading}
            className="px-4 py-2 text-xs font-bold text-slate-700 dark:text-slate-200 bg-slate-100 dark:bg-slate-800/80 hover:bg-slate-200 dark:hover:bg-slate-700/80 rounded-xl border border-slate-300 dark:border-white/10 transition-all flex items-center gap-2 cursor-pointer shadow-sm disabled:opacity-50"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-emerald-500' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Top 4 Financial Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Gross Settlement */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {currency === 'ALL' ? 'Combined' : currency} Gross Settlement
            </span>
            <div className="p-2 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-xl">
              <DollarSign className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-black text-slate-900 dark:text-white">
            {currSymbol}{summary.total_gross.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
            From {summary.settled_donations_count.toLocaleString()} settled {currency === 'ALL' ? 'all' : currency} transactions
          </div>
        </div>

        {/* Processing Fees Paid */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Processing Fees Paid
            </span>
            <div className="p-2 bg-rose-500/10 text-rose-600 dark:text-rose-400 rounded-xl">
              <CreditCard className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-black text-rose-600 dark:text-rose-400">
            {currSymbol}{summary.total_fees.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
            {summary.total_gross > 0 ? ((summary.total_fees / summary.total_gross) * 100).toFixed(2) : '0.00'}% platform & CC fee ratio
          </div>
        </div>

        {/* Reserve Withheld */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {currency === 'USD' ? 'FX Outflow to GBP' : 'Reserve Adjustment'}
            </span>
            <div className="p-2 bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded-xl">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-black text-amber-600 dark:text-amber-400">
            {currency === 'USD' 
              ? `${currSymbol}${Math.abs(Number(disb.foreign_exchange || 0)).toLocaleString('en-GB', { minimumFractionDigits: 2 })}`
              : `${currSymbol}${summary.total_reserves.toLocaleString('en-GB', { minimumFractionDigits: 2 })}`
            }
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
            {currency === 'USD' ? 'Converted into GBP charity account' : 'Platform rolling reserves & hold funds'}
          </div>
        </div>

        {/* Net Bank Transfers Received */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              {currency === 'USD' ? 'Net USD Remaining' : 'Net Bank Transfers'}
            </span>
            <div className="p-2 bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 rounded-xl">
              <Building className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-black text-cyan-600 dark:text-cyan-400">
            {currSymbol}{summary.net_payout.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1">
            <CheckCircle className="w-3.5 h-3.5 text-cyan-500" />
            <span>{currency === 'USD' ? '100% converted to GBP balance' : 'Net payout transferred to bank'}</span>
          </div>
        </div>
      </div>

      {/* Sub-Tab Navigation & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm">
        {/* Tab Buttons */}
        <div className="flex items-center gap-2">
          <button 
            onClick={() => setActiveTab('disbursement')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'disbursement'
                ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-teal-500/20'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Finance Disbursement Summary ({currency === 'ALL' ? 'Combined' : currency})</span>
          </button>

          <button 
            onClick={() => setActiveTab('batches')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'batches'
                ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-teal-500/20'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            <Building className="w-3.5 h-3.5" />
            <span>Transfer Batches ({batchesData.total_batches})</span>
          </button>
          
          <button 
            onClick={() => setActiveTab('campaigns')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'campaigns'
                ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-teal-500/20'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            <FolderOpen className="w-3.5 h-3.5" />
            <span>Code & Campaign Breakdown ({codeGroups.length} Codes)</span>
          </button>

          <button 
            onClick={() => setActiveTab('ledger')}
            className={`px-4 py-2 rounded-xl text-xs font-bold transition-all flex items-center gap-2 cursor-pointer ${
              activeTab === 'ledger'
                ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-md shadow-teal-500/20'
                : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700'
            }`}
          >
            <CreditCard className="w-3.5 h-3.5" />
            <span>Accounting Ledger Audit ({summary.ledger_breakdown?.length || 0})</span>
          </button>
        </div>

        {/* Live Search */}
        <div className="relative min-w-[260px]">
          <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
          <input 
            type="text"
            placeholder="Search Transfer ID or Campaign..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setCurrentPage(1);
              setCampPage(1);
            }}
            className="w-full pl-9 pr-4 py-2 text-xs rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-800/60 text-slate-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-emerald-500/50"
          />
        </div>
      </div>

      {/* Main Content Area */}
      {loading ? (
        <div className="p-12 text-center text-xs font-bold text-slate-500 dark:text-slate-400 animate-pulse flex flex-col items-center gap-3">
          <RefreshCw className="w-6 h-6 animate-spin text-emerald-500" />
          <span>Loading Payout Reconciliation Data...</span>
        </div>
      ) : activeTab === 'disbursement' ? (
        /* Tab 0: Finance Disbursement Summary Table (Matching Finance Team Model) */
        <div className="flex flex-col gap-6">
          <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm overflow-hidden">
            <div className="p-4 border-b border-slate-200 dark:border-white/10 flex items-center justify-between">
              <div className="flex items-center gap-2">
                <div className="p-1.5 rounded-lg bg-emerald-500/10 text-emerald-600 dark:text-emerald-400">
                  <TrendingUp className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-black text-slate-900 dark:text-white">
                    Disbursement Summary ({currency})
                  </h3>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
                    Verified finance team ledger reconciliation model for {currency} settlement
                  </p>
                </div>
              </div>
              <span className="px-3 py-1 rounded-xl text-xs font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-400">
                100% Reconciled
              </span>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-100/70 dark:bg-slate-800/60 text-[11px] uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-white/10">
                    <th className="p-3.5 pl-6">Disbursement Summary Line Item</th>
                    <th className="p-3.5 text-center"># Transactions</th>
                    <th className="p-3.5 pr-6 text-right">Value ({currency})</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-white/5 text-xs text-slate-800 dark:text-slate-200 font-medium">
                  {/* Gross Donations / Contributions */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 font-bold text-slate-900 dark:text-white">
                      Gross Donations/Contributions
                    </td>
                    <td className="p-3.5 text-center font-mono font-bold text-slate-700 dark:text-slate-300">
                      {Number(disb.gross_donations_count || 0).toLocaleString()}
                    </td>
                    <td className="p-3.5 pr-6 text-right font-mono font-bold text-slate-900 dark:text-white">
                      {currSymbol}{Number(disb.gross_donations || 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>

                  {/* Refunds */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 text-slate-700 dark:text-slate-300">
                      Refunds
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-600 dark:text-slate-400">
                      {Number(disb.refunds_count || 0).toLocaleString()}
                    </td>
                    <td className="p-3.5 pr-6 text-right font-mono font-semibold text-rose-600 dark:text-rose-400">
                      {disb.refunds ? `${currSymbol}${Number(disb.refunds).toLocaleString('en-GB', { minimumFractionDigits: 2 })}` : `${currSymbol}0.00`}
                    </td>
                  </tr>

                  {/* Refunds Failed */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 text-slate-500 dark:text-slate-400">
                      Refunds Failed
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-500 dark:text-slate-400">
                      0
                    </td>
                    <td className="p-3.5 pr-6 text-right font-mono text-slate-500 dark:text-slate-400">
                      {currSymbol}0.00
                    </td>
                  </tr>

                  {/* Chargebacks */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 text-slate-500 dark:text-slate-400">
                      Chargebacks
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-500 dark:text-slate-400">
                      0
                    </td>
                    <td className="p-3.5 pr-6 text-right font-mono text-slate-500 dark:text-slate-400">
                      {currSymbol}0.00
                    </td>
                  </tr>

                  {/* Chargebacks Reversed */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 text-slate-500 dark:text-slate-400">
                      Chargebacks Reversed
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-500 dark:text-slate-400">
                      0
                    </td>
                    <td className="p-3.5 pr-6 text-right font-mono text-slate-500 dark:text-slate-400">
                      {currSymbol}0.00
                    </td>
                  </tr>

                  {/* Net Sales Highlight Row */}
                  <tr className="bg-slate-100/90 dark:bg-slate-800/80 font-black border-y-2 border-slate-300 dark:border-white/10">
                    <td className="p-3.5 pl-6 text-slate-900 dark:text-white uppercase tracking-wider text-[11px]">
                      Net Sales
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-900 dark:text-white">
                      {Number(disb.net_sales_count || 0).toLocaleString()}
                    </td>
                    <td className="p-3.5 pr-6 text-right font-mono text-slate-900 dark:text-white text-sm">
                      {currSymbol}{Number(disb.net_sales || 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>

                  {/* Processing Fees */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 text-slate-700 dark:text-slate-300">
                      Processing Fees
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-400">—</td>
                    <td className="p-3.5 pr-6 text-right font-mono font-bold text-rose-600 dark:text-rose-400">
                      {currSymbol}{Number(disb.processing_fees || 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>

                  {/* Non Processing Fees */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 text-slate-500 dark:text-slate-400">
                      Non Processing Fees
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-400">—</td>
                    <td className="p-3.5 pr-6 text-right font-mono text-slate-500 dark:text-slate-400">
                      {currSymbol}0.00
                    </td>
                  </tr>

                  {/* Manual Adjustments Total */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 text-slate-700 dark:text-slate-300">
                      Manual Adjustments Total (Zakat donation fees)
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-600 dark:text-slate-400">
                      {Number(disb.manual_adjustments_count || 0)}
                    </td>
                    <td className="p-3.5 pr-6 text-right font-mono font-bold text-rose-600 dark:text-rose-400">
                      {currSymbol}{Number(disb.manual_adjustments || 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>

                  {/* Reserve Adjustment */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 text-slate-700 dark:text-slate-300">
                      Reserve Adjustment
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-600 dark:text-slate-400">
                      {Number(disb.reserve_adjustment_count || 0)}
                    </td>
                    <td className="p-3.5 pr-6 text-right font-mono font-bold text-amber-600 dark:text-amber-400">
                      {currSymbol}{Number(disb.reserve_adjustment || 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>

                  {/* Foreign Exchange */}
                  <tr className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="p-3.5 pl-6 text-slate-700 dark:text-slate-300">
                      Foreign Exchange
                    </td>
                    <td className="p-3.5 text-center font-mono text-slate-600 dark:text-slate-400">
                      {Number(disb.foreign_exchange_count || 0)}
                    </td>
                    <td className={`p-3.5 pr-6 text-right font-mono font-bold ${Number(disb.foreign_exchange || 0) < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-cyan-600 dark:text-cyan-400'}`}>
                      {currSymbol}{Number(disb.foreign_exchange || 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>

                  {/* Total Disbursement Final Highlight */}
                  <tr className="bg-emerald-50/80 dark:bg-emerald-950/40 border-t-2 border-emerald-500/40">
                    <td className="p-4 pl-6 text-emerald-900 dark:text-emerald-200 font-black text-sm uppercase tracking-wider">
                      Total Disbursement
                    </td>
                    <td className="p-4 text-center font-mono font-bold text-emerald-800 dark:text-emerald-300">
                      {Number(disb.total_disbursement_count || 0)} batches
                    </td>
                    <td className="p-4 pr-6 text-right font-mono font-black text-emerald-600 dark:text-emerald-400 text-base">
                      {currSymbol}{Number(disb.total_disbursement || 0).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>
      ) : activeTab === 'batches' ? (
        /* Tab 1: Payout Transfer Batches Table */
        <div className="flex flex-col gap-4">
          <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-100/70 dark:bg-slate-800/60 text-[11px] uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-white/10">
                    <th className="p-3.5 pl-5">Transfer ID</th>
                    <th className="p-3.5">Date</th>
                    <th className="p-3.5">Campaigns</th>
                    <th className="p-3.5">Donations</th>
                    <th className="p-3.5">Gross Amount</th>
                    <th className="p-3.5">Processing Fees</th>
                    <th className="p-3.5 pr-5">Net Payout</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-white/5 text-xs text-slate-800 dark:text-slate-200 font-medium">
                  {batchesData.batches.length === 0 ? (
                    <tr>
                      <td colSpan="7" className="p-8 text-center text-slate-500 dark:text-slate-400 font-semibold">
                        No payout transfer batches found.
                      </td>
                    </tr>
                  ) : (
                    batchesData.batches.map((batch, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                        <td className="p-3.5 pl-5 font-mono font-bold text-emerald-600 dark:text-emerald-400">
                          #{batch.transfer_id}
                        </td>
                        <td className="p-3.5 font-medium text-slate-600 dark:text-slate-400">
                          {batch.created_date}
                        </td>
                        <td className="p-3.5">
                          <span className="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300">
                            {batch.campaigns_count} campaigns
                          </span>
                        </td>
                        <td className="p-3.5">
                          <span className="px-2.5 py-1 rounded-lg text-[11px] font-bold bg-teal-50 text-teal-700 dark:bg-teal-950/40 dark:text-teal-300 border border-teal-500/20">
                            {batch.donations_count} transactions
                          </span>
                        </td>
                        <td className="p-3.5 font-bold text-slate-900 dark:text-white">
                          £{Number(batch.gross_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-3.5 font-semibold text-rose-600 dark:text-rose-400">
                          £{Number(batch.processing_fees).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-3.5 pr-5 font-extrabold text-emerald-600 dark:text-emerald-400">
                          £{Number(batch.transfer_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                        </td>
                      </tr>
                    ))
                  )}
                </tbody>
              </table>
            </div>
          </div>

          {/* Batches Pagination Footer */}
          {batchesData.total_pages > 1 && (
            <div className="flex items-center justify-between gap-4 p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm text-xs font-semibold">
              <div className="text-slate-500 dark:text-slate-400">
                Showing Page <span className="text-slate-900 dark:text-white font-bold">{batchesData.page}</span> of <span className="text-slate-900 dark:text-white font-bold">{batchesData.total_pages}</span> ({batchesData.total_batches} total batches)
              </div>
              <div className="flex items-center gap-2">
                <button 
                  onClick={() => handlePageChange(batchesData.page - 1)}
                  disabled={batchesData.page <= 1}
                  className="p-2 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 transition-all cursor-pointer"
                >
                  <ChevronLeft className="w-4 h-4 text-slate-700 dark:text-slate-300" />
                </button>
                <button 
                  onClick={() => handlePageChange(batchesData.page + 1)}
                  disabled={batchesData.page >= batchesData.total_pages}
                  className="p-2 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 transition-all cursor-pointer"
                >
                  <ChevronRight className="w-4 h-4 text-slate-700 dark:text-slate-300" />
                </button>
              </div>
            </div>
          )}
        </div>
      ) : activeTab === 'campaigns' ? (
        /* Tab 2: Code & Campaign Fee Breakdown (Hierarchical Drilldown) */
        <div className="flex flex-col gap-4">
          {/* Sub-Header Toolbar: View Mode Switcher & Expand/Collapse */}
          <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm">
            <div className="flex items-center gap-3">
              <div className="flex items-center p-1 bg-slate-100 dark:bg-slate-800 rounded-xl border border-slate-200 dark:border-white/10 shadow-inner text-xs font-bold">
                <button
                  onClick={() => setBreakdownViewMode('code_groups')}
                  className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 cursor-pointer ${
                    breakdownViewMode === 'code_groups'
                      ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-sm shadow-emerald-500/20'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  <FolderOpen className="w-3.5 h-3.5" />
                  <span>Group by Classification Code ({codeGroups.length})</span>
                </button>
                <button
                  onClick={() => setBreakdownViewMode('flat')}
                  className={`px-3.5 py-1.5 rounded-lg transition-all flex items-center gap-1.5 cursor-pointer ${
                    breakdownViewMode === 'flat'
                      ? 'bg-gradient-to-r from-emerald-600 to-teal-600 text-white shadow-sm shadow-emerald-500/20'
                      : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                  }`}
                >
                  <Layers className="w-3.5 h-3.5" />
                  <span>Flat Campaigns List ({campaignData.length})</span>
                </button>
              </div>
            </div>

            {breakdownViewMode === 'code_groups' && codeGroups.length > 0 && (
              <div className="flex items-center gap-2 text-xs font-semibold">
                <button
                  onClick={expandAllCodes}
                  className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 text-slate-700 dark:text-slate-300 transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <Maximize2 className="w-3.5 h-3.5 text-emerald-500" />
                  <span>Expand All Codes</span>
                </button>
                <button
                  onClick={collapseAllCodes}
                  className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/10 bg-slate-50 dark:bg-slate-800/60 hover:bg-slate-100 dark:hover:bg-slate-700/60 text-slate-700 dark:text-slate-300 transition-all flex items-center gap-1.5 cursor-pointer"
                >
                  <Minimize2 className="w-3.5 h-3.5 text-slate-400" />
                  <span>Collapse All</span>
                </button>
              </div>
            )}
          </div>

          {breakdownViewMode === 'code_groups' ? (
            /* Mode A: Hierarchical Code Groups Table with Expandable Sub-Campaigns */
            <div className="flex flex-col gap-4">
              <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-slate-100/70 dark:bg-slate-800/60 text-[11px] uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-white/10">
                        <th className="p-3.5 pl-6">Classification Code & Campaigns</th>
                        <th className="p-3.5">Category & Details</th>
                        <th className="p-3.5">Gross Raised</th>
                        <th className="p-3.5">CC & Platform Fees</th>
                        <th className="p-3.5">Fee Ratio</th>
                        <th className="p-3.5 pr-6">Net Settlement</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-white/5 text-xs text-slate-800 dark:text-slate-200 font-medium">
                      {paginatedCodes.length === 0 ? (
                        <tr>
                          <td colSpan="6" className="p-8 text-center text-slate-500 dark:text-slate-400 font-semibold">
                            No classification code revenue breakdown data found.
                          </td>
                        </tr>
                      ) : (
                        paginatedCodes.map((cg, idx) => {
                          const isExp = !!expandedCodes[cg.code];
                          return (
                            <React.Fragment key={idx}>
                              {/* Parent Code Group Row */}
                              <tr 
                                onClick={() => toggleCodeExpand(cg.code)}
                                className={`transition-colors cursor-pointer select-none ${
                                  isExp 
                                    ? 'bg-emerald-50/50 dark:bg-emerald-950/20 hover:bg-emerald-50/80 dark:hover:bg-emerald-950/30' 
                                    : 'hover:bg-slate-50/80 dark:hover:bg-slate-800/50'
                                }`}
                              >
                                <td className="p-3.5 pl-6">
                                  <div className="flex items-center gap-3">
                                    <div className={`p-1 rounded-lg transition-transform duration-200 ${isExp ? 'rotate-90 text-emerald-600 dark:text-emerald-400 bg-emerald-100 dark:bg-emerald-500/20' : 'text-slate-400 hover:text-slate-600'}`}>
                                      <ChevronRight className="w-4 h-4" />
                                    </div>
                                    <div className="flex items-center gap-2">
                                      <span className="px-2.5 py-1 rounded-lg text-xs font-mono font-black uppercase bg-teal-50 text-teal-800 dark:bg-teal-950/50 dark:text-teal-300 border border-teal-500/30 shadow-xs">
                                        {cg.code}
                                      </span>
                                      <span className="px-2 py-0.5 rounded-md text-[11px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 border border-slate-200 dark:border-white/10">
                                        {cg.campaigns_count} {cg.campaigns_count === 1 ? 'campaign' : 'campaigns'}
                                      </span>
                                    </div>
                                  </div>
                                </td>

                                <td className="p-3.5">
                                  <div className="flex flex-col gap-0.5 text-[11px]">
                                    <div className="flex items-center gap-2">
                                      <span className="font-bold text-slate-800 dark:text-slate-200">{cg.heading}</span>
                                      {cg.zakat !== 'Unassigned' && (
                                        <span className="px-1.5 py-0.2 rounded text-[10px] font-bold bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300">
                                          {cg.zakat}
                                        </span>
                                      )}
                                    </div>
                                    <span className="text-slate-500 dark:text-slate-400 text-[10px]">
                                      {cg.sub_heading !== 'Unassigned' ? cg.sub_heading : ''} {cg.country !== 'Unassigned' ? `• ${cg.country}` : ''}
                                    </span>
                                  </div>
                                </td>

                                <td className="p-3.5 font-black text-slate-900 dark:text-white font-mono">
                                  {currSymbol}{Number(cg.gross_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                                </td>

                                <td className="p-3.5 font-bold text-rose-600 dark:text-rose-400 font-mono">
                                  {currSymbol}{Number(cg.processing_fees).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                                </td>

                                <td className="p-3.5">
                                  <div className="flex items-center gap-2 min-w-[100px]">
                                    <div className="w-16 bg-slate-200 dark:bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                      <div 
                                        className="bg-rose-500 h-full rounded-full" 
                                        style={{ width: `${Math.min(100, cg.fee_percentage * 5)}%` }}
                                      ></div>
                                    </div>
                                    <span className="text-[11px] font-bold text-rose-600 dark:text-rose-400 font-mono">{cg.fee_percentage}%</span>
                                  </div>
                                </td>

                                <td className="p-3.5 pr-6 font-black text-emerald-600 dark:text-emerald-400 font-mono text-sm">
                                  {currSymbol}{Number(cg.transfer_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                                </td>
                              </tr>

                              {/* Nested Sub-Campaigns Breakdown Card */}
                              {isExp && (
                                <tr>
                                  <td colSpan="6" className="p-0 bg-slate-100/50 dark:bg-slate-950/40 border-y border-slate-200 dark:border-white/10">
                                    <div className="p-4 pl-12 pr-6 flex flex-col gap-3">
                                      <div className="flex items-center justify-between">
                                        <div className="flex items-center gap-2 text-xs font-bold text-slate-700 dark:text-slate-300">
                                          <FolderOpen className="w-4 h-4 text-emerald-500" />
                                          <span>Campaign Breakdown for Code <span className="font-mono text-emerald-600 dark:text-emerald-400 font-black">{cg.code}</span>:</span>
                                        </div>
                                        <span className="text-[11px] font-medium text-slate-500 dark:text-slate-400">
                                          {cg.campaigns.length} contributing {cg.campaigns.length === 1 ? 'campaign' : 'campaigns'}
                                        </span>
                                      </div>

                                      <div className="rounded-xl border border-slate-200/80 dark:border-white/10 bg-white/90 dark:bg-slate-900/90 shadow-sm overflow-hidden">
                                        <table className="w-full text-left border-collapse">
                                          <thead>
                                            <tr className="bg-slate-50/80 dark:bg-slate-800/80 text-[10px] uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-white/10">
                                              <th className="p-2.5 pl-4">Contributing Campaign Name</th>
                                              <th className="p-2.5 text-center">Donations</th>
                                              <th className="p-2.5">Gross Raised</th>
                                              <th className="p-2.5">CC Fees</th>
                                              <th className="p-2.5">Fee Ratio</th>
                                              <th className="p-2.5 pr-4">Net Settlement</th>
                                            </tr>
                                          </thead>
                                          <tbody className="divide-y divide-slate-100 dark:divide-white/5 text-xs text-slate-700 dark:text-slate-300">
                                            {cg.campaigns.map((sc, sIdx) => (
                                              <tr key={sIdx} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                                                <td className="p-2.5 pl-4 font-bold text-slate-900 dark:text-white max-w-[340px] truncate" title={sc.campaign_name}>
                                                  {sc.campaign_name}
                                                </td>
                                                <td className="p-2.5 text-center font-mono text-[11px]">
                                                  <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400">
                                                    {Number(sc.donations_count || 0).toLocaleString()}
                                                  </span>
                                                </td>
                                                <td className="p-2.5 font-bold font-mono text-slate-900 dark:text-white">
                                                  {currSymbol}{Number(sc.gross_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                                                </td>
                                                <td className="p-2.5 font-semibold font-mono text-rose-600 dark:text-rose-400">
                                                  {currSymbol}{Number(sc.processing_fees).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                                                </td>
                                                <td className="p-2.5 font-mono text-[11px] text-rose-600 dark:text-rose-400 font-bold">
                                                  {sc.fee_percentage}%
                                                </td>
                                                <td className="p-2.5 pr-4 font-black font-mono text-emerald-600 dark:text-emerald-400">
                                                  {currSymbol}{Number(sc.transfer_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                                                </td>
                                              </tr>
                                            ))}
                                          </tbody>
                                        </table>
                                      </div>
                                    </div>
                                  </td>
                                </tr>
                              )}
                            </React.Fragment>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Code Groups Pagination Footer */}
              <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm text-xs font-semibold">
                <div className="flex items-center gap-3">
                  <span className="text-slate-500 dark:text-slate-400">Page Size:</span>
                  <select 
                    value={codePageSize}
                    onChange={(e) => {
                      setCodePageSize(e.target.value);
                      setCodePage(1);
                    }}
                    className="bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-white/10 rounded-xl px-3 py-1.5 text-xs text-slate-800 dark:text-white focus:outline-none cursor-pointer"
                  >
                    <option value={25}>25 codes</option>
                    <option value={50}>50 codes</option>
                    <option value={100}>100 codes</option>
                    <option value="All">All ({codeGroups.length})</option>
                  </select>
                  <span className="text-slate-500 dark:text-slate-400 border-l border-slate-200 dark:border-white/10 pl-3">
                    Showing Page <span className="text-slate-900 dark:text-white font-bold">{safeCodePage}</span> of <span className="text-slate-900 dark:text-white font-bold">{totalCodePages}</span> ({codeGroups.length} total codes)
                  </span>
                </div>

                {codePageSize !== 'All' && totalCodePages > 1 && (
                  <div className="flex items-center gap-2">
                    <button 
                      onClick={() => setCodePage(p => Math.max(1, p - 1))}
                      disabled={safeCodePage <= 1}
                      className="p-2 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 transition-all cursor-pointer"
                    >
                      <ChevronLeft className="w-4 h-4 text-slate-700 dark:text-slate-300" />
                    </button>
                    <button 
                      onClick={() => setCodePage(p => Math.min(totalCodePages, p + 1))}
                      disabled={safeCodePage >= totalCodePages}
                      className="p-2 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 transition-all cursor-pointer"
                    >
                      <ChevronRight className="w-4 h-4 text-slate-700 dark:text-slate-300" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          ) : (
            /* Mode B: Flat Individual Campaigns List */
            <div className="flex flex-col gap-4">
              <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm overflow-hidden">
                <div className="overflow-x-auto">
                  <table className="w-full text-left border-collapse">
                    <thead>
                      <tr className="bg-slate-100/70 dark:bg-slate-800/60 text-[11px] uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-white/10">
                        <th className="p-3.5 pl-5">Campaign / Project Name</th>
                        <th className="p-3.5">Classification Code</th>
                        <th className="p-3.5">Gross Raised</th>
                        <th className="p-3.5">CC & Platform Fees</th>
                        <th className="p-3.5">Fee Ratio</th>
                        <th className="p-3.5 pr-5">Net Settlement</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200 dark:divide-white/5 text-xs text-slate-800 dark:text-slate-200 font-medium">
                      {paginatedCampaigns.length === 0 ? (
                        <tr>
                          <td colSpan="6" className="p-8 text-center text-slate-500 dark:text-slate-400 font-semibold">
                            No campaign settlement breakdown data found.
                          </td>
                        </tr>
                      ) : (
                        paginatedCampaigns.map((camp, idx) => (
                          <tr key={idx} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                            <td className="p-3.5 pl-5 font-bold text-slate-900 dark:text-white max-w-[280px] truncate" title={camp.campaign_name}>
                              {camp.campaign_name}
                            </td>
                            <td className="p-3.5">
                              <div className="flex flex-col gap-0.5 text-[11px]">
                                <span className="font-bold text-slate-700 dark:text-slate-300">{camp.heading}</span>
                                <span className="text-slate-500 dark:text-slate-400 text-[10px] font-mono font-bold">{camp.code !== 'Unassigned' ? camp.code : camp.sub_heading}</span>
                              </div>
                            </td>
                            <td className="p-3.5 font-bold text-slate-900 dark:text-white font-mono">
                              {currSymbol}{Number(camp.gross_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                            </td>
                            <td className="p-3.5 font-semibold text-rose-600 dark:text-rose-400 font-mono">
                              {currSymbol}{Number(camp.processing_fees).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                            </td>
                            <td className="p-3.5">
                              <div className="flex items-center gap-2 min-w-[100px]">
                                <div className="w-16 bg-slate-200 dark:bg-slate-800 rounded-full h-1.5 overflow-hidden">
                                  <div 
                                    className="bg-rose-500 h-full rounded-full" 
                                    style={{ width: `${Math.min(100, camp.fee_percentage * 5)}%` }}
                                  ></div>
                                </div>
                                <span className="text-[11px] font-bold text-rose-600 dark:text-rose-400 font-mono">{camp.fee_percentage}%</span>
                              </div>
                            </td>
                            <td className="p-3.5 pr-5 font-black text-emerald-600 dark:text-emerald-400 font-mono">
                              {currSymbol}{Number(camp.transfer_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                            </td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Campaign Breakdown Pagination Footer */}
              <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm text-xs font-semibold">
                <div className="flex items-center gap-3">
                  <span className="text-slate-500 dark:text-slate-400">Page Size:</span>
                  <select 
                    value={campPageSize}
                    onChange={(e) => {
                      setCampPageSize(e.target.value);
                      setCampPage(1);
                    }}
                    className="bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-white/10 rounded-xl px-3 py-1.5 text-xs text-slate-800 dark:text-white focus:outline-none cursor-pointer"
                  >
                    <option value={25}>25 campaigns</option>
                    <option value={50}>50 campaigns</option>
                    <option value={100}>100 campaigns</option>
                    <option value="All">All ({campaignData.length})</option>
                  </select>
                  <span className="text-slate-500 dark:text-slate-400 border-l border-slate-200 dark:border-white/10 pl-3">
                    Showing Page <span className="text-slate-900 dark:text-white font-bold">{safeCampPage}</span> of <span className="text-slate-900 dark:text-white font-bold">{totalCampPages}</span> ({campaignData.length} total campaigns)
                  </span>
                </div>

                {campPageSize !== 'All' && totalCampPages > 1 && (
                  <div className="flex items-center gap-2">
                    <button 
                      onClick={() => setCampPage(p => Math.max(1, p - 1))}
                      disabled={safeCampPage <= 1}
                      className="p-2 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 transition-all cursor-pointer"
                    >
                      <ChevronLeft className="w-4 h-4 text-slate-700 dark:text-slate-300" />
                    </button>
                    <button 
                      onClick={() => setCampPage(p => Math.min(totalCampPages, p + 1))}
                      disabled={safeCampPage >= totalCampPages}
                      className="p-2 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40 transition-all cursor-pointer"
                    >
                      <ChevronRight className="w-4 h-4 text-slate-700 dark:text-slate-300" />
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Tab 3: Accounting Ledger Audit Table */
        <div className="flex flex-col gap-4">
          <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-100/70 dark:bg-slate-800/60 text-[11px] uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-white/10">
                    <th className="p-3.5 pl-5">Row Type</th>
                    <th className="p-3.5">Row Count</th>
                    <th className="p-3.5">Gross Amount</th>
                    <th className="p-3.5">Processing Fees</th>
                    <th className="p-3.5">Net Amount</th>
                    <th className="p-3.5 pr-5">Description</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200 dark:divide-white/5 text-xs text-slate-800 dark:text-slate-200 font-medium">
                  {(!summary.ledger_breakdown || summary.ledger_breakdown.length === 0) ? (
                    <tr>
                      <td colSpan="6" className="p-8 text-center text-slate-500 dark:text-slate-400 font-semibold">
                        No accounting ledger rows found.
                      </td>
                    </tr>
                  ) : (
                    summary.ledger_breakdown.map((row, idx) => {
                      const rType = String(row.row_type || '').toLowerCase();
                      let badgeStyle = 'bg-slate-100 text-slate-700 border-slate-300 dark:bg-slate-800 dark:text-slate-300';
                      if (rType === 'donation') badgeStyle = 'bg-emerald-100 text-emerald-800 dark:bg-emerald-500/20 dark:text-emerald-300 border-emerald-500/30';
                      else if (rType === 'payout') badgeStyle = 'bg-purple-100 text-purple-800 dark:bg-purple-500/20 dark:text-purple-300 border-purple-500/30';
                      else if (rType === 'reserve') badgeStyle = 'bg-amber-100 text-amber-800 dark:bg-amber-500/20 dark:text-amber-300 border-amber-500/30';
                      else if (rType === 'fx') badgeStyle = 'bg-cyan-100 text-cyan-800 dark:bg-cyan-500/20 dark:text-cyan-300 border-cyan-500/30';
                      else if (rType === 'adjustment') badgeStyle = 'bg-rose-100 text-rose-800 dark:bg-rose-500/20 dark:text-rose-300 border-rose-500/30';
                      else if (rType === 'refund') badgeStyle = 'bg-orange-100 text-orange-800 dark:bg-orange-500/20 dark:text-orange-300 border-orange-500/30';

                      return (
                        <tr key={idx} className="hover:bg-slate-50/60 dark:hover:bg-slate-800/40 transition-colors">
                          <td className="p-3.5 pl-5">
                            <span className={`px-2.5 py-1 rounded-lg text-xs font-mono font-bold uppercase border ${badgeStyle}`}>
                              {row.row_type}
                            </span>
                          </td>
                          <td className="p-3.5 font-bold text-slate-900 dark:text-white">
                            {Number(row.row_count).toLocaleString()}
                          </td>
                          <td className="p-3.5 font-bold text-slate-900 dark:text-white">
                            £{Number(row.gross_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                          </td>
                          <td className="p-3.5 font-semibold text-rose-600 dark:text-rose-400">
                            £{Number(row.processing_fees).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                          </td>
                          <td className={`p-3.5 font-extrabold ${row.net_amount < 0 ? 'text-rose-600 dark:text-rose-400' : 'text-emerald-600 dark:text-emerald-400'}`}>
                            £{Number(row.net_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                          </td>
                          <td className="p-3.5 pr-5 text-slate-600 dark:text-slate-400 text-[11px] font-medium">
                            {row.description}
                          </td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* Super Admin Purge Payout Data Modal */}
      {showPurgeModal && (
        <div className="fixed inset-0 z-50 bg-slate-950/80 backdrop-blur-md flex items-center justify-center p-4">
          <div className="bg-slate-900 border border-rose-500/30 rounded-2xl max-w-md w-full p-6 shadow-2xl flex flex-col gap-4 text-white">
            <div className="flex items-center justify-between border-b border-white/10 pb-3">
              <h3 className="text-base font-extrabold text-rose-400 flex items-center gap-2">
                <AlertCircle className="w-5 h-5" /> Purge Payout Settlement Data
              </h3>
              <button onClick={() => setShowPurgeModal(false)} className="text-slate-400 hover:text-white">
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              This action will permanently delete all LaunchGood payout settlement transactions from the database. Raw donor contribution records will <span className="font-bold text-emerald-400">NOT</span> be affected.
            </p>

            <div className="flex items-center gap-3 p-3 rounded-xl bg-rose-950/40 border border-rose-500/30">
              <input 
                type="checkbox" 
                id="purgeConfirmCheck"
                checked={purgeConfirm}
                onChange={e => setPurgeConfirm(e.target.checked)}
                className="w-4 h-4 rounded border-rose-400 text-rose-600 focus:ring-rose-500 cursor-pointer"
              />
              <label htmlFor="purgeConfirmCheck" className="text-xs font-bold text-rose-200 cursor-pointer">
                I understand this will delete all payout settlement rows.
              </label>
            </div>

            {purgeMsg && (
              <div className={`text-xs font-bold ${purgeMsg.includes('✅') ? 'text-emerald-400' : 'text-rose-400'}`}>
                {purgeMsg}
              </div>
            )}

            <div className="flex items-center justify-end gap-3 pt-2">
              <button 
                onClick={() => setShowPurgeModal(false)}
                className="px-4 py-2 text-xs font-bold rounded-xl bg-slate-800 text-slate-300 hover:bg-slate-700"
              >
                Cancel
              </button>
              <button 
                onClick={handlePurgePayouts}
                disabled={!purgeConfirm || purging}
                className="px-4 py-2 text-xs font-extrabold rounded-xl bg-rose-600 text-white hover:bg-rose-500 disabled:opacity-40 flex items-center gap-1.5 shadow-md shadow-rose-600/30"
              >
                {purging ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                <span>Permanently Purge Payouts</span>
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

