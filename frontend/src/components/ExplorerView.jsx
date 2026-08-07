import React, { useEffect, useState } from 'react';
import { Table, Search, Download, ChevronLeft, ChevronRight, Edit3, UserCheck, Eye, Columns, CheckSquare, Square, Save } from 'lucide-react';
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

  // Inline Cell Editing State
  const [editingCell, setEditingCell] = useState(null); // { rowIdx, colName, value }
  const [cellMessage, setCellMessage] = useState('');

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

  const loadDonors = () => {
    setLoading(true);
    const params = new URLSearchParams({
      page: currentPage,
      page_size: pageSize,
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
    }

    fetch(`${API_BASE_URL}/api/donors?${params.toString()}`)
      .then(res => res.json())
      .then(resData => {
        setData(resData);
        if (selectedColumns.length === 0 && resData.available_columns?.length > 0) {
          // Initialize default columns
          setSelectedColumns(resData.available_columns.slice(0, 10));
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
  }, [currentPage, pageSize, search, filters]);

  const handleToggleColumn = (col) => {
    if (selectedColumns.includes(col)) {
      setSelectedColumns(selectedColumns.filter(c => c !== col));
    } else {
      setSelectedColumns([...selectedColumns, col]);
    }
  };

  const handleInlineSave = (row, colName, newVal) => {
    if (user?.role !== 'super_admin') return;

    fetch(`${API_BASE_URL}/api/donors/bulk-edit`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role,
        target_columns: [colName],
        new_values: [newVal],
        filter_search: row['Email'] || row['Display Name']
      })
    })
      .then(r => r.json())
      .then(res => {
        if (res?.status === 'success') {
          setCellMessage('✅ Saved cell edit!');
          setEditingCell(null);
          loadDonors();
          setTimeout(() => setCellMessage(''), 2000);
        }
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
        filter_campaign_search: filters?.campaign_search
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
      case 'Super High': return 'badge-purple';
      case 'High': return 'badge-pink';
      case 'Medium': return 'badge-cyan';
      case 'Medium Low': return 'badge-emerald';
      default: return 'badge-amber';
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
        <div className="relative min-w-[300px]">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-3" />
          <input 
            type="text"
            placeholder="🔍 Quick Search (Name / Email / Campaign)..."
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
      </div>

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
                  <th className="w-12 text-center">360°</th>
                  {selectedColumns.map(c => (
                    <th key={c} className="whitespace-nowrap font-extrabold tracking-wider">
                      {COLUMN_ALIASES[c] || c}
                    </th>
                  ))}
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
                      <td className="text-center py-2 px-3">
                        <button 
                          onClick={() => onSelectDonor(donorKey)}
                          title="Open Donor 360 Profile"
                          className="w-7 h-7 rounded-lg bg-slate-800 group-hover:bg-cyan-500/20 group-hover:text-cyan-400 flex items-center justify-center text-slate-400 transition-all"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                      </td>
                      {selectedColumns.map(c => {
                        const val = row[c];
                        const isEditingThis = editingCell?.rowIdx === rowIdx && editingCell?.colName === c;

                        if (isEditingThis) {
                          return (
                            <td key={c} className="p-1">
                              <div className="flex items-center gap-1">
                                <input 
                                  type="text" 
                                  value={editingCell.value} 
                                  onChange={e => setEditingCell({ ...editingCell, value: e.target.value })}
                                  className="bg-slate-900 border border-cyan-400 rounded px-2 py-1 text-xs text-white w-full"
                                />
                                <button 
                                  onClick={() => handleInlineSave(row, c, editingCell.value)}
                                  className="p-1 rounded bg-cyan-500 text-slate-950 font-bold text-xs"
                                >
                                  <Save className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </td>
                          );
                        }

                        if (c === 'Total Online Donations Net Amount in Settled Currency' || typeof val === 'number') {
                          return (
                            <td key={c} className="font-mono text-cyan-400 font-extrabold whitespace-nowrap">
                              £{typeof val === 'number' ? val.toFixed(2) : parseFloat(val || 0).toFixed(2)}
                            </td>
                          );
                        }
                        if (c === 'Lifetime Donor Classification' || c === 'Transaction Donor Classification') {
                          return (
                            <td key={c} className="whitespace-nowrap">
                              <span className={`badge ${getTierBadgeClass(val)}`}>{val || 'Unassigned'}</span>
                            </td>
                          );
                        }
                        if (c === 'Created Date (UTC)') {
                          return (
                            <td key={c} className="text-slate-400 text-xs font-mono whitespace-nowrap">
                              {formatDate(val)}
                            </td>
                          );
                        }
                        return (
                          <td 
                            key={c} 
                            onDoubleClick={() => (user?.role === 'super_admin' || user?.can_edit_donors === 1) && setEditingCell({ rowIdx, colName: c, value: String(val || '') })}
                            title={(user?.role === 'super_admin' || user?.can_edit_donors === 1) ? "Double click to edit inline" : ""}
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
