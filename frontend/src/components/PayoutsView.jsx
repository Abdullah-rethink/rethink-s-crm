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
  ChevronRight
} from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function PayoutsView({ user, accentColor }) {
  const [summary, setSummary] = useState({
    total_gross: 0,
    total_fees: 0,
    total_reserves: 0,
    net_payout: 0,
    total_transactions: 0,
    settled_donations_count: 0
  });
  
  const [batchesData, setBatchesData] = useState({ total_batches: 0, page: 1, page_size: 25, total_pages: 1, batches: [] });
  const [campaignData, setCampaignData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('batches'); // 'batches' or 'campaigns'
  
  const [search, setSearch] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  // Campaign Breakdown Pagination State
  const [campPage, setCampPage] = useState(1);
  const [campPageSize, setCampPageSize] = useState(25);

  // Purge Payout Modal State
  const [showPurgeModal, setShowPurgeModal] = useState(false);
  const [purgeConfirm, setPurgeConfirm] = useState(false);
  const [purging, setPurging] = useState(false);
  const [purgeMsg, setPurgeMsg] = useState('');

  const isSuperAdmin = user?.role === 'super_admin';

  const fetchPayoutData = () => {
    setLoading(true);
    const searchParam = search ? `?search=${encodeURIComponent(search)}` : '';
    
    Promise.all([
      fetch(`${API_BASE_URL}/api/payouts/summary`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/payouts/batches?page=${currentPage}&page_size=${pageSize}&search=${encodeURIComponent(search)}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/payouts/campaign-breakdown${searchParam}`).then(r => r.json())
    ])
      .then(([sumRes, batchRes, campRes]) => {
        setSummary(sumRes);
        setBatchesData(batchRes);
        setCampaignData(campRes.campaigns || []);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error loading payout reconciliation data:', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchPayoutData();
  }, [currentPage, pageSize, search]);

  const handlePageChange = (newPage) => {
    if (newPage >= 1 && newPage <= batchesData.total_pages) {
      setCurrentPage(newPage);
    }
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

  // Campaign Breakdown Pagination Calculations
  const effectiveCampPageSize = campPageSize === 'All' ? Math.max(1, campaignData.length) : Number(campPageSize);
  const totalCampPages = Math.max(1, Math.ceil(campaignData.length / effectiveCampPageSize));
  const safeCampPage = Math.min(Math.max(1, campPage), totalCampPages);

  const paginatedCampaigns = campPageSize === 'All' 
    ? campaignData 
    : campaignData.slice((safeCampPage - 1) * effectiveCampPageSize, safeCampPage * effectiveCampPageSize);

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
            <span>Refresh Reconciliation</span>
          </button>
        </div>
      </div>

      {/* Top 4 Financial Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Gross Settlement */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Gross Settlement</span>
            <div className="p-2 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 rounded-xl">
              <DollarSign className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-black text-slate-900 dark:text-white">
            £{summary.total_gross.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
            From {summary.settled_donations_count.toLocaleString()} settled donor transactions
          </div>
        </div>

        {/* Processing Fees Paid */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Processing Fees Paid</span>
            <div className="p-2 bg-rose-500/10 text-rose-600 dark:text-rose-400 rounded-xl">
              <CreditCard className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-black text-rose-600 dark:text-rose-400">
            £{summary.total_fees.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
            {summary.total_gross > 0 ? ((summary.total_fees / summary.total_gross) * 100).toFixed(2) : '0.00'}% platform & CC fee ratio
          </div>
        </div>

        {/* Reserve Withheld */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Reserve Withheld</span>
            <div className="p-2 bg-amber-500/10 text-amber-600 dark:text-amber-400 rounded-xl">
              <Layers className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-black text-amber-600 dark:text-amber-400">
            £{summary.total_reserves.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium">
            Platform rolling reserves & hold funds
          </div>
        </div>

        {/* Net Bank Transfers Received */}
        <div className="p-5 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold uppercase tracking-wider text-slate-500 dark:text-slate-400">Net Bank Transfers</span>
            <div className="p-2 bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 rounded-xl">
              <Building className="w-4 h-4" />
            </div>
          </div>
          <div className="text-2xl font-black text-cyan-600 dark:text-cyan-400">
            £{summary.net_payout.toLocaleString('en-GB', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
          </div>
          <div className="text-[11px] text-slate-500 dark:text-slate-400 font-medium flex items-center gap-1">
            <CheckCircle className="w-3.5 h-3.5 text-cyan-500" />
            <span>Net payout transferred to bank</span>
          </div>
        </div>
      </div>

      {/* Sub-Tab Navigation & Search Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 p-4 rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm">
        {/* Tab Buttons */}
        <div className="flex items-center gap-2">
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
            <TrendingUp className="w-3.5 h-3.5" />
            <span>Campaign Fee Breakdown ({campaignData.length})</span>
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
      ) : (
        /* Tab 2: Campaign Fee Breakdown Table (with Full Pagination) */
        <div className="flex flex-col gap-4">
          <div className="rounded-2xl border border-slate-200 dark:border-white/10 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl shadow-sm overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-slate-100/70 dark:bg-slate-800/60 text-[11px] uppercase font-bold text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-white/10">
                    <th className="p-3.5 pl-5">Campaign / Project Name</th>
                    <th className="p-3.5">Classification</th>
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
                            <span className="text-slate-500 dark:text-slate-400 text-[10px]">{camp.code !== 'Unassigned' ? camp.code : camp.sub_heading}</span>
                          </div>
                        </td>
                        <td className="p-3.5 font-bold text-slate-900 dark:text-white">
                          £{Number(camp.gross_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-3.5 font-semibold text-rose-600 dark:text-rose-400">
                          £{Number(camp.processing_fees).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
                        </td>
                        <td className="p-3.5">
                          <div className="flex items-center gap-2 min-w-[100px]">
                            <div className="w-16 bg-slate-200 dark:bg-slate-800 rounded-full h-1.5 overflow-hidden">
                              <div 
                                className="bg-rose-500 h-full rounded-full" 
                                style={{ width: `${Math.min(100, camp.fee_percentage * 5)}%` }}
                              ></div>
                            </div>
                            <span className="text-[11px] font-bold text-rose-600 dark:text-rose-400">{camp.fee_percentage}%</span>
                          </div>
                        </td>
                        <td className="p-3.5 pr-5 font-extrabold text-emerald-600 dark:text-emerald-400">
                          £{Number(camp.transfer_amount).toLocaleString('en-GB', { minimumFractionDigits: 2 })}
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

