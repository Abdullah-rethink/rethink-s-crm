import React, { useEffect, useState } from 'react';
import { Table, Search, Download, ChevronLeft, ChevronRight, Edit3, UserCheck, Eye, Columns, CheckSquare, Square, Save, ArrowUpDown, ArrowUp, ArrowDown, X, Check, AlertCircle } from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function ExplorerView({ user, filters, onSelectDonor }) {
  const [data, setData] = useState({ total_records: 0, page: 1, page_size: 100, total_pages: 1, available_columns: [], records: [] });
  const [loading, setLoading] = useState(true);
  
  // Controls state
  const [search, setSearch] = useState('');
  const [preset, setPreset] = useState('default');
  const [pageSize, setPageSize] = useState(100);
  const [currentPage, setCurrentPage] = useState(1);
  const [showColumnChooser, setShowColumnChooser] = useState(false);
  const [selectedColumns, setSelectedColumns] = useState([]);
  const [sortBy, setSortBy] = useState(null);
  const [sortOrder, setSortOrder] = useState('asc');

  // Inline Cell Editing State
  const [editingCell, setEditingCell] = useState(null); // { rowIdx, colName, value }
  const [cellMessage, setCellMessage] = useState('');

  // Classification lookups for smart quick-pick and auto-enrichment
  const [campaignCodesLookup, setCampaignCodesLookup] = useState({});
  const [codeMap, setCodeMap] = useState({});

  // Single Donor Record Modal Edit State
  const [editingDonorModal, setEditingDonorModal] = useState(null); // { row, fields }
  const [editModalSaving, setEditModalSaving] = useState(false);
  const [editModalMsg, setEditModalMsg] = useState('');

  // Bulk edit form state
  const [showBulkEdit, setShowBulkEdit] = useState(false);
  const [bulkCol1, setBulkCol1] = useState('First Name');
  const [bulkVal1, setBulkVal1] = useState('');
  const [bulkCol2, setBulkCol2] = useState('');
  const [bulkVal2, setBulkVal2] = useState('');
  const [bulkCol3, setBulkCol3] = useState('');
  const [bulkVal3, setBulkVal3] = useState('');
  const [bulkCol4, setBulkCol4] = useState('');
  const [bulkVal4, setBulkVal4] = useState('');
  const [bulkSaving, setBulkSaving] = useState(false);
  const [bulkMessage, setBulkMessage] = useState('');

  const canEdit = user?.role === 'super_admin' || user?.can_edit_donors === 1;

  // Load Campaign Codes lookup and Code Map on mount
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/classifications/campaign-codes`)
      .then(r => r.json())
      .then(data => { if (data && typeof data === 'object') setCampaignCodesLookup(data); })
      .catch(err => console.error('Error fetching campaign-codes lookup:', err));

    fetch(`${API_BASE_URL}/api/classifications/code-map`)
      .then(r => r.json())
      .then(data => { if (data && typeof data === 'object') setCodeMap(data); })
      .catch(err => console.error('Error fetching code-map:', err));
  }, []);

  const loadDonors = () => {
    setLoading(true);
    const params = new URLSearchParams({
      page: currentPage,
      page_size: pageSize,
      search: search
    });

    if (sortBy) {
      params.append('sort_by', sortBy);
      params.append('sort_order', sortOrder);
    }

    if (filters) {
      if (filters.payment_type) params.append('payment_type', filters.payment_type);
      if (filters.tier) params.append('tier', filters.tier);
      if (filters.source) params.append('source', filters.source);
      if (filters.heading) params.append('heading', filters.heading);
      if (filters.subheading) params.append('subheading', filters.subheading);
      if (filters.country) params.append('country', filters.country);
      if (filters.code) params.append('code', filters.code);
      if (filters.zakat) params.append('zakat', filters.zakat);
      if (filters.donor_country) params.append('donor_country', filters.donor_country);
      if (filters.campaign_search) params.append('campaign_search', filters.campaign_search);
      if (filters.gift_aid) params.append('gift_aid', filters.gift_aid);
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);
    }

    fetch(`${API_BASE_URL}/api/donors?${params.toString()}`)
      .then(res => res.json())
      .then(resData => {
        setData(resData);
        if (resData.available_columns?.length > 0) {
          setSelectedColumns(prev => {
            if (prev && prev.length > 0) {
              const validPrev = prev.filter(c => resData.available_columns.includes(c));
              if (validPrev.length > 0) return validPrev;
            }
            const defaultCols = [
              'First Name',
              'Last Name',
              'Total Online Donations Net Amount in Settled Currency',
              'Transaction Donor Classification',
              'Lifetime Donor Classification',
              'Total LTV',
              'Payment Frequency',
              'Heading',
              'Sub-Heading',
              'Country',
              'Code',
              'Zakat Eligibility'
            ].filter(c => resData.available_columns.includes(c));
            return defaultCols.length > 0 ? defaultCols : resData.available_columns.slice(0, 12);
          });
        }
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching donors explorer:', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadDonors();
  }, [currentPage, pageSize, search, filters, sortBy, sortOrder]);

  const handleToggleColumn = (col) => {
    if (selectedColumns.includes(col)) {
      setSelectedColumns(selectedColumns.filter(c => c !== col));
    } else {
      setSelectedColumns([...selectedColumns, col]);
    }
  };

  const handleInlineSave = (row, colName, newVal) => {
    if (!canEdit) return;

    fetch(`${API_BASE_URL}/api/donors/update-record`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role || 'admin',
        can_edit_donors: canEdit,
        row_id: row._row_id !== undefined && row._row_id !== null ? Number(row._row_id) : null,
        donation_id: row['Donation ID'] || null,
        column_name: colName,
        new_value: String(newVal)
      })
    })
      .then(async r => {
        const text = await r.text();
        try {
          return JSON.parse(text);
        } catch {
          return { status: 'error', detail: text || `HTTP ${r.status}` };
        }
      })
      .then(res => {
        if (res?.status === 'success') {
          setCellMessage(`✅ Saved ${colName}!`);
          setEditingCell(null);
          loadDonors();
          setTimeout(() => setCellMessage(''), 2500);
        } else {
          setCellMessage(`❌ ${res?.detail || 'Save failed'}`);
          setTimeout(() => setCellMessage(''), 3000);
        }
      })
      .catch(err => {
        setCellMessage(`❌ Error: ${err.message}`);
        setTimeout(() => setCellMessage(''), 3000);
      });
  };

  const handleSaveDonorModal = (e) => {
    e.preventDefault();
    if (!editingDonorModal || !canEdit) return;
    setEditModalSaving(true);
    setEditModalMsg('');

    fetch(`${API_BASE_URL}/api/donors/update-record`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role || 'admin',
        can_edit_donors: canEdit,
        row_id: editingDonorModal.row._row_id !== undefined && editingDonorModal.row._row_id !== null ? Number(editingDonorModal.row._row_id) : null,
        donation_id: editingDonorModal.row['Donation ID'] || null,
        updated_fields: editingDonorModal.fields
      })
    })
      .then(async r => {
        const text = await r.text();
        try {
          return JSON.parse(text);
        } catch {
          return { status: 'error', detail: text || `HTTP ${r.status}` };
        }
      })
      .then(res => {
        setEditModalSaving(false);
        if (res?.status === 'success') {
          setEditModalMsg(`✅ Successfully updated donor record!`);
          loadDonors();
          setTimeout(() => {
            setEditingDonorModal(null);
            setEditModalMsg('');
          }, 1000);
        } else {
          setEditModalMsg(`❌ ${res?.detail || 'Failed to update record.'}`);
        }
      })
      .catch(err => {
        setEditModalSaving(false);
        setEditModalMsg(`❌ Error: ${err.message}`);
      });
  };

  const handleBulkEditSubmit = (e) => {
    e.preventDefault();
    setBulkSaving(true);
    setBulkMessage('');

    const target_columns = [];
    const new_values = [];

    if (bulkCol1) {
      target_columns.push(bulkCol1);
      new_values.push(bulkVal1);
    }
    if (bulkCol2) {
      target_columns.push(bulkCol2);
      new_values.push(bulkVal2);
    }
    if (bulkCol3) {
      target_columns.push(bulkCol3);
      new_values.push(bulkVal3);
    }
    if (bulkCol4) {
      target_columns.push(bulkCol4);
      new_values.push(bulkVal4);
    }

    if (target_columns.length === 0) {
      setBulkMessage('❌ Please select at least one target field.');
      setBulkSaving(false);
      return;
    }

    fetch(`${API_BASE_URL}/api/donors/bulk-edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role || 'admin',
        target_columns,
        new_values,
        filter_search: search,
        filter_payment_type: filters?.payment_type,
        filter_tier: filters?.tier,
        filter_source: filters?.source,
        filter_heading: filters?.heading,
        filter_subheading: filters?.subheading,
        filter_country: filters?.country,
        filter_code: filters?.code,
        filter_zakat: filters?.zakat,
        filter_donor_country: filters?.donor_country,
        filter_campaign_search: filters?.campaign_search,
        filter_gift_aid: filters?.gift_aid,
        filter_start_date: filters?.start_date,
        filter_end_date: filters?.end_date
      })
    })
      .then(r => r.json())
      .then(res => {
        setBulkSaving(false);
        if (res?.status === 'success') {
          setBulkMessage(`✅ ${res.message}`);
          loadDonors();
          setTimeout(() => setShowBulkEdit(false), 1500);
        } else {
          setBulkMessage(`❌ ${res?.detail || 'Failed to apply bulk edit.'}`);
        }
      })
      .catch(err => {
        setBulkSaving(false);
        setBulkMessage(`❌ Error: ${err.message}`);
      });
  };

  const COLUMN_ALIASES = {
    'Display Name': 'Donor Name',
    'Total Online Donations Net Amount in Settled Currency': 'Settled Net Amount',
    'Lifetime Donor Classification': 'Lifetime Classification',
    'Transaction Donor Classification': 'Transaction Classification',
    'Campaign Name': 'Campaign',
    'Community Name': 'Community',
    'Created Date (UTC)': 'Date',
    'Donation Amount in Project Currency (May be approx.)': 'Project Amount',
    'Donation Currency (DC)': 'Currency',
    'Payment Frequency': 'Frequency'
  };

  const getTierBadgeClass = (tier) => {
    switch (tier) {
      case 'Super High': return 'badge-pink';
      case 'High': return 'badge-amber';
      case 'Medium': return 'badge-emerald';
      case 'Medium Low': return 'badge-cyan';
      default: return 'badge-slate';
    }
  };

  const formatDate = (val) => {
    if (!val) return 'N/A';
    const str = String(val);
    return str.split('T')[0].split(' ')[0];
  };

  const handleExportDonors = (format) => {
    const params = new URLSearchParams({
      format: format,
      search: search
    });

    if (filters) {
      if (filters.payment_type) params.append('payment_type', filters.payment_type);
      if (filters.tier) params.append('tier', filters.tier);
      if (filters.source) params.append('source', filters.source);
      if (filters.heading) params.append('heading', filters.heading);
      if (filters.subheading) params.append('subheading', filters.subheading);
      if (filters.country) params.append('country', filters.country);
      if (filters.code) params.append('code', filters.code);
      if (filters.zakat) params.append('zakat', filters.zakat);
      if (filters.donor_country) params.append('donor_country', filters.donor_country);
      if (filters.campaign_search) params.append('campaign_search', filters.campaign_search);
      if (filters.gift_aid) params.append('gift_aid', filters.gift_aid);
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);
    }

    window.open(`${API_BASE_URL}/api/donors/export?${params.toString()}`, '_blank');
  };

  return (
    <div className="flex flex-col gap-6">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            <Table className="w-5 h-5 text-cyan-400" /> Data Explorer & 360° Profile Center
          </h2>
          <p className="text-xs text-slate-400">Search, filter, inspect donor 360° profiles, customize visible columns, and edit records.</p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Export Dropdown Group */}
          <div className="flex items-center gap-1 bg-slate-900/90 border border-emerald-500/30 p-1 rounded-xl">
            <button 
              onClick={() => handleExportDonors('csv')}
              className="text-xs font-bold text-emerald-400 hover:bg-emerald-500/20 px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition-all"
              title="Export filtered records as CSV file"
            >
              <Download className="w-3.5 h-3.5" /> CSV
            </button>
            <span className="text-white/20 text-xs">|</span>
            <button 
              onClick={() => handleExportDonors('xlsx')}
              className="text-xs font-bold text-emerald-400 hover:bg-emerald-500/20 px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition-all"
              title="Export filtered records as Excel (.xlsx) file"
            >
              <Download className="w-3.5 h-3.5" /> Excel (.xlsx)
            </button>
          </div>

          <select
            value={preset}
            onChange={e => {
              const val = e.target.value;
              setPreset(val);
              if (val === 'default') {
                setSelectedColumns([
                  'First Name',
                  'Last Name',
                  'Total Online Donations Net Amount in Settled Currency',
                  'Lifetime Donor Classification',
                  'Total LTV',
                  'Transaction Donor Classification',
                  'Payment Frequency',
                  'Heading',
                  'Sub-Heading',
                  'Country',
                  'Code',
                  'Zakat Eligibility'
                ].filter(c => data.available_columns.includes(c)));
              } else if (val === 'all') {
                setSelectedColumns(data.available_columns);
              } else if (val === 'minimal') {
                setSelectedColumns([
                  'First Name',
                  'Last Name',
                  'Total Online Donations Net Amount in Settled Currency',
                  'Payment Frequency'
                ].filter(c => data.available_columns.includes(c)));
              }
            }}
            className="bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500 cursor-pointer"
          >
            <option value="default">📋 Default Preset</option>
            <option value="minimal">🔍 Minimal View</option>
            <option value="all">🌐 All Columns</option>
          </select>

          <button 
            onClick={() => setShowColumnChooser(!showColumnChooser)}
            className="btn-secondary text-xs flex items-center gap-1.5 text-cyan-400 border-cyan-500/30 hover:bg-cyan-500/10"
          >
            <Columns className="w-3.5 h-3.5" /> 📐 Choose Visible Columns ({selectedColumns.length})
          </button>

          {(user?.role === 'super_admin' || user?.can_edit_donors === 1) && (
            <button 
              onClick={() => setShowBulkEdit(!showBulkEdit)}
              className="btn-secondary text-xs flex items-center gap-1.5 text-purple-400 border-purple-500/30 hover:bg-purple-500/10"
            >
              <Edit3 className="w-3.5 h-3.5" /> ⚡ Bulk Edit Records
            </button>
          )}
        </div>
      </div>

      {cellMessage && <div className="text-xs font-bold text-emerald-400 animate-pulse">{cellMessage}</div>}

      {/* Column Chooser Modal UI */}
      {showColumnChooser && (
        <div className="glass-panel p-5 border-l-4 border-cyan-400 flex flex-col gap-4 animate-fadeIn">
          <div className="flex items-center justify-between border-b border-white/10 pb-3">
            <h3 className="text-xs font-extrabold text-white uppercase tracking-wider flex items-center gap-2">
              <Columns className="w-4 h-4 text-cyan-400" /> Select & Customize Visible Columns
            </h3>
            <button onClick={() => setShowColumnChooser(false)} className="text-xs text-slate-400 hover:text-white">Close</button>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-2.5 max-h-[220px] overflow-y-auto pr-1">
            {data.available_columns?.map(col => {
              const isChecked = selectedColumns.includes(col);
              return (
                <div 
                  key={col} 
                  onClick={() => handleToggleColumn(col)}
                  className={`p-2 rounded-lg border text-xs cursor-pointer flex items-center gap-2 transition-all ${
                    isChecked ? 'border-cyan-400/50 bg-cyan-500/10 text-cyan-300 font-bold' : 'border-white/5 bg-slate-900/60 text-slate-400 hover:text-white'
                  }`}
                >
                  {isChecked ? <CheckSquare className="w-4 h-4 text-cyan-400 shrink-0" /> : <Square className="w-4 h-4 text-slate-500 shrink-0" />}
                  <span className="truncate">{COLUMN_ALIASES[col] || col}</span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Bulk Edit Form */}
      {showBulkEdit && (
        <div className="glass-panel p-5 border-l-4 border-purple-400 flex flex-col gap-4 animate-fadeIn">
          <h3 className="text-sm font-bold text-white flex items-center gap-2">
            <Edit3 className="w-4 h-4 text-purple-400" /> Bulk Edit All {data.total_records?.toLocaleString()} Filtered Donor Records
          </h3>
          {bulkMessage && <div className="text-xs font-bold text-emerald-400">{bulkMessage}</div>}

          <form onSubmit={handleBulkEditSubmit} className="flex flex-col gap-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
              {/* Field 1 (Required) */}
              <div className="flex flex-col gap-1.5 p-3 rounded-xl border border-white/5 bg-slate-900/40">
                <label className="text-[11px] text-purple-300 font-bold uppercase tracking-wider">Target Field #1 *</label>
                <select 
                  value={bulkCol1} 
                  onChange={e => setBulkCol1(e.target.value)} 
                  className="w-full bg-slate-900 border border-white/10 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-purple-400"
                >
                  <option value="">-- Choose Field --</option>
                  {data.available_columns.map(col => (
                    <option key={col} value={col}>{COLUMN_ALIASES[col] || col}</option>
                  ))}
                </select>
                <input 
                  type="text" 
                  placeholder="New Value #1..." 
                  value={bulkVal1} 
                  onChange={e => setBulkVal1(e.target.value)} 
                  disabled={!bulkCol1}
                  className="w-full bg-slate-900 border border-white/10 rounded-lg p-2 text-xs text-white disabled:opacity-40 disabled:cursor-not-allowed"
                />
              </div>

              {/* Field 2 (Optional) */}
              <div className="flex flex-col gap-1.5 p-3 rounded-xl border border-white/5 bg-slate-900/40">
                <label className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">Target Field #2 (Optional)</label>
                <select 
                  value={bulkCol2} 
                  onChange={e => setBulkCol2(e.target.value)} 
                  className="w-full bg-slate-900 border border-white/10 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-purple-400"
                >
                  <option value="">-- None --</option>
                  {data.available_columns.map(col => (
                    <option key={col} value={col}>{COLUMN_ALIASES[col] || col}</option>
                  ))}
                </select>
                <input 
                  type="text" 
                  placeholder="New Value #2..." 
                  value={bulkVal2} 
                  onChange={e => setBulkVal2(e.target.value)} 
                  disabled={!bulkCol2}
                  className="w-full bg-slate-900 border border-white/10 rounded-lg p-2 text-xs text-white disabled:opacity-40 disabled:cursor-not-allowed"
                />
              </div>

              {/* Field 3 (Optional) */}
              <div className="flex flex-col gap-1.5 p-3 rounded-xl border border-white/5 bg-slate-900/40">
                <label className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">Target Field #3 (Optional)</label>
                <select 
                  value={bulkCol3} 
                  onChange={e => setBulkCol3(e.target.value)} 
                  className="w-full bg-slate-900 border border-white/10 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-purple-400"
                >
                  <option value="">-- None --</option>
                  {data.available_columns.map(col => (
                    <option key={col} value={col}>{COLUMN_ALIASES[col] || col}</option>
                  ))}
                </select>
                <input 
                  type="text" 
                  placeholder="New Value #3..." 
                  value={bulkVal3} 
                  onChange={e => setBulkVal3(e.target.value)} 
                  disabled={!bulkCol3}
                  className="w-full bg-slate-900 border border-white/10 rounded-lg p-2 text-xs text-white disabled:opacity-40 disabled:cursor-not-allowed"
                />
              </div>

              {/* Field 4 (Optional) */}
              <div className="flex flex-col gap-1.5 p-3 rounded-xl border border-white/5 bg-slate-900/40">
                <label className="text-[11px] text-slate-400 font-bold uppercase tracking-wider">Target Field #4 (Optional)</label>
                <select 
                  value={bulkCol4} 
                  onChange={e => setBulkCol4(e.target.value)} 
                  className="w-full bg-slate-900 border border-white/10 rounded-lg p-2 text-xs text-white focus:outline-none focus:border-purple-400"
                >
                  <option value="">-- None --</option>
                  {data.available_columns.map(col => (
                    <option key={col} value={col}>{COLUMN_ALIASES[col] || col}</option>
                  ))}
                </select>
                <input 
                  type="text" 
                  placeholder="New Value #4..." 
                  value={bulkVal4} 
                  onChange={e => setBulkVal4(e.target.value)} 
                  disabled={!bulkCol4}
                  className="w-full bg-slate-900 border border-white/10 rounded-lg p-2 text-xs text-white disabled:opacity-40 disabled:cursor-not-allowed"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 mt-2">
              <button type="button" onClick={() => setShowBulkEdit(false)} className="btn-secondary text-xs">Cancel</button>
              <button type="submit" disabled={bulkSaving} className="btn-primary text-xs">
                {bulkSaving ? 'Saving...' : '⚡ Apply Bulk Changes Now'}
              </button>
            </div>
          </form>
        </div>
      )}

      {/* Control Toolbar */}
      <div className="glass-panel p-4 flex flex-wrap items-center justify-between gap-4">
        {/* Search */}
        <div className="relative min-w-[340px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
          <input 
            type="text"
            placeholder="🔍 Quick Search (Name, Email, Campaign, or Donation ID(s)...)"
            value={search}
            onChange={e => { setSearch(e.target.value); setCurrentPage(1); }}
            className="w-full bg-slate-900/90 border border-white/10 rounded-xl pl-10 pr-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500 transition-all"
          />
        </div>

        {/* Page Size */}
        <div className="flex items-center gap-2">
          <span className="text-xs text-slate-400 font-bold">Page Size:</span>
          <select 
            value={pageSize} 
            onChange={e => { setPageSize(Number(e.target.value)); setCurrentPage(1); }}
            className="bg-slate-900 border border-white/10 rounded-xl px-3 py-2 text-xs text-white focus:outline-none focus:border-cyan-500"
          >
            <option value={50}>50 rows</option>
            <option value={100}>100 rows</option>
            <option value={250}>250 rows</option>
            <option value={500}>500 rows</option>
          </select>
        </div>

        {/* Cell Message Banner */}
        {cellMessage && (
          <div className="p-2.5 rounded-xl bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 text-xs font-bold flex items-center gap-2 animate-fade-in">
            <Check className="w-4 h-4 text-cyan-400" />
            <span>{cellMessage}</span>
          </div>
        )}
      </div>

      {/* Single Donor Record Edit Modal */}
      {editingDonorModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-md animate-fade-in">
          <div className="bg-slate-900 border border-white/15 rounded-3xl p-6 max-w-xl w-full shadow-2xl flex flex-col gap-5 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-white/10 pb-4">
              <div className="flex items-center gap-2.5">
                <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                  <Edit3 className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-black text-white">
                    Edit Donor Record
                  </h3>
                  <p className="text-xs text-slate-400">
                    {editingDonorModal.row['Display Name'] || editingDonorModal.row['First Name'] || 'Donor Record'} {editingDonorModal.row['Donation ID'] ? `(#${editingDonorModal.row['Donation ID']})` : ''}
                  </p>
                </div>
              </div>
              <button
                onClick={() => setEditingDonorModal(null)}
                className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {editModalMsg && (
              <div className={`p-3 rounded-xl text-xs font-bold flex items-center gap-2 ${editModalMsg.startsWith('✅') ? 'bg-emerald-500/15 text-emerald-300 border border-emerald-500/30' : 'bg-rose-500/15 text-rose-300 border border-rose-500/30'}`}>
                {editModalMsg.startsWith('✅') ? <Check className="w-4 h-4 text-emerald-400" /> : <AlertCircle className="w-4 h-4 text-rose-400" />}
                <span>{editModalMsg}</span>
              </div>
            )}

            <form onSubmit={handleSaveDonorModal} className="flex flex-col gap-4">
              {/* 🎯 Smart Campaign Code Quick-Pick (If Campaign has known code variants) */}
              {(() => {
                const activeCName = (editingDonorModal.fields['Campaign Name'] || editingDonorModal.row['Campaign Name'] || '').trim().toLowerCase();
                const variants = (activeCName && campaignCodesLookup[activeCName]) || [];
                if (variants.length === 0) return null;

                return (
                  <div className="p-3.5 rounded-2xl bg-amber-500/10 border border-amber-500/30 flex flex-col gap-2 shadow-inner">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-bold text-amber-300 uppercase tracking-wider flex items-center gap-1.5">
                        🎯 Campaign Quick-Pick ({variants.length} Code {variants.length > 1 ? 'Variants' : 'Variant'})
                      </span>
                      <span className="text-[10px] text-amber-200/70">Click variant to auto-fill all classification fields</span>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {variants.map(v => {
                        const isSelected = editingDonorModal.fields['Code']?.trim().toUpperCase() === v.code.toUpperCase();
                        return (
                          <button
                            key={v.code}
                            type="button"
                            onClick={() => {
                              setEditingDonorModal(prev => ({
                                ...prev,
                                fields: {
                                  ...prev.fields,
                                  'Code': v.code,
                                  'Heading': v.heading,
                                  'Sub-Heading': v.sub_heading,
                                  'Country': v.country,
                                  'Zakat Eligibility': v.zakat_eligibility
                                }
                              }));
                            }}
                            className={`px-3 py-1.5 rounded-xl text-xs font-mono font-bold transition-all cursor-pointer flex items-center gap-1.5 ${
                              isSelected
                                ? 'bg-amber-400 text-slate-950 shadow-md shadow-amber-500/30 ring-2 ring-amber-300'
                                : 'bg-slate-800/90 text-amber-300 hover:bg-amber-500/20 border border-amber-500/30'
                            }`}
                          >
                            <span>{v.code}</span>
                            {v.is_primary && <span className="text-[10px] text-emerald-400 font-sans">⭐ Primary</span>}
                            <span className="text-[10px] opacity-70 font-sans font-normal">({v.heading} • {v.country})</span>
                          </button>
                        );
                      })}
                    </div>
                  </div>
                );
              })()}

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3.5 text-xs">
                {Object.keys(editingDonorModal.fields).map(field => {
                  const isCodeField = field === 'Code';
                  return (
                    <div key={field} className="flex flex-col gap-1.5">
                      <label className="text-slate-400 font-bold uppercase tracking-wider text-[10px]">
                        {COLUMN_ALIASES[field] || field}
                      </label>
                      <input
                        type="text"
                        list={isCodeField ? "explorer-modal-codes-list" : undefined}
                        value={editingDonorModal.fields[field] || ''}
                        onChange={e => {
                          const val = e.target.value;
                          let updatedFields = {
                            ...editingDonorModal.fields,
                            [field]: val
                          };
                          // If user typed/selected a Code, auto-fill recognized fields
                          if (isCodeField) {
                            const codeKey = (val || '').trim().toLowerCase();
                            if (codeMap[codeKey]) {
                              const cInfo = codeMap[codeKey];
                              if (cInfo.Heading && cInfo.Heading !== 'Unassigned') updatedFields['Heading'] = cInfo.Heading;
                              if (cInfo['Sub-Heading'] && cInfo['Sub-Heading'] !== 'Unassigned') updatedFields['Sub-Heading'] = cInfo['Sub-Heading'];
                              if (cInfo.Country && cInfo.Country !== 'Unassigned') updatedFields['Country'] = cInfo.Country;
                              if (cInfo['Zakat Eligibility'] && cInfo['Zakat Eligibility'] !== 'Unassigned') updatedFields['Zakat Eligibility'] = cInfo['Zakat Eligibility'];
                            }
                          }
                          setEditingDonorModal({
                            ...editingDonorModal,
                            fields: updatedFields
                          });
                        }}
                        className={`bg-slate-950 border border-white/10 rounded-xl px-3 py-2 text-white text-xs focus:outline-none focus:border-cyan-400 transition-all ${
                          isCodeField ? 'font-mono uppercase font-bold text-cyan-400 border-cyan-500/40' : ''
                        }`}
                      />
                    </div>
                  );
                })}
              </div>

              <datalist id="explorer-modal-codes-list">
                {Object.keys(codeMap).map(k => (
                  <option key={k} value={k.toUpperCase()} />
                ))}
              </datalist>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => setEditingDonorModal(null)}
                  className="px-4 py-2 rounded-xl text-xs font-bold text-slate-400 hover:text-white bg-slate-800 hover:bg-slate-700 transition-all cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editModalSaving}
                  className="px-5 py-2 rounded-xl text-xs font-bold text-slate-950 bg-gradient-to-r from-emerald-400 to-teal-400 hover:from-emerald-300 hover:to-teal-300 shadow-md shadow-emerald-500/20 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
                >
                  {editModalSaving ? (
                    <span>Saving...</span>
                  ) : (
                    <>
                      <Save className="w-3.5 h-3.5" />
                      <span>Save Changes</span>
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Sleek Pagination Bar */}
      <div className="glass-panel px-4 py-3 flex flex-wrap items-center justify-between gap-4 text-xs">
        <div className="flex items-center gap-2">
          <button 
            disabled={currentPage <= 1}
            onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
            className="btn-secondary text-xs px-3 py-1.5 disabled:opacity-40"
          >
            <ChevronLeft className="w-3.5 h-3.5 inline mr-1" /> Prev
          </button>
          <button 
            disabled={currentPage >= data.total_pages}
            onClick={() => setCurrentPage(prev => Math.min(data.total_pages, prev + 1))}
            className="btn-secondary text-xs px-3 py-1.5 disabled:opacity-40"
          >
            Next <ChevronRight className="w-3.5 h-3.5 inline ml-1" />
          </button>

          <span className="badge badge-cyan ml-2">Page {currentPage} of {data.total_pages}</span>
        </div>

        <div className="text-slate-400 font-medium">
          Showing <b className="text-cyan-400">{((currentPage - 1) * pageSize) + 1} - {Math.min(currentPage * pageSize, data.total_records)}</b> of <b className="text-white">{data.total_records?.toLocaleString()}</b> total records
        </div>
      </div>

      {/* Main Data Table */}
      {loading ? (
        <div className="py-24 text-center text-slate-400 font-semibold animate-pulse">
          ⚡ Loading Explorer Records...
        </div>
      ) : (
        <div className="glass-panel overflow-hidden border border-white/10 rounded-2xl shadow-2xl">
          <div className="overflow-x-auto max-h-[640px]">
            <table className="crm-table">
              <thead className="sticky top-0 z-20 backdrop-blur-md bg-slate-900/90 border-b border-white/10">
                <tr>
                  <th className="whitespace-nowrap font-extrabold tracking-wider text-center pl-4 w-20">
                    Actions
                  </th>
                  {selectedColumns.map(c => {
                    const isSorted = sortBy === c;
                    return (
                      <th 
                        key={c} 
                        onClick={() => {
                          if (sortBy === c) {
                            if (sortOrder === 'asc') {
                              setSortOrder('desc');
                            } else {
                              setSortBy(null);
                              setSortOrder('asc');
                            }
                          } else {
                            setSortBy(c);
                            setSortOrder('asc');
                          }
                          setCurrentPage(1);
                        }}
                        className="whitespace-nowrap font-extrabold tracking-wider cursor-pointer hover:bg-white/5 select-none transition-colors group"
                      >
                        <div className="flex items-center gap-1.5 justify-between">
                          <span>{COLUMN_ALIASES[c] || c}</span>
                          <span className="text-slate-400 group-hover:text-white transition-colors">
                            {isSorted ? (
                              sortOrder === 'asc' ? <ArrowUp className="w-3.5 h-3.5 text-cyan-400" /> : <ArrowDown className="w-3.5 h-3.5 text-cyan-400" />
                            ) : (
                              <ArrowUpDown className="w-3 h-3 opacity-30 group-hover:opacity-100" />
                            )}
                          </span>
                        </div>
                      </th>
                    );
                  })}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {data.records?.map((row, rowIdx) => {
                  const donorKey = row['Email'] || row['Display Name'] || row['First Name'];
                  return (
                    <tr 
                      key={rowIdx} 
                      className="hover:bg-cyan-500/5 transition-colors group"
                    >
                      {/* Actions Column on Extreme Left */}
                      <td className="whitespace-nowrap text-center pl-4 w-20">
                        <div className="flex items-center justify-center gap-1.5" onClick={e => e.stopPropagation()}>
                          <button
                            type="button"
                            onClick={() => onSelectDonor(donorKey)}
                            className="p-1.5 rounded-lg text-cyan-400 hover:bg-cyan-500/15 transition-all cursor-pointer"
                            title="View Donor Profile Drawer"
                          >
                            <Eye className="w-3.5 h-3.5" />
                          </button>
                          {canEdit && (
                            <button
                              type="button"
                              onClick={() => setEditingDonorModal({
                                row,
                                fields: {
                                  'First Name': row['First Name'] || '',
                                  'Last Name': row['Last Name'] || '',
                                  'Email': row['Email'] || '',
                                  'Campaign Name': row['Campaign Name'] || '',
                                  'Heading': row['Heading'] || '',
                                  'Sub-Heading': row['Sub-Heading'] || '',
                                  'Country': row['Country'] || '',
                                  'Code': row['Code'] || '',
                                  'Zakat Eligibility': row['Zakat Eligibility'] || ''
                                }
                              })}
                              className="p-1.5 rounded-lg text-emerald-400 hover:bg-emerald-500/15 transition-all cursor-pointer"
                              title="Edit Donor Record Details"
                            >
                              <Edit3 className="w-3.5 h-3.5" />
                            </button>
                          )}
                        </div>
                      </td>

                      {selectedColumns.map(c => {
                        const val = row[c];

                        if (c === 'First Name' || c === 'Display Name') {
                          const isSettled = String(row['Payout Settled'] || row['payout_settled'] || '').toLowerCase() === 'yes';
                          return (
                            <td 
                              key={c} 
                              className="whitespace-nowrap font-medium"
                            >
                              <div className="flex items-center gap-2">
                                <button
                                  type="button"
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    onSelectDonor(donorKey);
                                  }}
                                  className="text-cyan-400 hover:text-cyan-300 font-bold hover:underline flex items-center gap-1.5 cursor-pointer text-left"
                                  title="Click to view donor detail side view"
                                >
                                  <Eye className="w-3 h-3 opacity-60 group-hover:opacity-100" />
                                  <span>{val || 'Unnamed Donor'}</span>
                                </button>
                                {isSettled && (
                                  <span className="text-[10px] px-2 py-0.5 rounded-full font-extrabold uppercase bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30 shadow-sm" title="Donor transaction settled in payout bank transfer">
                                    Settled
                                  </span>
                                )}
                              </div>
                            </td>
                          );
                        }
                        if (c === 'Total Online Donations Net Amount in Settled Currency' || typeof val === 'number') {
                          return (
                            <td 
                              key={c} 
                              className="font-mono text-cyan-400 font-extrabold whitespace-nowrap"
                            >
                              £{typeof val === 'number' ? val.toFixed(2) : parseFloat(val || 0).toFixed(2)}
                            </td>
                          );
                        }
                        if (c === 'Lifetime Donor Classification' || c === 'Transaction Donor Classification') {
                          return (
                            <td 
                              key={c} 
                              className="whitespace-nowrap"
                            >
                              <span className={`badge ${getTierBadgeClass(val)}`}>{val || 'Unassigned'}</span>
                            </td>
                          );
                        }
                        if (c === 'Created Date (UTC)') {
                          return (
                            <td 
                              key={c} 
                              className="text-slate-400 text-xs font-mono whitespace-nowrap"
                            >
                              {formatDate(val)}
                            </td>
                          );
                        }
                        return (
                          <td 
                            key={c} 
                            className="max-w-[240px] truncate text-slate-200"
                          >
                            {val !== undefined && val !== null ? String(val) : ''}
                          </td>
                        );
                      })}
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
