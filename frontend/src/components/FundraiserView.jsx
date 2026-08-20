import React, { useEffect, useState, useMemo } from 'react';
import { 
  HeartHandshake, PlusCircle, Search, Filter, Calendar, Target, 
  TrendingUp, Users, DollarSign, Edit3, Trash2, Eye, X, Check, 
  RefreshCw, ChevronRight, BarChart3, Clock, AlertCircle, ShieldAlert,
  Layers, CheckCircle2, Award, ArrowUpRight, LayoutGrid, List, Sparkles,
  Lock
} from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function FundraiserView({ user, accentColor = 'cyan' }) {
  // Strictly enforce that only Super Admin accounts can manage fundraisers
  const isSuperAdmin = user?.role?.toLowerCase() === 'super_admin';

  // Data State
  const [fundraisersData, setFundraisersData] = useState({ summary: {}, fundraisers: [] });
  const [availableCampaigns, setAvailableCampaigns] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  // Filters & View State
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [dateFilterMode, setDateFilterMode] = useState('all'); // 'all', 'this_year', 'last_year', 'last_30', 'last_90', 'custom'
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');
  const [appliedStartDate, setAppliedStartDate] = useState('');
  const [appliedEndDate, setAppliedEndDate] = useState('');
  const [viewMode, setViewMode] = useState('grid'); // 'grid' or 'table'

  // Modal State (Create / Edit)
  const [showModal, setShowModal] = useState(false);
  const [editingFundraiser, setEditingFundraiser] = useState(null);
  const [modalForm, setModalForm] = useState({
    name: '',
    email: '',
    phone: '',
    target_goal: '',
    start_date: '',
    status: 'ACTIVE',
    notes: '',
    assigned_campaigns: []
  });
  const [campaignSearch, setCampaignSearch] = useState('');
  const [platformFilter, setPlatformFilter] = useState('ALL');
  const [assignmentFilter, setAssignmentFilter] = useState('ALL'); // 'ALL', 'UNASSIGNED', 'ASSIGNED_THIS'
  const [submitting, setSubmitting] = useState(false);
  const [formMsg, setFormMsg] = useState('');

  // Delete State
  const [deleteConfirm, setDeleteConfirm] = useState(null);
  const [deleting, setDeleting] = useState(false);

  // Drilldown Drawer State
  const [selectedFundraiserId, setSelectedFundraiserId] = useState(null);
  const [drilldownData, setDrilldownData] = useState(null);
  const [loadingDrilldown, setLoadingDrilldown] = useState(false);
  const [drilldownStartDate, setDrilldownStartDate] = useState('');
  const [drilldownEndDate, setDrilldownEndDate] = useState('');

  // Synchronize applied date filters based on preset buttons
  const handleDatePresetChange = (mode) => {
    setDateFilterMode(mode);
    const today = new Date();
    if (mode === 'all') {
      setAppliedStartDate('');
      setAppliedEndDate('');
      setCustomStartDate('');
      setCustomEndDate('');
    } else if (mode === 'this_year') {
      const start = `${today.getFullYear()}-01-01`;
      setAppliedStartDate(start);
      setAppliedEndDate('');
      setCustomStartDate(start);
      setCustomEndDate('');
    } else if (mode === 'last_year') {
      const start = `${today.getFullYear() - 1}-01-01`;
      const end = `${today.getFullYear() - 1}-12-31`;
      setAppliedStartDate(start);
      setAppliedEndDate(end);
      setCustomStartDate(start);
      setCustomEndDate(end);
    } else if (mode === 'last_30') {
      const d = new Date();
      d.setDate(today.getDate() - 30);
      const start = d.toISOString().split('T')[0];
      setAppliedStartDate(start);
      setAppliedEndDate('');
      setCustomStartDate(start);
      setCustomEndDate('');
    } else if (mode === 'last_90') {
      const d = new Date();
      d.setDate(today.getDate() - 90);
      const start = d.toISOString().split('T')[0];
      setAppliedStartDate(start);
      setAppliedEndDate('');
      setCustomStartDate(start);
      setCustomEndDate('');
    } else if (mode === 'custom') {
      // Keep existing custom inputs
    }
  };

  const handleApplyCustomDateRange = (e) => {
    if (e) e.preventDefault();
    setAppliedStartDate(customStartDate);
    setAppliedEndDate(customEndDate);
  };

  const handleClearDateFilter = () => {
    setDateFilterMode('all');
    setAppliedStartDate('');
    setAppliedEndDate('');
    setCustomStartDate('');
    setCustomEndDate('');
  };

  // Load fundraisers list
  const loadFundraisers = (silent = false) => {
    if (!silent) setLoading(true);
    setRefreshing(true);

    const params = new URLSearchParams();
    if (appliedStartDate) params.append('start_date', appliedStartDate);
    if (appliedEndDate) params.append('end_date', appliedEndDate);
    if (statusFilter !== 'ALL') params.append('status_filter', statusFilter);

    fetch(`${API_BASE_URL}/api/fundraisers?${params.toString()}`)
      .then(res => res.json())
      .then(data => {
        setFundraisersData(data);
        setLoading(false);
        setRefreshing(false);
      })
      .catch(err => {
        console.error('Error fetching fundraisers:', err);
        setLoading(false);
        setRefreshing(false);
      });
  };

  // Load available campaigns for assignment
  const loadCampaignsList = () => {
    fetch(`${API_BASE_URL}/api/fundraisers/campaigns-list`)
      .then(res => res.json())
      .then(data => setAvailableCampaigns(data || []))
      .catch(err => console.error('Error fetching campaigns list:', err));
  };

  // Load Drilldown for selected fundraiser
  const loadDrilldown = (fid, sDate = drilldownStartDate, eDate = drilldownEndDate) => {
    if (!fid) return;
    setLoadingDrilldown(true);
    const params = new URLSearchParams();
    if (sDate) params.append('start_date', sDate);
    if (eDate) params.append('end_date', eDate);

    fetch(`${API_BASE_URL}/api/fundraisers/${fid}?${params.toString()}`)
      .then(res => res.json())
      .then(data => {
        setDrilldownData(data);
        setLoadingDrilldown(false);
      })
      .catch(err => {
        console.error('Error loading drilldown:', err);
        setLoadingDrilldown(false);
      });
  };

  useEffect(() => {
    loadFundraisers();
    loadCampaignsList();

    // WebSocket real-time events listener
    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsHost = API_BASE_URL ? API_BASE_URL.replace(/^http/, 'ws') : `${wsProtocol}//${window.location.host}`;
    const wsUrl = `${wsHost}/ws/events`;

    let socket;
    try {
      socket = new WebSocket(wsUrl);
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (['FUNDRAISER_UPDATED', 'DONORS_UPDATED', 'MATRIX_UPDATED', 'PAYOUTS_UPDATED'].includes(payload?.event)) {
            loadFundraisers(true);
            loadCampaignsList();
          }
        } catch (e) {}
      };
    } catch (e) {}

    const handleFocus = () => {
      loadFundraisers(true);
    };
    window.addEventListener('focus', handleFocus);

    return () => {
      if (socket) socket.close();
      window.removeEventListener('focus', handleFocus);
    };
  }, [appliedStartDate, appliedEndDate, statusFilter]);

  // Open Create Modal
  const handleOpenCreateModal = () => {
    if (!isSuperAdmin) return;
    setEditingFundraiser(null);
    setModalForm({
      name: '',
      email: '',
      phone: '',
      target_goal: '',
      start_date: '',
      status: 'ACTIVE',
      notes: '',
      assigned_campaigns: []
    });
    setFormMsg('');
    setCampaignSearch('');
    setPlatformFilter('ALL');
    setAssignmentFilter('ALL');
    setShowModal(true);
    loadCampaignsList();
  };

  // Open Edit Modal
  const handleOpenEditModal = (f) => {
    if (!isSuperAdmin) return;
    setEditingFundraiser(f);
    setModalForm({
      name: f.name || '',
      email: f.email || '',
      phone: f.phone || '',
      target_goal: f.target_goal || '',
      start_date: f.start_date !== 'N/A' ? f.start_date : '',
      status: f.status || 'ACTIVE',
      notes: f.notes || '',
      assigned_campaigns: (f.assigned_campaigns || []).map(c => ({
        campaign_name: c.campaign_name,
        code: c.code || 'ALL',
        platform: c.platform || 'ALL'
      }))
    });
    setFormMsg('');
    setCampaignSearch('');
    setPlatformFilter('ALL');
    setAssignmentFilter('ALL');
    setShowModal(true);
    loadCampaignsList();
  };

  // Toggle Campaign Assignment in Modal Form (Ensuring 1 campaign -> 1 fundraiser)
  const handleToggleCampaignAssignment = (camp) => {
    const isAssignedToOther = camp.is_assigned && camp.assigned_to?.fundraiser_id && (!editingFundraiser || camp.assigned_to.fundraiser_id !== editingFundraiser.id);
    
    if (isAssignedToOther) {
      setFormMsg(`⚠️ Campaign '${camp.campaign_name}' (Code: ${camp.code}) is already assigned to '${camp.assigned_to.fundraiser_name}'. A campaign can only belong to one fundraiser.`);
      return;
    }

    const exists = modalForm.assigned_campaigns.some(
      c => c.campaign_name.toLowerCase() === camp.campaign_name.toLowerCase() &&
           (c.code || 'ALL').toLowerCase() === (camp.code || 'ALL').toLowerCase()
    );

    if (exists) {
      setModalForm(prev => ({
        ...prev,
        assigned_campaigns: prev.assigned_campaigns.filter(
          c => !(c.campaign_name.toLowerCase() === camp.campaign_name.toLowerCase() &&
                 (c.code || 'ALL').toLowerCase() === (camp.code || 'ALL').toLowerCase())
        )
      }));
    } else {
      setModalForm(prev => ({
        ...prev,
        assigned_campaigns: [
          ...prev.assigned_campaigns,
          {
            campaign_name: camp.campaign_name,
            code: camp.code || 'ALL',
            platform: camp.platform || 'ALL'
          }
        ]
      }));
    }
  };

  // Submit Modal Form (Create / Update)
  const handleSubmitModal = (e) => {
    e.preventDefault();
    if (!isSuperAdmin) {
      setFormMsg('❌ Managing fundraisers is strictly restricted to Super Admin accounts.');
      return;
    }

    if (!modalForm.name.trim()) {
      setFormMsg('❌ Fundraiser name is required.');
      return;
    }

    setSubmitting(true);
    setFormMsg('');

    const payload = {
      user_role: user?.role,
      name: modalForm.name.trim(),
      email: modalForm.email.trim(),
      phone: modalForm.phone.trim(),
      target_goal: parseFloat(modalForm.target_goal || 0),
      start_date: modalForm.start_date || '',
      status: modalForm.status,
      notes: modalForm.notes,
      assigned_campaigns: modalForm.assigned_campaigns
    };

    const isEdit = !!editingFundraiser;
    const url = isEdit ? `${API_BASE_URL}/api/fundraisers/${editingFundraiser.id}` : `${API_BASE_URL}/api/fundraisers`;
    const method = isEdit ? 'PUT' : 'POST';

    fetch(url, {
      method: method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .then(r => r.json())
      .then(res => {
        setSubmitting(false);
        if (res.status === 'success') {
          setFormMsg(`✅ ${res.message}`);
          loadFundraisers(true);
          loadCampaignsList();
          setTimeout(() => {
            setShowModal(false);
            setFormMsg('');
          }, 1200);
        } else {
          setFormMsg(`❌ ${res.detail || 'Failed to save fundraiser.'}`);
        }
      })
      .catch(err => {
        setSubmitting(false);
        setFormMsg(`❌ Error: ${err.message}`);
      });
  };

  // Delete Fundraiser
  const handleDeleteFundraiser = (fid) => {
    if (!isSuperAdmin) return;
    setDeleting(true);

    fetch(`${API_BASE_URL}/api/fundraisers/${fid}?user_role=${user?.role}`, {
      method: 'DELETE'
    })
      .then(r => r.json())
      .then(res => {
        setDeleting(false);
        setDeleteConfirm(null);
        if (res.status === 'success') {
          loadFundraisers(true);
          loadCampaignsList();
          if (selectedFundraiserId === fid) {
            setSelectedFundraiserId(null);
            setDrilldownData(null);
          }
        }
      })
      .catch(err => {
        setDeleting(false);
        console.error('Error deleting fundraiser:', err);
      });
  };

  // Filter available campaigns in modal
  const filteredAvailableCampaigns = useMemo(() => {
    return availableCampaigns.filter(c => {
      const matchSearch = !campaignSearch || 
        c.campaign_name.toLowerCase().includes(campaignSearch.toLowerCase()) ||
        c.code.toLowerCase().includes(campaignSearch.toLowerCase()) ||
        c.heading.toLowerCase().includes(campaignSearch.toLowerCase()) ||
        c.country.toLowerCase().includes(campaignSearch.toLowerCase());
      
      const matchPlatform = platformFilter === 'ALL' || c.platform.toLowerCase() === platformFilter.toLowerCase();

      const isAssignedToOther = c.is_assigned && c.assigned_to?.fundraiser_id && (!editingFundraiser || c.assigned_to.fundraiser_id !== editingFundraiser.id);
      const isAssignedToThis = modalForm.assigned_campaigns.some(
        ac => ac.campaign_name.toLowerCase() === c.campaign_name.toLowerCase() &&
              (ac.code || 'ALL').toLowerCase() === (c.code || 'ALL').toLowerCase()
      );

      let matchAssignment = true;
      if (assignmentFilter === 'UNASSIGNED') {
        matchAssignment = !c.is_assigned || (editingFundraiser && c.assigned_to?.fundraiser_id === editingFundraiser.id);
      } else if (assignmentFilter === 'ASSIGNED_THIS') {
        matchAssignment = isAssignedToThis;
      }

      return matchSearch && matchPlatform && matchAssignment;
    });
  }, [availableCampaigns, campaignSearch, platformFilter, assignmentFilter, editingFundraiser, modalForm.assigned_campaigns]);

  // Filter fundraisers list for display
  const filteredFundraisers = useMemo(() => {
    const list = fundraisersData.fundraisers || [];
    return list.filter(f => {
      const matchSearch = !searchQuery || 
        f.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
        (f.email && f.email.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (f.assigned_campaigns || []).some(c => 
          c.campaign_name.toLowerCase().includes(searchQuery.toLowerCase()) ||
          (c.code && c.code.toLowerCase().includes(searchQuery.toLowerCase()))
        );
      return matchSearch;
    });
  }, [fundraisersData.fundraisers, searchQuery]);

  const summary = fundraisersData.summary || {};
  const isDateFiltered = !!(appliedStartDate || appliedEndDate);

  return (
    <div className="flex flex-col gap-6">
      
      {/* ── Top Header & Actions ─────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-4">
        <div>
          <h2 className="text-xl font-extrabold flex items-center gap-2" style={{ color: 'var(--text-main)' }}>
            <HeartHandshake className="w-6 h-6 text-cyan-500" /> Fundraiser Tracking &amp; Campaign Attribution
          </h2>
          <p className="text-xs font-medium mt-0.5" style={{ color: 'var(--text-muted)' }}>
            Attribution based on actual donor data timestamps with live date-range filtering (From Date X to Date Y).
          </p>
        </div>

        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            onClick={() => loadFundraisers(false)}
            disabled={refreshing}
            className="btn-secondary text-xs flex items-center gap-1.5 px-3 py-2"
            title="Refresh live metrics from database"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} /> Refresh Live
          </button>

          {isSuperAdmin && (
            <button
              onClick={handleOpenCreateModal}
              className="btn-primary text-xs flex items-center gap-1.5 shadow-lg shadow-cyan-500/20 px-4 py-2"
            >
              <PlusCircle className="w-4 h-4" /> Add Fundraiser
            </button>
          )}
        </div>
      </div>

      {/* ── KPI Summary Cards ────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Active Fundraisers */}
        <div className="glass-panel p-4 flex items-center gap-4 relative overflow-hidden">
          <div className="p-3 rounded-xl bg-cyan-500/10 text-cyan-500 border border-cyan-500/20">
            <Users className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              Active Fundraisers
            </div>
            <div className="text-2xl font-black mt-0.5" style={{ color: 'var(--text-main)' }}>
              {summary.total_fundraisers || 0}
            </div>
            <div className="text-[10px] text-cyan-500 font-semibold mt-0.5">
              {filteredFundraisers.filter(f => f.status === 'ACTIVE').length} currently active
            </div>
          </div>
        </div>

        {/* Card 2: Raised in Selected Date Window */}
        <div className="glass-panel p-4 flex items-center gap-4 relative overflow-hidden">
          <div className="p-3 rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">
            <DollarSign className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              {isDateFiltered ? 'Raised (Filtered Window)' : 'Raised (All-Time)'}
            </div>
            <div className="text-2xl font-black text-emerald-500 mt-0.5">
              £{(summary.total_raised_period || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className="text-[10px] font-semibold mt-0.5 truncate max-w-[200px]" style={{ color: 'var(--text-muted)' }}>
              {isDateFiltered ? `${appliedStartDate || 'Start'} to ${appliedEndDate || 'Present'}` : 'Since first donor gift'}
            </div>
          </div>
        </div>

        {/* Card 3: Total Lifetime Raised */}
        <div className="glass-panel p-4 flex items-center gap-4 relative overflow-hidden">
          <div className="p-3 rounded-xl bg-purple-500/10 text-purple-500 border border-purple-500/20">
            <TrendingUp className="w-5 h-5" />
          </div>
          <div>
            <div className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              All-Time Lifetime Raised
            </div>
            <div className="text-2xl font-black text-purple-500 mt-0.5">
              £{(summary.total_raised_all_time || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className="text-[10px] font-semibold mt-0.5" style={{ color: 'var(--text-muted)' }}>
              Across {summary.total_transactions || 0} total donations
            </div>
          </div>
        </div>

        {/* Card 4: Goal Achievement */}
        <div className="glass-panel p-4 flex items-center gap-4 relative overflow-hidden">
          <div className="p-3 rounded-xl bg-amber-500/10 text-amber-500 border border-amber-500/20">
            <Target className="w-5 h-5" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              Overall Goal Progress
            </div>
            <div className="text-2xl font-black text-amber-500 mt-0.5">
              {summary.overall_progress_pct || 0}%
            </div>
            <div className="w-full rounded-full h-1.5 mt-1.5 overflow-hidden" style={{ backgroundColor: 'var(--bg-card-inner)' }}>
              <div 
                className="bg-gradient-to-r from-amber-500 to-emerald-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${Math.min(summary.overall_progress_pct || 0, 100)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── Interactive Date Range Filter Toolbar ───────────────── */}
      <div className="glass-panel p-4 flex flex-col gap-3">
        
        {/* Row 1: Search, Status, and View Mode */}
        <div className="flex flex-col md:flex-row items-stretch md:items-center justify-between gap-3">
          <div className="flex items-center gap-3 flex-1 flex-wrap">
            {/* Search Box */}
            <div className="relative flex-1 min-w-[220px]">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search by fundraiser name or campaign..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full pl-9 pr-3 py-2 text-xs rounded-xl focus:outline-none"
                style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
              />
            </div>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={e => setStatusFilter(e.target.value)}
              className="px-3 py-2 text-xs rounded-xl focus:outline-none"
              style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
            >
              <option value="ALL">All Statuses</option>
              <option value="ACTIVE">Active Only</option>
              <option value="PAUSED">Paused</option>
              <option value="COMPLETED">Completed</option>
            </select>
          </div>

          {/* View Mode Toggle */}
          <div className="flex items-center gap-1.5 self-end md:self-auto">
            <button
              onClick={() => setViewMode('grid')}
              className={`p-2 rounded-xl transition-all ${viewMode === 'grid' ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
              title="Grid Cards View"
            >
              <LayoutGrid className="w-4 h-4" />
            </button>
            <button
              onClick={() => setViewMode('table')}
              className={`p-2 rounded-xl transition-all ${viewMode === 'table' ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
              title="Leaderboard Table View"
            >
              <List className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Row 2: Date Filters & Custom Date Range Inputs */}
        <div className="flex items-center justify-between flex-wrap gap-3 pt-3 border-t" style={{ borderColor: 'var(--border-glass)' }}>
          
          {/* Preset Buttons */}
          <div className="flex items-center gap-1.5 flex-wrap">
            <span className="text-xs font-bold flex items-center gap-1 mr-1" style={{ color: 'var(--text-muted)' }}>
              <Calendar className="w-3.5 h-3.5 text-cyan-500" /> Filter Period:
            </span>

            <button
              onClick={() => handleDatePresetChange('all')}
              className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                dateFilterMode === 'all' 
                  ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/30' 
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              All-Time (First Gift)
            </button>

            <button
              onClick={() => handleDatePresetChange('this_year')}
              className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                dateFilterMode === 'this_year' 
                  ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/30' 
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              This Year
            </button>

            <button
              onClick={() => handleDatePresetChange('last_year')}
              className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                dateFilterMode === 'last_year' 
                  ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/30' 
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              Last Year
            </button>

            <button
              onClick={() => handleDatePresetChange('last_30')}
              className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                dateFilterMode === 'last_30' 
                  ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/30' 
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              Last 30 Days
            </button>

            <button
              onClick={() => handleDatePresetChange('last_90')}
              className={`px-2.5 py-1 rounded-lg text-xs font-bold transition-all ${
                dateFilterMode === 'last_90' 
                  ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/30' 
                  : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'
              }`}
            >
              Last 90 Days
            </button>
          </div>

          {/* Manual Date Range Inputs (From Date X to Date Y) */}
          <form onSubmit={handleApplyCustomDateRange} className="flex items-center gap-2 flex-wrap">
            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-bold" style={{ color: 'var(--text-muted)' }}>From (X):</span>
              <input
                type="date"
                value={customStartDate}
                onChange={e => {
                  setCustomStartDate(e.target.value);
                  setDateFilterMode('custom');
                }}
                className="px-2 py-1 text-xs rounded-lg focus:outline-none"
                style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
              />
            </div>

            <div className="flex items-center gap-1.5">
              <span className="text-[11px] font-bold" style={{ color: 'var(--text-muted)' }}>To (Y):</span>
              <input
                type="date"
                value={customEndDate}
                onChange={e => {
                  setCustomEndDate(e.target.value);
                  setDateFilterMode('custom');
                }}
                className="px-2 py-1 text-xs rounded-lg focus:outline-none"
                style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
              />
            </div>

            <button
              type="submit"
              className="btn-primary text-xs px-3 py-1 shadow-sm"
            >
              Apply Filter
            </button>

            {isDateFiltered && (
              <button
                type="button"
                onClick={handleClearDateFilter}
                className="p-1 rounded-lg hover:bg-rose-500/10 text-rose-500 text-xs flex items-center gap-1 transition-colors"
                title="Clear date filter and view all-time"
              >
                <X className="w-3.5 h-3.5" /> Reset
              </button>
            )}
          </form>
        </div>

        {/* Active Filter Indicator Badge */}
        {isDateFiltered && (
          <div className="flex items-center gap-2 text-xs font-bold px-3 py-1.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 text-cyan-700 dark:text-cyan-300">
            <Clock className="w-3.5 h-3.5" />
            <span>Active Filter Window:</span>
            <span className="font-extrabold text-cyan-600 dark:text-cyan-400">
              {appliedStartDate || 'Beginning'} &rarr; {appliedEndDate || 'Latest'}
            </span>
            <span className="text-[11px] opacity-75">• Showing exact amount raised within this period</span>
          </div>
        )}
      </div>

      {/* ── Main Content: Grid / Table Views ─────────────────────── */}
      {loading ? (
        <div className="glass-panel p-12 text-center flex flex-col items-center justify-center gap-3">
          <RefreshCw className="w-8 h-8 text-cyan-500 animate-spin" />
          <p className="text-sm font-semibold" style={{ color: 'var(--text-main)' }}>Loading live fundraiser analytics...</p>
        </div>
      ) : filteredFundraisers.length === 0 ? (
        <div className="glass-panel p-12 text-center flex flex-col items-center justify-center gap-4">
          <div className="p-4 rounded-2xl bg-cyan-500/10 text-cyan-500 border border-cyan-500/20">
            <HeartHandshake className="w-10 h-10" />
          </div>
          <div>
            <h3 className="text-base font-bold" style={{ color: 'var(--text-main)' }}>No Fundraisers Found</h3>
            <p className="text-xs mt-1 max-w-md mx-auto" style={{ color: 'var(--text-muted)' }}>
              {searchQuery ? `No fundraisers match search "${searchQuery}".` : 'Create your first fundraiser and assign campaigns to start tracking live progress.'}
            </p>
          </div>
          {isSuperAdmin && (
            <button
              onClick={handleOpenCreateModal}
              className="btn-primary text-xs flex items-center gap-1.5 px-4 py-2"
            >
              <PlusCircle className="w-4 h-4" /> Create First Fundraiser
            </button>
          )}
        </div>
      ) : viewMode === 'grid' ? (
        /* ── Grid Cards View ─────────────────────────────────────── */
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-5">
          {filteredFundraisers.map(f => {
            const hasGoal = f.target_goal > 0;
            const progress = f.progress_percentage || 0;
            const isCompleted = progress >= 100;
            const firstDate = f.first_donation_date && f.first_donation_date !== 'N/A' ? f.first_donation_date : (f.start_date !== 'N/A' ? f.start_date : 'No donations yet');

            return (
              <div 
                key={f.id}
                className="glass-panel p-5 flex flex-col justify-between gap-4 transition-all duration-300 hover:border-cyan-500/30 hover:shadow-xl group relative overflow-hidden"
              >
                {/* Status Indicator Bar */}
                <div className={`absolute top-0 left-0 right-0 h-1 ${
                  f.status === 'ACTIVE' ? 'bg-cyan-500' : f.status === 'COMPLETED' ? 'bg-emerald-500' : 'bg-slate-500'
                }`} />

                {/* Card Top: Profile & Status */}
                <div>
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-center gap-3">
                      <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-500/20 to-blue-500/20 text-cyan-500 font-black flex items-center justify-center border border-cyan-500/30 text-sm">
                        {f.name.substring(0, 2).toUpperCase()}
                      </div>
                      <div>
                        <h4 className="text-sm font-extrabold group-hover:text-cyan-500 transition-colors" style={{ color: 'var(--text-main)' }}>
                          {f.name}
                        </h4>
                        <div className="text-[11px] flex items-center gap-2 mt-0.5" style={{ color: 'var(--text-muted)' }}>
                          {f.email ? <span>{f.email}</span> : null}
                          {f.phone ? <span>• {f.phone}</span> : null}
                        </div>
                      </div>
                    </div>

                    {/* Status Badge */}
                    <span className={`px-2 py-0.5 rounded-md text-[10px] font-black border ${
                      f.status === 'ACTIVE' 
                        ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30' 
                        : f.status === 'COMPLETED'
                        ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30'
                        : 'bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30'
                    }`}>
                      {f.status}
                    </span>
                  </div>

                  {/* ── Date Factor Prominent Banner ─────────────────── */}
                  <div 
                    className="mt-3.5 p-2.5 rounded-xl border flex items-center justify-between text-xs"
                    style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}
                  >
                    <div className="flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                      <Clock className="w-3.5 h-3.5 text-cyan-500 shrink-0" />
                      {isDateFiltered ? (
                        <span>Raised in window:</span>
                      ) : (
                        <span>Since first donation (<strong style={{ color: 'var(--text-main)' }}>{firstDate}</strong>):</span>
                      )}
                    </div>
                    <span className="font-extrabold text-emerald-600 dark:text-emerald-400 text-sm">
                      £{f.total_raised_period.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>

                  {/* Target Goal Progress */}
                  {hasGoal && (
                    <div className="mt-3.5">
                      <div className="flex items-center justify-between text-xs mb-1">
                        <span className="text-[11px] font-bold" style={{ color: 'var(--text-muted)' }}>
                          Target Goal: £{f.target_goal.toLocaleString()}
                        </span>
                        <span className={`text-xs font-black ${isCompleted ? 'text-emerald-500' : 'text-cyan-500'}`}>
                          {progress}%
                        </span>
                      </div>
                      <div className="w-full rounded-full h-2 overflow-hidden border" style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}>
                        <div 
                          className={`h-full rounded-full transition-all duration-500 ${
                            isCompleted 
                              ? 'bg-gradient-to-r from-emerald-500 to-teal-400' 
                              : 'bg-gradient-to-r from-cyan-500 to-blue-500'
                          }`}
                          style={{ width: `${Math.min(progress, 100)}%` }}
                        />
                      </div>
                    </div>
                  )}

                  {/* Metrics Grid */}
                  <div className="grid grid-cols-3 gap-2 mt-4 pt-3 border-t" style={{ borderColor: 'var(--border-glass)' }}>
                    <div className="text-center">
                      <div className="text-[10px] uppercase font-bold" style={{ color: 'var(--text-muted)' }}>Lifetime</div>
                      <div className="text-xs font-black mt-0.5 text-purple-600 dark:text-purple-400">
                        £{f.total_raised_all_time.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-[10px] uppercase font-bold" style={{ color: 'var(--text-muted)' }}>
                        {isDateFiltered ? 'Period Donors' : 'Donors'}
                      </div>
                      <div className="text-xs font-black mt-0.5" style={{ color: 'var(--text-main)' }}>
                        {isDateFiltered ? f.period_donors : f.total_donors}
                      </div>
                    </div>
                    <div className="text-center">
                      <div className="text-[10px] uppercase font-bold" style={{ color: 'var(--text-muted)' }}>Avg Gift</div>
                      <div className="text-xs font-black mt-0.5 text-cyan-600 dark:text-cyan-400">
                        £{f.avg_donation}
                      </div>
                    </div>
                  </div>

                  {/* Assigned Campaigns Badges */}
                  <div className="mt-3.5">
                    <div className="text-[10px] font-bold uppercase tracking-wider mb-1.5 flex items-center justify-between" style={{ color: 'var(--text-muted)' }}>
                      <span>Assigned Campaigns ({f.assigned_campaigns?.length || 0})</span>
                      {f.latest_donation_date && f.latest_donation_date !== 'N/A' && (
                        <span className="text-[9px] font-normal" style={{ color: 'var(--text-sub)' }}>
                          Latest: {f.latest_donation_date}
                        </span>
                      )}
                    </div>
                    <div className="flex flex-wrap gap-1.5 max-h-20 overflow-y-auto custom-scrollbar">
                      {(f.assigned_campaigns || []).length === 0 ? (
                        <span className="text-[11px] italic" style={{ color: 'var(--text-sub)' }}>No campaigns assigned yet.</span>
                      ) : (
                        (f.assigned_campaigns || []).map((c, idx) => (
                          <span 
                            key={idx}
                            className="inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[10px] font-bold bg-cyan-500/10 text-cyan-600 dark:text-cyan-300 border border-cyan-500/20 truncate max-w-[200px]"
                            title={`${c.campaign_name} [Code: ${c.code || 'ALL'}]`}
                          >
                            <span className="truncate">{c.campaign_name}</span>
                            {c.code && c.code !== 'ALL' && (
                              <span className="px-1 rounded bg-cyan-500/20 text-cyan-700 dark:text-cyan-200 text-[9px] font-black shrink-0">
                                {c.code}
                              </span>
                            )}
                          </span>
                        ))
                      )}
                    </div>
                  </div>
                </div>

                {/* Card Footer Actions */}
                <div className="flex items-center justify-between pt-3 border-t mt-2" style={{ borderColor: 'var(--border-glass)' }}>
                  <button
                    onClick={() => {
                      setSelectedFundraiserId(f.id);
                      setDrilldownStartDate(appliedStartDate);
                      setDrilldownEndDate(appliedEndDate);
                      loadDrilldown(f.id, appliedStartDate, appliedEndDate);
                    }}
                    className="text-xs font-bold text-cyan-600 dark:text-cyan-400 hover:text-cyan-500 flex items-center gap-1 transition-colors"
                  >
                    <BarChart3 className="w-3.5 h-3.5" /> Campaign Breakdown <ArrowUpRight className="w-3 h-3" />
                  </button>

                  {isSuperAdmin && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleOpenEditModal(f)}
                        className="p-1.5 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700/40 text-slate-400 hover:text-cyan-500 transition-colors"
                        title="Edit Fundraiser &amp; Campaigns"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(f)}
                        className="p-1.5 rounded-lg hover:bg-rose-500/10 text-slate-400 hover:text-rose-500 transition-colors"
                        title="Delete Fundraiser"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        /* ── Table View ─────────────────────────────────────────── */
        <div className="glass-panel overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b" style={{ borderColor: 'var(--border-glass)', backgroundColor: 'var(--table-header-bg)' }}>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Fundraiser</th>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>First Gift Date</th>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                    {isDateFiltered ? 'Period Raised' : 'Total Raised'}
                  </th>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Lifetime Raised</th>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Target Goal</th>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Progress</th>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Donors</th>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Assigned Campaigns</th>
                  <th className="py-3 px-4 font-bold uppercase tracking-wider text-right" style={{ color: 'var(--text-muted)' }}>Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: 'var(--border-glass)' }}>
                {filteredFundraisers.map(f => (
                  <tr key={f.id} className="hover:bg-slate-200/40 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-3 px-4 font-bold" style={{ color: 'var(--text-main)' }}>
                      <div className="flex items-center gap-2.5">
                        <div className="w-7 h-7 rounded-lg bg-cyan-500/20 text-cyan-500 font-bold flex items-center justify-center text-xs">
                          {f.name.substring(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <div>{f.name}</div>
                          <div className="text-[10px] font-normal" style={{ color: 'var(--text-sub)' }}>{f.email || 'No email'}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-3 px-4 font-semibold" style={{ color: 'var(--text-muted)' }}>
                      {f.first_donation_date && f.first_donation_date !== 'N/A' ? f.first_donation_date : (f.start_date || 'N/A')}
                    </td>
                    <td className="py-3 px-4 font-extrabold text-emerald-600 dark:text-emerald-400">
                      £{f.total_raised_period.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-4 font-bold text-purple-600 dark:text-purple-400">
                      £{f.total_raised_all_time.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-3 px-4 font-semibold" style={{ color: 'var(--text-main)' }}>
                      {f.target_goal > 0 ? `£${f.target_goal.toLocaleString()}` : 'No Goal'}
                    </td>
                    <td className="py-3 px-4">
                      {f.target_goal > 0 ? (
                        <div className="flex items-center gap-2">
                          <div className="w-16 rounded-full h-1.5 overflow-hidden" style={{ backgroundColor: 'var(--bg-card-inner)' }}>
                            <div 
                              className="bg-cyan-500 h-full rounded-full"
                              style={{ width: `${Math.min(f.progress_percentage, 100)}%` }}
                            />
                          </div>
                          <span className="font-bold text-[11px] text-cyan-600 dark:text-cyan-400">{f.progress_percentage}%</span>
                        </div>
                      ) : (
                        <span className="text-[11px]" style={{ color: 'var(--text-sub)' }}>—</span>
                      )}
                    </td>
                    <td className="py-3 px-4 font-semibold" style={{ color: 'var(--text-main)' }}>
                      {isDateFiltered ? `${f.period_donors} (in window)` : f.total_donors}
                    </td>
                    <td className="py-3 px-4">
                      <div className="flex flex-wrap gap-1 max-w-[220px]">
                        {(f.assigned_campaigns || []).slice(0, 2).map((c, i) => (
                          <span key={i} className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-cyan-500/10 text-cyan-600 dark:text-cyan-300 border border-cyan-500/20 truncate max-w-[120px]">
                            {c.campaign_name}
                          </span>
                        ))}
                        {(f.assigned_campaigns || []).length > 2 && (
                          <span className="text-[10px] font-bold self-center" style={{ color: 'var(--text-sub)' }}>
                            +{f.assigned_campaigns.length - 2} more
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-3 px-4 text-right">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => {
                            setSelectedFundraiserId(f.id);
                            setDrilldownStartDate(appliedStartDate);
                            setDrilldownEndDate(appliedEndDate);
                            loadDrilldown(f.id, appliedStartDate, appliedEndDate);
                          }}
                          className="p-1 rounded bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-500 transition-colors"
                          title="View Drilldown"
                        >
                          <Eye className="w-3.5 h-3.5" />
                        </button>
                        {isSuperAdmin && (
                          <>
                            <button
                              onClick={() => handleOpenEditModal(f)}
                              className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700/60 text-slate-400 hover:text-cyan-500 transition-colors"
                              title="Edit Fundraiser"
                            >
                              <Edit3 className="w-3.5 h-3.5" />
                            </button>
                            <button
                              onClick={() => setDeleteConfirm(f)}
                              className="p-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition-colors"
                              title="Delete Fundraiser"
                            >
                              <Trash2 className="w-3.5 h-3.5" />
                            </button>
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Super Admin: Create / Edit Modal ─────────────────────── */}
      {showModal && isSuperAdmin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div 
            className="glass-panel w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl rounded-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200 border"
            style={{ backgroundColor: 'var(--bg-card)', borderColor: 'var(--border-glass)', color: 'var(--text-main)' }}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between p-5 border-b" style={{ borderColor: 'var(--border-glass)' }}>
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-cyan-500/15 text-cyan-500">
                  <HeartHandshake className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="text-base font-extrabold" style={{ color: 'var(--text-main)' }}>
                    {editingFundraiser ? `Edit Fundraiser: ${editingFundraiser.name}` : 'Create New Fundraiser'}
                  </h3>
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                    Assign campaigns and codes. A campaign can only be assigned to one fundraiser.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-5 custom-scrollbar flex flex-col gap-4">
              {formMsg && (
                <div className={`p-3 rounded-xl text-xs font-bold border ${
                  formMsg.startsWith('✅') ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30'
                }`}>
                  {formMsg}
                </div>
              )}

              <form onSubmit={handleSubmitModal} id="fundraiser-form" className="flex flex-col gap-4">
                {/* Row 1: Name & Target Goal */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                      Fundraiser Name *
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Kamrul, Team Alpha, Fatima"
                      value={modalForm.name}
                      onChange={e => setModalForm(prev => ({ ...prev, name: e.target.value }))}
                      className="w-full rounded-xl px-3 py-2 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                      Target Fundraising Goal (£)
                    </label>
                    <input
                      type="number"
                      min="0"
                      step="100"
                      placeholder="e.g. 50000"
                      value={modalForm.target_goal}
                      onChange={e => setModalForm(prev => ({ ...prev, target_goal: e.target.value }))}
                      className="w-full rounded-xl px-3 py-2 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    />
                  </div>
                </div>

                {/* Row 2: Status & Optional Manual Start Date */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                      Status
                    </label>
                    <select
                      value={modalForm.status}
                      onChange={e => setModalForm(prev => ({ ...prev, status: e.target.value }))}
                      className="w-full rounded-xl px-3 py-2 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    >
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="PAUSED">PAUSED</option>
                      <option value="COMPLETED">COMPLETED</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                      <Calendar className="w-3.5 h-3.5 inline mr-1 text-cyan-500" /> Manual Start Date (Optional)
                    </label>
                    <input
                      type="date"
                      value={modalForm.start_date}
                      onChange={e => setModalForm(prev => ({ ...prev, start_date: e.target.value }))}
                      className="w-full rounded-xl px-3 py-2 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    />
                    <span className="text-[10px] block mt-0.5" style={{ color: 'var(--text-sub)' }}>
                      Defaults automatically to the earliest donation date in dataset.
                    </span>
                  </div>
                </div>

                {/* Row 3: Email & Phone (Optional) */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                      Contact Email (Optional)
                    </label>
                    <input
                      type="email"
                      placeholder="fundraiser@example.com"
                      value={modalForm.email}
                      onChange={e => setModalForm(prev => ({ ...prev, email: e.target.value }))}
                      className="w-full rounded-xl px-3 py-2 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    />
                  </div>

                  <div>
                    <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                      Contact Phone (Optional)
                    </label>
                    <input
                      type="text"
                      placeholder="+44 7123 456789"
                      value={modalForm.phone}
                      onChange={e => setModalForm(prev => ({ ...prev, phone: e.target.value }))}
                      className="w-full rounded-xl px-3 py-2 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    />
                  </div>
                </div>

                {/* ── Campaign & Code Assignment Section ──────────────── */}
                <div className="mt-2 border-t pt-4" style={{ borderColor: 'var(--border-glass)' }}>
                  <div className="flex items-center justify-between mb-2">
                    <div>
                      <label className="block text-xs font-extrabold flex items-center gap-1.5" style={{ color: 'var(--text-main)' }}>
                        <Layers className="w-4 h-4 text-cyan-500" /> Assign Campaigns &amp; Multi-Codes *
                      </label>
                      <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                        Select the campaigns belonging to this fundraiser ({modalForm.assigned_campaigns.length} assigned)
                      </p>
                    </div>
                  </div>

                  {/* Selected Badges */}
                  {modalForm.assigned_campaigns.length > 0 && (
                    <div 
                      className="p-3 rounded-xl border mb-3 flex flex-wrap gap-1.5 max-h-28 overflow-y-auto custom-scrollbar"
                      style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}
                    >
                      {modalForm.assigned_campaigns.map((c, i) => (
                        <span 
                          key={i}
                          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border border-cyan-500/30"
                        >
                          <span className="truncate max-w-[200px]">{c.campaign_name}</span>
                          <span className="px-1 rounded bg-cyan-500/25 text-cyan-900 dark:text-white text-[9px] font-black">
                            {c.code || 'ALL'}
                          </span>
                          <button
                            type="button"
                            onClick={() => handleToggleCampaignAssignment(c)}
                            className="hover:text-rose-500 ml-0.5"
                          >
                            <X className="w-3 h-3" />
                          </button>
                        </span>
                      ))}
                    </div>
                  )}

                  {/* Search, Platform Filter, and Assignment Filter Toolbar */}
                  <div className="flex items-center gap-2 mb-2 flex-wrap">
                    <div className="relative flex-1 min-w-[180px]">
                      <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type="text"
                        placeholder="Search available campaigns..."
                        value={campaignSearch}
                        onChange={e => setCampaignSearch(e.target.value)}
                        className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg focus:outline-none"
                        style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                      />
                    </div>

                    <select
                      value={platformFilter}
                      onChange={e => setPlatformFilter(e.target.value)}
                      className="px-2.5 py-1.5 text-xs rounded-lg focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    >
                      <option value="ALL">All Platforms</option>
                      <option value="LaunchGood">LaunchGood</option>
                      <option value="GiveBright">GiveBright</option>
                      <option value="Paysuite">Paysuite</option>
                      <option value="Rethink Website">Rethink Website</option>
                    </select>

                    <select
                      value={assignmentFilter}
                      onChange={e => setAssignmentFilter(e.target.value)}
                      className="px-2.5 py-1.5 text-xs rounded-lg focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    >
                      <option value="ALL">All Campaigns</option>
                      <option value="UNASSIGNED">Unassigned Only</option>
                      <option value="ASSIGNED_THIS">Assigned to this Fundraiser</option>
                    </select>
                  </div>

                  {/* Available Campaigns Multi-Select List */}
                  <div 
                    className="border rounded-xl p-2 max-h-48 overflow-y-auto custom-scrollbar flex flex-col gap-1"
                    style={{ borderColor: 'var(--border-glass)', backgroundColor: 'var(--bg-card-inner)' }}
                  >
                    {filteredAvailableCampaigns.length === 0 ? (
                      <div className="text-center py-4 text-xs" style={{ color: 'var(--text-sub)' }}>
                        No matching campaigns found.
                      </div>
                    ) : (
                      filteredAvailableCampaigns.map((camp, idx) => {
                        const isAssignedToThis = modalForm.assigned_campaigns.some(
                          c => c.campaign_name.toLowerCase() === camp.campaign_name.toLowerCase() &&
                               (c.code || 'ALL').toLowerCase() === (camp.code || 'ALL').toLowerCase()
                        );
                        const isAssignedToOther = camp.is_assigned && camp.assigned_to?.fundraiser_id && (!editingFundraiser || camp.assigned_to.fundraiser_id !== editingFundraiser.id);

                        return (
                          <div
                            key={idx}
                            onClick={() => !isAssignedToOther && handleToggleCampaignAssignment(camp)}
                            className={`p-2 rounded-lg text-xs flex items-center justify-between gap-2 transition-colors ${
                              isAssignedToOther 
                                ? 'opacity-60 cursor-not-allowed bg-slate-500/5' 
                                : isAssignedToThis
                                ? 'bg-cyan-500/20 text-cyan-800 dark:text-cyan-200 border border-cyan-500/40 font-bold cursor-pointer'
                                : 'hover:bg-slate-200/60 dark:hover:bg-slate-800/60 border border-transparent cursor-pointer'
                            }`}
                            style={{ color: isAssignedToThis ? undefined : 'var(--text-main)' }}
                            title={isAssignedToOther ? `Already assigned to ${camp.assigned_to?.fundraiser_name}` : undefined}
                          >
                            <div className="flex items-center gap-2 min-w-0">
                              <div className={`w-4 h-4 rounded flex items-center justify-center text-[10px] font-bold shrink-0 ${
                                isAssignedToOther 
                                  ? 'bg-amber-500/20 text-amber-600 border border-amber-500/30'
                                  : isAssignedToThis 
                                  ? 'bg-cyan-500 text-white' 
                                  : 'border border-slate-400'
                              }`}>
                                {isAssignedToOther ? <Lock className="w-2.5 h-2.5" /> : isAssignedToThis ? <Check className="w-3 h-3 stroke-[3]" /> : null}
                              </div>
                              <div className="truncate">
                                <span className="font-semibold">{camp.campaign_name}</span>
                                <span 
                                  className="ml-2 px-1.5 py-0.5 rounded text-[10px] font-mono border"
                                  style={{ backgroundColor: 'var(--bg-card)', color: 'var(--accent-cyan)', borderColor: 'var(--border-glass)' }}
                                >
                                  {camp.code}
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              {isAssignedToOther && (
                                <span className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 flex items-center gap-1">
                                  <Lock className="w-2.5 h-2.5" /> {camp.assigned_to?.fundraiser_name}
                                </span>
                              )}
                              <span className="text-[10px]" style={{ color: 'var(--text-sub)' }}>
                                {camp.platform} • {camp.heading}
                              </span>
                            </div>
                          </div>
                        );
                      })
                    )}
                  </div>
                </div>
              </form>
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t flex items-center justify-end gap-3" style={{ borderColor: 'var(--border-glass)' }}>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="btn-secondary text-xs px-4 py-2"
              >
                Cancel
              </button>
              <button
                type="submit"
                form="fundraiser-form"
                disabled={submitting}
                className="btn-primary text-xs flex items-center gap-1.5 px-5 py-2 shadow-lg shadow-cyan-500/20"
              >
                {submitting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                {editingFundraiser ? 'Save Changes' : 'Create Fundraiser'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Super Admin: Delete Confirmation Modal ──────────────── */}
      {deleteConfirm && isSuperAdmin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div 
            className="glass-panel max-w-md w-full p-6 rounded-2xl border shadow-2xl animate-in zoom-in-95"
            style={{ backgroundColor: 'var(--bg-card)', borderColor: 'rgba(244,63,94,0.3)', color: 'var(--text-main)' }}
          >
            <div className="flex items-center gap-3 text-rose-500 mb-3">
              <ShieldAlert className="w-6 h-6" />
              <h3 className="text-base font-extrabold">Confirm Delete Fundraiser</h3>
            </div>
            <p className="text-xs" style={{ color: 'var(--text-main)' }}>
              Are you sure you want to delete fundraiser <strong style={{ color: 'var(--text-main)' }}>"{deleteConfirm.name}"</strong>?
            </p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--text-sub)' }}>
              This will remove the fundraiser profile and all campaign assignments. Underlying donor transactions will not be deleted.
            </p>
            <div className="flex items-center justify-end gap-3 mt-6">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="btn-secondary text-xs px-4 py-2"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteFundraiser(deleteConfirm.id)}
                disabled={deleting}
                className="px-4 py-2 rounded-xl text-xs font-bold bg-rose-500 hover:bg-rose-600 text-white transition-colors flex items-center gap-1.5 shadow-lg shadow-rose-500/20"
              >
                {deleting ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Trash2 className="w-3.5 h-3.5" />}
                Delete Permanently
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── Drilldown Drawer: Campaign Breakdown & Donor Log ─────── */}
      {selectedFundraiserId && (
        <div className="fixed inset-0 z-50 flex justify-end bg-black/60 backdrop-blur-sm animate-in fade-in">
          <div 
            className="w-full max-w-3xl h-full glass-panel border-l shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-300 rounded-none" 
            style={{ backgroundColor: 'var(--drawer-bg)', borderColor: 'var(--border-glass)', color: 'var(--text-main)' }}
          >
            
            {/* Drawer Header */}
            <div className="p-5 border-b flex items-center justify-between gap-4" style={{ borderColor: 'var(--border-glass)' }}>
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-xl bg-cyan-500/20 text-cyan-500 font-black flex items-center justify-center text-sm border border-cyan-500/30">
                  {drilldownData?.fundraiser?.name?.substring(0, 2).toUpperCase() || 'FR'}
                </div>
                <div>
                  <h3 className="text-base font-extrabold" style={{ color: 'var(--text-main)' }}>
                    {drilldownData?.fundraiser?.name || 'Fundraiser Performance'}
                  </h3>
                  <div className="text-xs flex items-center gap-2 flex-wrap" style={{ color: 'var(--text-muted)' }}>
                    <span>First Gift: <strong>{drilldownData?.fundraiser?.first_donation_date || drilldownData?.fundraiser?.start_date || 'N/A'}</strong></span>
                    {drilldownData?.fundraiser?.latest_donation_date && drilldownData?.fundraiser?.latest_donation_date !== 'N/A' && (
                      <span>• Latest: <strong>{drilldownData?.fundraiser?.latest_donation_date}</strong></span>
                    )}
                    <span>• Goal: £{drilldownData?.fundraiser?.target_goal?.toLocaleString() || '0'}</span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => {
                  setSelectedFundraiserId(null);
                  setDrilldownData(null);
                }}
                className="p-2 rounded-xl text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Drawer Filter Sub-bar */}
            <div className="p-3 border-b flex items-center justify-between gap-3 flex-wrap text-xs" style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}>
              <div className="flex items-center gap-2 flex-wrap">
                <span className="font-bold flex items-center gap-1" style={{ color: 'var(--text-muted)' }}>
                  <Calendar className="w-3.5 h-3.5 text-cyan-500" /> Filter Drilldown Period:
                </span>
                <input
                  type="date"
                  value={drilldownStartDate}
                  onChange={e => setDrilldownStartDate(e.target.value)}
                  className="px-2 py-1 text-xs rounded-lg focus:outline-none"
                  style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                />
                <span style={{ color: 'var(--text-sub)' }}>&rarr;</span>
                <input
                  type="date"
                  value={drilldownEndDate}
                  onChange={e => setDrilldownEndDate(e.target.value)}
                  className="px-2 py-1 text-xs rounded-lg focus:outline-none"
                  style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                />
                <button
                  onClick={() => loadDrilldown(selectedFundraiserId, drilldownStartDate, drilldownEndDate)}
                  className="btn-primary text-xs px-2.5 py-1"
                >
                  Apply
                </button>
                {(drilldownStartDate || drilldownEndDate) && (
                  <button
                    onClick={() => {
                      setDrilldownStartDate('');
                      setDrilldownEndDate('');
                      loadDrilldown(selectedFundraiserId, '', '');
                    }}
                    className="text-rose-500 font-bold hover:underline ml-1"
                  >
                    Reset
                  </button>
                )}
              </div>

              <div className="font-extrabold text-emerald-600 dark:text-emerald-400">
                {(drilldownStartDate || drilldownEndDate) ? (
                  <span>Period Raised: £{drilldownData?.fundraiser?.total_raised_period?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                ) : (
                  <span>All-Time: £{drilldownData?.fundraiser?.total_raised_all_time?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                )}
              </div>
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto p-5 custom-scrollbar flex flex-col gap-6">
              {loadingDrilldown ? (
                <div className="text-center py-12 flex flex-col items-center justify-center gap-3">
                  <RefreshCw className="w-8 h-8 text-cyan-500 animate-spin" />
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Loading campaign breakdown...</p>
                </div>
              ) : (
                <>
                  {/* Campaign Breakdown Table */}
                  <div>
                    <h4 className="text-xs font-extrabold uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                      <BarChart3 className="w-4 h-4 text-cyan-500" /> Assigned Campaign Performance
                    </h4>
                    <div className="border rounded-xl overflow-hidden" style={{ borderColor: 'var(--border-glass)' }}>
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b" style={{ backgroundColor: 'var(--table-header-bg)', borderColor: 'var(--border-glass)' }}>
                            <th className="py-2.5 px-3 font-bold" style={{ color: 'var(--text-muted)' }}>Campaign</th>
                            <th className="py-2.5 px-3 font-bold" style={{ color: 'var(--text-muted)' }}>Code</th>
                            <th className="py-2.5 px-3 font-bold" style={{ color: 'var(--text-muted)' }}>Category</th>
                            <th className="py-2.5 px-3 font-bold text-right" style={{ color: 'var(--text-muted)' }}>
                              {(drilldownStartDate || drilldownEndDate) ? 'Period Raised' : 'Gross Raised'}
                            </th>
                            <th className="py-2.5 px-3 font-bold text-right" style={{ color: 'var(--text-muted)' }}>Donors</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y" style={{ borderColor: 'var(--border-glass)' }}>
                          {(drilldownData?.campaign_breakdown || []).length === 0 ? (
                            <tr>
                              <td colSpan={5} className="py-4 text-center" style={{ color: 'var(--text-sub)' }}>
                                No donation activity recorded for assigned campaigns yet.
                              </td>
                            </tr>
                          ) : (
                            drilldownData.campaign_breakdown.map((cb, i) => (
                              <tr key={i} className="hover:bg-slate-200/40 dark:hover:bg-slate-800/40 transition-colors">
                                <td className="py-2.5 px-3 font-bold max-w-[200px] truncate" style={{ color: 'var(--text-main)' }} title={cb.campaign_name}>
                                  {cb.campaign_name}
                                </td>
                                <td className="py-2.5 px-3 font-mono text-cyan-600 dark:text-cyan-400 font-bold text-[11px]">
                                  {cb.code}
                                </td>
                                <td className="py-2.5 px-3 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                                  {cb.heading}
                                </td>
                                <td className="py-2.5 px-3 font-extrabold text-emerald-600 dark:text-emerald-400 text-right">
                                  £{cb.gross_raised.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </td>
                                <td className="py-2.5 px-3 text-right font-semibold" style={{ color: 'var(--text-main)' }}>
                                  {cb.total_donors}
                                </td>
                              </tr>
                            ))
                          )}
                        </tbody>
                      </table>
                    </div>
                  </div>

                  {/* Monthly Timeline */}
                  {(drilldownData?.monthly_timeline || []).length > 0 && (
                    <div>
                      <h4 className="text-xs font-extrabold uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                        <TrendingUp className="w-4 h-4 text-purple-500" /> Monthly Growth Breakdown
                      </h4>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        {drilldownData.monthly_timeline.map((m, i) => (
                          <div 
                            key={i} 
                            className="p-2.5 rounded-xl border text-center transition-all"
                            style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}
                          >
                            <div className="text-[10px] font-bold uppercase" style={{ color: 'var(--text-sub)' }}>{m.month}</div>
                            <div className="text-xs font-black text-purple-600 dark:text-purple-400 mt-0.5">
                              £{m.amount.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Recent Donations Log */}
                  <div>
                    <h4 className="text-xs font-extrabold uppercase tracking-wider mb-3 flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                      <Clock className="w-4 h-4 text-cyan-500" /> Recent Transactions ({drilldownData?.recent_transactions?.length || 0})
                    </h4>
                    <div className="border rounded-xl overflow-hidden max-h-60 overflow-y-auto custom-scrollbar" style={{ borderColor: 'var(--border-glass)' }}>
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b" style={{ backgroundColor: 'var(--table-header-bg)', borderColor: 'var(--border-glass)' }}>
                            <th className="py-2 px-3 font-bold" style={{ color: 'var(--text-muted)' }}>Date</th>
                            <th className="py-2 px-3 font-bold" style={{ color: 'var(--text-muted)' }}>Donor</th>
                            <th className="py-2 px-3 font-bold" style={{ color: 'var(--text-muted)' }}>Campaign</th>
                            <th className="py-2 px-3 font-bold text-right" style={{ color: 'var(--text-muted)' }}>Amount</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y" style={{ borderColor: 'var(--border-glass)' }}>
                          {(drilldownData?.recent_transactions || []).map((tx, i) => (
                            <tr key={i} className="hover:bg-slate-200/40 dark:hover:bg-slate-800/40 transition-colors">
                              <td className="py-2 px-3 text-[11px]" style={{ color: 'var(--text-sub)' }}>{tx.date}</td>
                              <td className="py-2 px-3 font-bold" style={{ color: 'var(--text-main)' }}>{tx.donor_name}</td>
                              <td className="py-2 px-3 truncate max-w-[150px]" style={{ color: 'var(--text-muted)' }}>{tx.campaign_name}</td>
                              <td className="py-2 px-3 font-bold text-emerald-600 dark:text-emerald-400 text-right">£{tx.amount.toFixed(2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
