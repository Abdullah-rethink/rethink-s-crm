import React, { useEffect, useState, useMemo } from 'react';
import { 
  HeartHandshake, PlusCircle, Search, Filter, Calendar, Target, 
  TrendingUp, Users, DollarSign, Edit3, Trash2, Eye, X, Check, 
  RefreshCw, ChevronRight, BarChart3, Clock, AlertCircle, ShieldAlert,
  Layers, CheckCircle2, Award, ArrowUpRight, LayoutGrid, List, Sparkles,
  Lock, ArrowRight, ExternalLink, Activity, ChevronLeft, ChevronsLeft,
  ChevronsRight, ArrowUpDown, ArrowDown, ArrowUp, SlidersHorizontal
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
  const [syncing, setSyncing] = useState(false);
  const [syncToast, setSyncToast] = useState(null);

  // Sync & Discover new fundraisers from live transaction data
  const handleSyncDiscovered = () => {
    setSyncing(true);
    fetch(`${API_BASE_URL}/api/fundraisers/sync-discovered`, { method: 'POST' })
      .then(r => r.json())
      .then(res => {
        setSyncing(false);
        setSyncToast(res.message || 'Fundraisers synced from data successfully.');
        loadFundraisers(true);
        loadCampaignsList();
        setTimeout(() => setSyncToast(null), 4500);
      })
      .catch(err => {
        setSyncing(false);
        setSyncToast('Sync error: ' + err.message);
        setTimeout(() => setSyncToast(null), 4500);
      });
  };

  // Filters & View State
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL');
  const [dateFilterMode, setDateFilterMode] = useState('all'); // 'all', 'this_year', 'last_year', 'last_30', 'last_90', 'custom'
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');
  const [appliedStartDate, setAppliedStartDate] = useState('');
  const [appliedEndDate, setAppliedEndDate] = useState('');
  const [viewMode, setViewMode] = useState('grid'); // 'grid' or 'table'

  // Pagination & Sorting State
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(24); // 12, 24, 48, 96, 'ALL'
  const [sortBy, setSortBy] = useState('period_raised'); // 'period_raised', 'all_time_raised', 'target_goal', 'progress', 'donors', 'txns', 'date', 'name'
  const [sortOrder, setSortOrder] = useState('desc'); // 'desc' or 'asc'
  const [jumpPageInput, setJumpPageInput] = useState('');

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
    setCurrentPage(1);
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
      // Keep custom inputs
    }
  };

  const handleApplyCustomDateRange = (e) => {
    if (e) e.preventDefault();
    setAppliedStartDate(customStartDate);
    setAppliedEndDate(customEndDate);
    setCurrentPage(1);
  };

  const handleClearDateFilter = () => {
    setDateFilterMode('all');
    setAppliedStartDate('');
    setAppliedEndDate('');
    setCustomStartDate('');
    setCustomEndDate('');
    setCurrentPage(1);
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

  // Toggle Campaign Assignment in Modal Form
  const handleToggleCampaignAssignment = (camp) => {
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
      
      const matchStatus = statusFilter === 'ALL' || f.status === statusFilter;
      return matchSearch && matchStatus;
    });
  }, [fundraisersData.fundraisers, searchQuery, statusFilter]);

  // Sort filtered fundraisers
  const sortedFundraisers = useMemo(() => {
    return [...filteredFundraisers].sort((a, b) => {
      let valA, valB;
      if (sortBy === 'period_raised') {
        valA = a.total_raised != null ? a.total_raised : (a.total_raised_period || 0);
        valB = b.total_raised != null ? b.total_raised : (b.total_raised_period || 0);
      } else if (sortBy === 'all_time_raised') {
        valA = a.all_time_raised != null ? a.all_time_raised : (a.total_raised_all_time || a.total_raised || 0);
        valB = b.all_time_raised != null ? b.all_time_raised : (b.total_raised_all_time || b.total_raised || 0);
      } else if (sortBy === 'target_goal') {
        valA = a.target_goal || 0;
        valB = b.target_goal || 0;
      } else if (sortBy === 'progress') {
        valA = a.progress_percentage || 0;
        valB = b.progress_percentage || 0;
      } else if (sortBy === 'donors') {
        valA = a.donor_count != null ? a.donor_count : (a.period_donors || a.total_donors || 0);
        valB = b.donor_count != null ? b.donor_count : (b.period_donors || b.total_donors || 0);
      } else if (sortBy === 'txns') {
        valA = a.donation_count != null ? a.donation_count : (a.period_transactions || a.total_transactions || 0);
        valB = b.donation_count != null ? b.donation_count : (b.period_transactions || b.total_transactions || 0);
      } else if (sortBy === 'name') {
        return sortOrder === 'asc' 
          ? a.name.localeCompare(b.name) 
          : b.name.localeCompare(a.name);
      } else if (sortBy === 'date') {
        valA = a.first_donation_date && a.first_donation_date !== 'N/A' ? a.first_donation_date : (a.start_date || '');
        valB = b.first_donation_date && b.first_donation_date !== 'N/A' ? b.first_donation_date : (b.start_date || '');
        return sortOrder === 'asc' 
          ? valA.localeCompare(valB) 
          : valB.localeCompare(valA);
      } else {
        valA = a.total_raised || 0;
        valB = b.total_raised || 0;
      }

      if (sortOrder === 'asc') {
        return valA > valB ? 1 : valA < valB ? -1 : 0;
      } else {
        return valA < valB ? 1 : valA > valB ? -1 : 0;
      }
    });
  }, [filteredFundraisers, sortBy, sortOrder]);

  // Pagination calculation
  const totalItems = sortedFundraisers.length;
  const isAllPages = pageSize === 'ALL';
  const effectivePageSize = isAllPages ? Math.max(1, totalItems) : Number(pageSize);
  const totalPages = isAllPages ? 1 : Math.max(1, Math.ceil(totalItems / effectivePageSize));

  // Auto-adjust page if current page exceeds total pages
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(totalPages);
    }
  }, [totalPages, currentPage]);

  const paginatedFundraisers = useMemo(() => {
    if (isAllPages) return sortedFundraisers;
    const startIndex = (currentPage - 1) * effectivePageSize;
    return sortedFundraisers.slice(startIndex, startIndex + effectivePageSize);
  }, [sortedFundraisers, currentPage, effectivePageSize, isAllPages]);

  const startItemIndex = totalItems === 0 ? 0 : isAllPages ? 1 : (currentPage - 1) * effectivePageSize + 1;
  const endItemIndex = isAllPages ? totalItems : Math.min(currentPage * effectivePageSize, totalItems);

  // Smart pagination range builder (e.g. 1, 2, 3 ... 10)
  const paginationRange = useMemo(() => {
    if (totalPages <= 7) {
      return Array.from({ length: totalPages }, (_, i) => i + 1);
    }
    const delta = 1;
    const range = [];
    const rangeWithDots = [];
    let l;

    for (let i = 1; i <= totalPages; i++) {
      if (i === 1 || i === totalPages || (i >= currentPage - delta && i <= currentPage + delta)) {
        range.push(i);
      }
    }

    for (let i of range) {
      if (l) {
        if (i - l === 2) {
          rangeWithDots.push(l + 1);
        } else if (i - l !== 1) {
          rangeWithDots.push('...');
        }
      }
      rangeWithDots.push(i);
      l = i;
    }
    return rangeWithDots;
  }, [totalPages, currentPage]);

  // Pagination Controls UI Bar
  const renderPaginationControls = (isTop = false) => {
    if (totalItems === 0) return null;

    return (
      <div 
        className={`flex flex-col sm:flex-row items-center justify-between gap-3 px-4 py-2.5 rounded-xl border ${
          isTop ? 'mb-1' : 'mt-2'
        }`}
        style={{
          backgroundColor: 'var(--bg-glass)',
          borderColor: 'var(--border-glass)',
          backdropFilter: 'blur(8px)'
        }}
      >
        {/* Left Side: Count & Page Size Selector */}
        <div className="flex items-center gap-3 flex-wrap justify-center sm:justify-start">
          <span className="text-xs font-bold" style={{ color: 'var(--text-muted)' }}>
            Showing <span className="font-extrabold text-cyan-600 dark:text-cyan-400">{startItemIndex}</span> - <span className="font-extrabold text-cyan-600 dark:text-cyan-400">{endItemIndex}</span> of <span className="font-extrabold" style={{ color: 'var(--text-main)' }}>{totalItems}</span> fundraisers
          </span>

          <div className="flex items-center gap-1.5 pl-3 border-l" style={{ borderColor: 'var(--border-glass)' }}>
            <span className="text-[11px] font-semibold" style={{ color: 'var(--text-sub)' }}>Show:</span>
            {[12, 24, 48, 96, 'ALL'].map(size => {
              const isActive = pageSize === size || (size === 'ALL' && pageSize === 'ALL');
              return (
                <button
                  key={size}
                  onClick={() => {
                    setPageSize(size);
                    setCurrentPage(1);
                  }}
                  className={`px-2 py-0.5 rounded text-[11px] font-bold transition-all ${
                    isActive
                      ? 'bg-cyan-500 text-white shadow-sm'
                      : 'hover:bg-slate-200 dark:hover:bg-slate-800'
                  }`}
                  style={{
                    color: isActive ? '#ffffff' : 'var(--text-muted)'
                  }}
                >
                  {size === 'ALL' ? 'All' : size}
                </button>
              );
            })}
          </div>
        </div>

        {/* Right Side: Page Navigation Buttons & Jump */}
        {!isAllPages && totalPages > 1 && (
          <div className="flex items-center gap-1.5 flex-wrap justify-center sm:justify-end">
            {/* First Page */}
            <button
              onClick={() => setCurrentPage(1)}
              disabled={currentPage === 1}
              className="p-1.5 rounded-lg border text-xs disabled:opacity-30 disabled:cursor-not-allowed hover:border-cyan-500/50 transition-colors"
              style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', borderColor: 'var(--input-border)' }}
              title="First Page"
            >
              <ChevronsLeft className="w-3.5 h-3.5" />
            </button>

            {/* Previous Page */}
            <button
              onClick={() => setCurrentPage(prev => Math.max(prev - 1, 1))}
              disabled={currentPage === 1}
              className="p-1.5 rounded-lg border text-xs disabled:opacity-30 disabled:cursor-not-allowed hover:border-cyan-500/50 transition-colors"
              style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', borderColor: 'var(--input-border)' }}
              title="Previous Page"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>

            {/* Numbered Page Buttons */}
            <div className="flex items-center gap-1">
              {paginationRange.map((page, idx) => {
                if (page === '...') {
                  return (
                    <span key={`dots-${idx}`} className="px-1.5 py-1 text-xs font-bold text-slate-400">
                      •••
                    </span>
                  );
                }
                const isActive = currentPage === page;
                return (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    className={`min-w-[28px] h-7 px-2 rounded-lg text-xs font-extrabold transition-all ${
                      isActive
                        ? 'bg-gradient-to-r from-cyan-500 to-blue-600 text-white shadow-sm shadow-cyan-500/30'
                        : 'border hover:border-cyan-500/50'
                    }`}
                    style={{
                      backgroundColor: isActive ? undefined : 'var(--input-bg)',
                      color: isActive ? '#ffffff' : 'var(--text-main)',
                      borderColor: isActive ? 'transparent' : 'var(--input-border)'
                    }}
                  >
                    {page}
                  </button>
                );
              })}
            </div>

            {/* Next Page */}
            <button
              onClick={() => setCurrentPage(prev => Math.min(prev + 1, totalPages))}
              disabled={currentPage === totalPages}
              className="p-1.5 rounded-lg border text-xs disabled:opacity-30 disabled:cursor-not-allowed hover:border-cyan-500/50 transition-colors"
              style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', borderColor: 'var(--input-border)' }}
              title="Next Page"
            >
              <ChevronRight className="w-3.5 h-3.5" />
            </button>

            {/* Last Page */}
            <button
              onClick={() => setCurrentPage(totalPages)}
              disabled={currentPage === totalPages}
              className="p-1.5 rounded-lg border text-xs disabled:opacity-30 disabled:cursor-not-allowed hover:border-cyan-500/50 transition-colors"
              style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', borderColor: 'var(--input-border)' }}
              title="Last Page"
            >
              <ChevronsRight className="w-3.5 h-3.5" />
            </button>

            {/* Page Jump */}
            {totalPages > 3 && (
              <div className="flex items-center gap-1 pl-2 border-l" style={{ borderColor: 'var(--border-glass)' }}>
                <span className="text-[11px] font-semibold" style={{ color: 'var(--text-sub)' }}>Go to:</span>
                <input
                  type="number"
                  min="1"
                  max={totalPages}
                  placeholder={currentPage}
                  onKeyDown={e => {
                    if (e.key === 'Enter') {
                      const val = parseInt(e.target.value, 10);
                      if (!isNaN(val) && val >= 1 && val <= totalPages) {
                        setCurrentPage(val);
                        e.target.value = '';
                      }
                    }
                  }}
                  className="w-12 px-1.5 py-1 text-center text-xs rounded-lg border focus:outline-none focus:border-cyan-500"
                  style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', borderColor: 'var(--input-border)' }}
                />
              </div>
            )}
          </div>
        )}
      </div>
    );
  };

  const summary = fundraisersData.summary || {};
  const isDateFiltered = !!(appliedStartDate || appliedEndDate);

  return (
    <div className="flex flex-col gap-4">
      
      {/* ── Top Header & Actions ─────────────────────────────────── */}
      <div className="flex items-center justify-between flex-wrap gap-3 pb-1">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-cyan-500/20 to-blue-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-500 shadow-sm shrink-0">
            <HeartHandshake className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-lg font-black tracking-tight" style={{ color: 'var(--text-main)' }}>
                Fundraiser Tracking &amp; Campaign Attribution
              </h2>
              <span className="inline-flex items-center gap-1 text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border border-cyan-500/20">
                <span className="w-1.5 h-1.5 rounded-full bg-cyan-500 animate-pulse" /> Live Inception
              </span>
            </div>
            <p className="text-xs font-medium" style={{ color: 'var(--text-muted)' }}>
              Real-time campaign attribution based on actual donor data timestamps with custom Date X to Date Y window filtering.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {isSuperAdmin && (
            <button
              onClick={handleSyncDiscovered}
              disabled={syncing}
              className="btn-secondary text-xs flex items-center gap-1.5 px-3 py-1.5 border-cyan-500/30 text-cyan-600 dark:text-cyan-400 hover:bg-cyan-500/10"
              title="Scan donor records to auto-discover and link new fundraisers"
            >
              <Sparkles className={`w-3.5 h-3.5 ${syncing ? 'animate-spin' : 'text-cyan-500'}`} />
              {syncing ? 'Syncing Data...' : 'Sync from Data'}
            </button>
          )}

          <button
            onClick={() => loadFundraisers(false)}
            disabled={refreshing}
            className="btn-secondary text-xs flex items-center gap-1.5 px-3 py-1.5"
            title="Refresh live metrics from database"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${refreshing ? 'animate-spin' : ''}`} /> Refresh Live
          </button>

          {isSuperAdmin && (
            <button
              onClick={handleOpenCreateModal}
              className="btn-primary text-xs flex items-center gap-1.5 shadow-md shadow-cyan-500/20 px-3.5 py-1.5"
            >
              <PlusCircle className="w-3.5 h-3.5" /> Add Fundraiser
            </button>
          )}
        </div>
      </div>

      {/* ── Sync Notification Toast ───────────────────────────────── */}
      {syncToast && (
        <div className="glass-panel p-2.5 px-3.5 bg-gradient-to-r from-cyan-500/10 via-blue-500/10 to-transparent border border-cyan-500/30 flex items-center justify-between text-xs font-semibold text-cyan-700 dark:text-cyan-300">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-cyan-500 shrink-0" />
            <span>{syncToast}</span>
          </div>
          <button onClick={() => setSyncToast(null)} className="text-slate-400 hover:text-slate-200">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* ── KPI Summary Cards ────────────────────────────────────── */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5">
        {/* Card 1: Total Active Fundraisers */}
        <div className="glass-panel p-3.5 flex items-center gap-3.5 relative overflow-hidden border-l-4 border-l-cyan-500">
          <div className="p-2.5 rounded-xl bg-cyan-500/10 text-cyan-500 border border-cyan-500/20 shrink-0">
            <Users className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-extrabold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              Active Fundraisers
            </div>
            <div className="text-xl font-black mt-0.5 tracking-tight" style={{ color: 'var(--text-main)' }}>
              {summary.total_fundraisers || 0}
            </div>
            <div className="text-[10px] text-cyan-600 dark:text-cyan-400 font-semibold truncate">
              {filteredFundraisers.filter(f => f.status === 'ACTIVE').length} currently active
            </div>
          </div>
        </div>

        {/* Card 2: Raised in Selected Date Window */}
        <div className="glass-panel p-3.5 flex items-center gap-3.5 relative overflow-hidden border-l-4 border-l-emerald-500">
          <div className="p-2.5 rounded-xl bg-emerald-500/10 text-emerald-500 border border-emerald-500/20 shrink-0">
            <DollarSign className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-extrabold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              {isDateFiltered ? 'Raised (Filtered Window)' : 'Raised (All-Time)'}
            </div>
            <div className="text-xl font-black text-emerald-600 dark:text-emerald-400 mt-0.5 tracking-tight">
              £{(summary.total_raised_period || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className="text-[10px] font-semibold truncate" style={{ color: 'var(--text-muted)' }}>
              {isDateFiltered ? `${appliedStartDate || 'Start'} → ${appliedEndDate || 'Present'}` : 'Since first donor gift'}
            </div>
          </div>
        </div>

        {/* Card 3: Total Lifetime Raised */}
        <div className="glass-panel p-3.5 flex items-center gap-3.5 relative overflow-hidden border-l-4 border-l-purple-500">
          <div className="p-2.5 rounded-xl bg-purple-500/10 text-purple-500 border border-purple-500/20 shrink-0">
            <TrendingUp className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="text-[10px] font-extrabold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
              All-Time Lifetime Raised
            </div>
            <div className="text-xl font-black text-purple-600 dark:text-purple-400 mt-0.5 tracking-tight">
              £{(summary.total_raised_all_time || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
            </div>
            <div className="text-[10px] font-semibold truncate" style={{ color: 'var(--text-muted)' }}>
              Across {summary.total_transactions || 0} total donations
            </div>
          </div>
        </div>

        {/* Card 4: Goal Achievement */}
        <div className="glass-panel p-3.5 flex items-center gap-3.5 relative overflow-hidden border-l-4 border-l-amber-500">
          <div className="p-2.5 rounded-xl bg-amber-500/10 text-amber-500 border border-amber-500/20 shrink-0">
            <Target className="w-4 h-4" />
          </div>
          <div className="min-w-0 flex-1">
            <div className="flex items-center justify-between">
              <div className="text-[10px] font-extrabold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>
                Goal Progress
              </div>
              <span className="text-xs font-black text-amber-600 dark:text-amber-400">
                {summary.overall_progress_pct || 0}%
              </span>
            </div>
            <div className="text-lg font-black text-amber-600 dark:text-amber-400 mt-0.5">
              £{(summary.total_target_goal || 0).toLocaleString()} <span className="text-[10px] font-normal" style={{ color: 'var(--text-sub)' }}>target</span>
            </div>
            <div className="w-full rounded-full h-1.5 mt-1 overflow-hidden" style={{ backgroundColor: 'var(--bg-card-inner)' }}>
              <div 
                className="bg-gradient-to-r from-amber-500 to-emerald-500 h-full rounded-full transition-all duration-500"
                style={{ width: `${Math.min(summary.overall_progress_pct || 0, 100)}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      {/* ── Interactive Date Range Filter Toolbar ───────────────── */}
      <div className="glass-panel p-3.5 flex flex-col gap-2.5">
        
        {/* Row 1: Search, Status, Presets and View Mode */}
        <div className="flex flex-col lg:flex-row items-stretch lg:items-center justify-between gap-2.5">
          <div className="flex items-center gap-2 flex-1 flex-wrap">
            {/* Search Box */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="w-3.5 h-3.5 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
              <input
                type="text"
                placeholder="Search by fundraiser or campaign..."
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                className="w-full pl-8 pr-3 py-1.5 text-xs rounded-lg focus:outline-none"
                style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
              />
            </div>

            {/* Status Filter */}
            <select
              value={statusFilter}
              onChange={e => {
                setStatusFilter(e.target.value);
                setCurrentPage(1);
              }}
              className="px-2.5 py-1.5 text-xs rounded-lg focus:outline-none"
              style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
            >
              <option value="ALL">All Statuses</option>
              <option value="ACTIVE">Active Only</option>
              <option value="PAUSED">Paused</option>
              <option value="COMPLETED">Completed</option>
            </select>

            {/* Sort Filter */}
            <div className="flex items-center gap-1">
              <select
                value={sortBy}
                onChange={e => setSortBy(e.target.value)}
                className="px-2.5 py-1.5 text-xs rounded-lg focus:outline-none font-medium"
                style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
              >
                <option value="period_raised">{isDateFiltered ? 'Sort: Period Raised' : 'Sort: Total Raised'}</option>
                <option value="all_time_raised">Sort: Lifetime Raised</option>
                <option value="progress">Sort: Goal Progress %</option>
                <option value="target_goal">Sort: Target Goal</option>
                <option value="donors">Sort: Donor Count</option>
                <option value="txns">Sort: Transactions</option>
                <option value="name">Sort: Name (A-Z)</option>
                <option value="date">Sort: First Gift Date</option>
              </select>

              <button
                type="button"
                onClick={() => setSortOrder(prev => prev === 'desc' ? 'asc' : 'desc')}
                className="p-1.5 rounded-lg border hover:border-cyan-500/50 transition-colors"
                style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', borderColor: 'var(--input-border)' }}
                title={sortOrder === 'desc' ? 'Sort Descending (High to Low)' : 'Sort Ascending (Low to High)'}
              >
                {sortOrder === 'desc' ? <ArrowDown className="w-3.5 h-3.5 text-cyan-500" /> : <ArrowUp className="w-3.5 h-3.5 text-cyan-500" />}
              </button>
            </div>
          </div>

          {/* Preset Buttons */}
          <div className="flex items-center gap-1 flex-wrap">
            <span className="text-[11px] font-bold flex items-center gap-1 mr-1" style={{ color: 'var(--text-muted)' }}>
              <Calendar className="w-3 h-3 text-cyan-500" /> Period:
            </span>

            {[
              { id: 'all', label: 'All-Time (First Gift)' },
              { id: 'this_year', label: 'This Year' },
              { id: 'last_year', label: 'Last Year' },
              { id: 'last_30', label: 'Last 30 Days' },
              { id: 'last_90', label: 'Last 90 Days' }
            ].map(p => (
              <button
                key={p.id}
                onClick={() => handleDatePresetChange(p.id)}
                className={`px-2 py-1 rounded-md text-[11px] font-bold transition-all ${
                  dateFilterMode === p.id 
                    ? 'bg-cyan-500/20 text-cyan-600 dark:text-cyan-300 border border-cyan-500/30' 
                    : 'text-slate-500 hover:text-slate-700 dark:hover:text-slate-200'
                }`}
              >
                {p.label}
              </button>
            ))}

            {/* View Mode Toggle */}
            <div className="flex items-center gap-1 ml-2 pl-2 border-l" style={{ borderColor: 'var(--border-glass)' }}>
              <button
                onClick={() => setViewMode('grid')}
                className={`p-1.5 rounded-lg transition-all ${viewMode === 'grid' ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
                title="Grid Cards View"
              >
                <LayoutGrid className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => setViewMode('table')}
                className={`p-1.5 rounded-lg transition-all ${viewMode === 'table' ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/30' : 'text-slate-400 hover:text-slate-200'}`}
                title="Leaderboard Table View"
              >
                <List className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>

        {/* Row 2: Manual Date Range Inputs (From Date X to Date Y) */}
        <div className="flex items-center justify-between flex-wrap gap-2 pt-2 border-t" style={{ borderColor: 'var(--border-glass)' }}>
          <form onSubmit={handleApplyCustomDateRange} className="flex items-center gap-2 flex-wrap text-xs">
            <span className="text-[11px] font-bold" style={{ color: 'var(--text-muted)' }}>Custom Range:</span>
            
            <div className="flex items-center gap-1">
              <span className="text-[11px]" style={{ color: 'var(--text-sub)' }}>From (X):</span>
              <input
                type="date"
                value={customStartDate}
                onChange={e => {
                  setCustomStartDate(e.target.value);
                  setDateFilterMode('custom');
                }}
                className="px-2 py-1 text-xs rounded-md focus:outline-none"
                style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
              />
            </div>

            <div className="flex items-center gap-1">
              <span className="text-[11px]" style={{ color: 'var(--text-sub)' }}>To (Y):</span>
              <input
                type="date"
                value={customEndDate}
                onChange={e => {
                  setCustomEndDate(e.target.value);
                  setDateFilterMode('custom');
                }}
                className="px-2 py-1 text-xs rounded-md focus:outline-none"
                style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
              />
            </div>

            <button
              type="submit"
              className="btn-primary text-xs px-2.5 py-1 shadow-sm font-bold"
            >
              Apply Filter
            </button>

            {isDateFiltered && (
              <button
                type="button"
                onClick={handleClearDateFilter}
                className="px-2 py-1 rounded-md hover:bg-rose-500/10 text-rose-500 text-xs font-bold flex items-center gap-1 transition-colors"
                title="Clear date filter and view all-time"
              >
                <X className="w-3 h-3" /> Reset
              </button>
            )}
          </form>

          {/* Active Filter Indicator Badge */}
          {isDateFiltered && (
            <div className="flex items-center gap-1.5 text-[11px] font-bold px-2.5 py-1 rounded-lg bg-cyan-500/10 border border-cyan-500/20 text-cyan-700 dark:text-cyan-300">
              <Clock className="w-3 h-3" />
              <span>Window:</span>
              <span className="font-extrabold text-cyan-600 dark:text-cyan-400">
                {appliedStartDate || 'Beginning'} &rarr; {appliedEndDate || 'Latest'}
              </span>
            </div>
          )}
        </div>
      </div>

      {/* Top Pagination Controls */}
      {!loading && filteredFundraisers.length > 0 && renderPaginationControls(true)}

      {/* ── Main Content: Grid / Table Views ─────────────────────── */}
      {loading ? (
        <div className="glass-panel p-10 text-center flex flex-col items-center justify-center gap-2.5">
          <RefreshCw className="w-7 h-7 text-cyan-500 animate-spin" />
          <p className="text-xs font-semibold" style={{ color: 'var(--text-main)' }}>Loading live fundraiser analytics...</p>
        </div>
      ) : filteredFundraisers.length === 0 ? (
        <div className="glass-panel p-10 text-center flex flex-col items-center justify-center gap-3">
          <div className="p-3 rounded-2xl bg-cyan-500/10 text-cyan-500 border border-cyan-500/20">
            <HeartHandshake className="w-8 h-8" />
          </div>
          <div>
            <h3 className="text-sm font-bold" style={{ color: 'var(--text-main)' }}>No Fundraisers Found</h3>
            <p className="text-xs mt-0.5 max-w-md mx-auto" style={{ color: 'var(--text-muted)' }}>
              {searchQuery ? `No fundraisers match search "${searchQuery}".` : 'Create your first fundraiser and assign campaigns to start tracking live progress.'}
            </p>
          </div>
          {isSuperAdmin && (
            <button
              onClick={handleOpenCreateModal}
              className="btn-primary text-xs flex items-center gap-1.5 px-3.5 py-1.5"
            >
              <PlusCircle className="w-3.5 h-3.5" /> Create First Fundraiser
            </button>
          )}
        </div>
      ) : viewMode === 'grid' ? (
        /* ── Grid Cards View (Responsive 3/4 Column Layout) ───────── */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-3 2xl:grid-cols-4 gap-4">
          {paginatedFundraisers.map(f => {
            const hasGoal = f.target_goal > 0;
            const progress = f.progress_percentage || 0;
            const isCompleted = progress >= 100;
            const firstDate = f.first_donation_date && f.first_donation_date !== 'N/A' ? f.first_donation_date : (f.start_date !== 'N/A' ? f.start_date : 'No donations yet');

            return (
              <div 
                key={f.id}
                className="glass-panel p-4 flex flex-col justify-between gap-3 transition-all duration-300 hover:border-cyan-500/30 hover:shadow-lg group relative overflow-hidden"
              >
                {/* Status Indicator Bar */}
                <div className={`absolute top-0 left-0 right-0 h-1 ${
                  f.status === 'ACTIVE' ? 'bg-cyan-500' : f.status === 'COMPLETED' ? 'bg-emerald-500' : 'bg-slate-500'
                }`} />

                {/* Card Top: Profile & Status */}
                <div>
                  <div className="flex items-start justify-between gap-2.5">
                    <div className="flex items-center gap-2.5 min-w-0">
                      <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-cyan-500/20 to-blue-500/20 text-cyan-500 font-black flex items-center justify-center border border-cyan-500/30 text-xs shrink-0">
                        {f.name.substring(0, 2).toUpperCase()}
                      </div>
                      <div className="min-w-0">
                        <h4 className="text-xs font-black group-hover:text-cyan-500 transition-colors truncate" style={{ color: 'var(--text-main)' }}>
                          {f.name}
                        </h4>
                        <div className="text-[10px] flex items-center gap-1.5 truncate" style={{ color: 'var(--text-muted)' }}>
                          {f.email ? <span className="truncate">{f.email}</span> : null}
                          {f.phone ? <span>• {f.phone}</span> : null}
                        </div>
                      </div>
                    </div>

                    {/* Status Badge */}
                    <span className={`px-2 py-0.5 rounded text-[9px] font-black uppercase tracking-wider shrink-0 border ${
                      f.status === 'ACTIVE' 
                        ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30' 
                        : f.status === 'COMPLETED'
                        ? 'bg-blue-500/15 text-blue-600 dark:text-blue-400 border-blue-500/30'
                        : 'bg-slate-500/15 text-slate-600 dark:text-slate-400 border-slate-500/30'
                    }`}>
                      {f.status}
                    </span>
                  </div>

                  {/* ── Date Factor Hero Box ─────────────────────────── */}
                  <div 
                    className="mt-3 p-2 rounded-lg border flex items-center justify-between text-xs"
                    style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}
                  >
                    <div className="flex items-center gap-1.5 min-w-0 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      <Clock className="w-3 h-3 text-cyan-500 shrink-0" />
                      {isDateFiltered ? (
                        <span className="truncate">Period window:</span>
                      ) : (
                        <span className="truncate">First gift date:</span>
                      )}
                    </div>
                    <span className="font-extrabold text-[11px] text-cyan-600 dark:text-cyan-400 shrink-0 ml-1">
                      {isDateFiltered ? `${appliedStartDate || 'Start'} → ${appliedEndDate || 'Now'}` : firstDate}
                    </span>
                  </div>

                  {/* ── Raised Amounts ───────────────────────────────── */}
                  <div className="mt-3 flex items-baseline justify-between">
                    <div>
                      <div className="text-[10px] uppercase font-bold" style={{ color: 'var(--text-sub)' }}>
                        {isDateFiltered ? 'Raised (In Period)' : 'Total Raised (All-Time)'}
                      </div>
                      <div className="text-xl font-black text-emerald-600 dark:text-emerald-400 tracking-tight">
                        £{f.total_raised_period.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                      </div>
                    </div>
                    {isDateFiltered && (
                      <div className="text-right">
                        <div className="text-[10px] uppercase font-bold" style={{ color: 'var(--text-sub)' }}>Lifetime</div>
                        <div className="text-xs font-bold" style={{ color: 'var(--text-main)' }}>
                          £{f.total_raised_all_time.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                        </div>
                      </div>
                    )}
                  </div>

                  {/* ── Target & Progress Bar ────────────────────────── */}
                  {hasGoal ? (
                    <div className="mt-2.5">
                      <div className="flex items-center justify-between text-[11px] mb-1">
                        <span className="font-semibold" style={{ color: 'var(--text-muted)' }}>
                          Goal: £{f.target_goal.toLocaleString()}
                        </span>
                        <span className="font-black text-cyan-600 dark:text-cyan-400">
                          {progress}% {isCompleted ? '🎉' : ''}
                        </span>
                      </div>
                      <div className="w-full rounded-full h-2 overflow-hidden" style={{ backgroundColor: 'var(--bg-card-inner)' }}>
                        <div 
                          className={`h-full rounded-full transition-all duration-500 ${
                            isCompleted 
                              ? 'bg-gradient-to-r from-emerald-500 to-cyan-400' 
                              : 'bg-gradient-to-r from-cyan-500 to-blue-500'
                          }`}
                          style={{ width: `${Math.min(progress, 100)}%` }}
                        />
                      </div>
                    </div>
                  ) : (
                    <div className="mt-2 text-[11px] italic" style={{ color: 'var(--text-sub)' }}>
                      No fundraising target set
                    </div>
                  )}

                  {/* ── Donors & Avg Donation Metrics ────────────────── */}
                  <div className="mt-3 grid grid-cols-2 gap-2 pt-2 border-t" style={{ borderColor: 'var(--border-glass)' }}>
                    <div className="p-1.5 rounded-md" style={{ backgroundColor: 'var(--bg-card-inner)' }}>
                      <div className="text-[10px]" style={{ color: 'var(--text-sub)' }}>Donors</div>
                      <div className="text-xs font-extrabold" style={{ color: 'var(--text-main)' }}>
                        {isDateFiltered ? `${f.period_donors} (in period)` : f.total_donors}
                      </div>
                    </div>
                    <div className="p-1.5 rounded-md" style={{ backgroundColor: 'var(--bg-card-inner)' }}>
                      <div className="text-[10px]" style={{ color: 'var(--text-sub)' }}>Avg Donation</div>
                      <div className="text-xs font-extrabold" style={{ color: 'var(--text-main)' }}>
                        £{(f.average_donation || 0).toFixed(2)}
                      </div>
                    </div>
                  </div>

                  {/* ── Assigned Campaigns Pills ─────────────────────── */}
                  <div className="mt-3">
                    <div className="text-[10px] uppercase font-bold mb-1.5 flex items-center justify-between" style={{ color: 'var(--text-sub)' }}>
                      <span>Linked Campaigns ({f.assigned_campaigns ? f.assigned_campaigns.length : 0})</span>
                    </div>
                    <div className="flex flex-wrap gap-1 max-h-16 overflow-y-auto pr-1">
                      {(f.assigned_campaigns || []).map((c, i) => (
                        <span 
                          key={i} 
                          className="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border border-cyan-500/20 truncate max-w-full"
                          title={`${c.campaign_name} (${c.code || 'No Code'})`}
                        >
                          {c.campaign_name}
                        </span>
                      ))}
                      {(!f.assigned_campaigns || f.assigned_campaigns.length === 0) && (
                        <span className="text-[10px] italic" style={{ color: 'var(--text-sub)' }}>
                          No campaigns assigned yet
                        </span>
                      )}
                    </div>
                  </div>
                </div>

                {/* Card Bottom: Drilldown & Admin Actions */}
                <div className="pt-2 border-t flex items-center justify-between gap-2 mt-1" style={{ borderColor: 'var(--border-glass)' }}>
                  <button
                    onClick={() => {
                      setSelectedFundraiserId(f.id);
                      setDrilldownStartDate(appliedStartDate);
                      setDrilldownEndDate(appliedEndDate);
                      loadDrilldown(f.id, appliedStartDate, appliedEndDate);
                    }}
                    className="flex-1 py-1.5 px-2.5 rounded-lg bg-cyan-500/10 hover:bg-cyan-500/20 text-cyan-600 dark:text-cyan-400 text-xs font-bold flex items-center justify-center gap-1.5 transition-colors"
                  >
                    <Eye className="w-3.5 h-3.5" /> View Drilldown
                  </button>

                  {isSuperAdmin && (
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleOpenEditModal(f)}
                        className="p-1.5 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700/60 text-slate-400 hover:text-cyan-500 transition-colors"
                        title="Edit Fundraiser"
                      >
                        <Edit3 className="w-3.5 h-3.5" />
                      </button>
                      <button
                        onClick={() => setDeleteConfirm(f)}
                        className="p-1.5 rounded-lg bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition-colors"
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
                  <th 
                    onClick={() => {
                      if (sortBy === 'name') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                      else { setSortBy('name'); setSortOrder('asc'); }
                    }}
                    className="py-2.5 px-3.5 font-bold uppercase tracking-wider cursor-pointer hover:text-cyan-500 select-none transition-colors" 
                    style={{ color: sortBy === 'name' ? 'var(--color-primary, #06b6d4)' : 'var(--text-muted)' }}
                  >
                    <div className="flex items-center gap-1">
                      <span>Fundraiser</span>
                      {sortBy === 'name' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
                    </div>
                  </th>
                  <th 
                    onClick={() => {
                      if (sortBy === 'date') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                      else { setSortBy('date'); setSortOrder('desc'); }
                    }}
                    className="py-2.5 px-3.5 font-bold uppercase tracking-wider cursor-pointer hover:text-cyan-500 select-none transition-colors" 
                    style={{ color: sortBy === 'date' ? 'var(--color-primary, #06b6d4)' : 'var(--text-muted)' }}
                  >
                    <div className="flex items-center gap-1">
                      <span>First Gift Date</span>
                      {sortBy === 'date' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
                    </div>
                  </th>
                  <th 
                    onClick={() => {
                      if (sortBy === 'period_raised') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                      else { setSortBy('period_raised'); setSortOrder('desc'); }
                    }}
                    className="py-2.5 px-3.5 font-bold uppercase tracking-wider cursor-pointer hover:text-cyan-500 select-none transition-colors" 
                    style={{ color: sortBy === 'period_raised' ? 'var(--color-primary, #06b6d4)' : 'var(--text-muted)' }}
                  >
                    <div className="flex items-center gap-1">
                      <span>{isDateFiltered ? 'Period Raised' : 'Total Raised'}</span>
                      {sortBy === 'period_raised' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
                    </div>
                  </th>
                  <th 
                    onClick={() => {
                      if (sortBy === 'all_time_raised') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                      else { setSortBy('all_time_raised'); setSortOrder('desc'); }
                    }}
                    className="py-2.5 px-3.5 font-bold uppercase tracking-wider cursor-pointer hover:text-cyan-500 select-none transition-colors" 
                    style={{ color: sortBy === 'all_time_raised' ? 'var(--color-primary, #06b6d4)' : 'var(--text-muted)' }}
                  >
                    <div className="flex items-center gap-1">
                      <span>Lifetime Raised</span>
                      {sortBy === 'all_time_raised' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
                    </div>
                  </th>
                  <th 
                    onClick={() => {
                      if (sortBy === 'target_goal') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                      else { setSortBy('target_goal'); setSortOrder('desc'); }
                    }}
                    className="py-2.5 px-3.5 font-bold uppercase tracking-wider cursor-pointer hover:text-cyan-500 select-none transition-colors" 
                    style={{ color: sortBy === 'target_goal' ? 'var(--color-primary, #06b6d4)' : 'var(--text-muted)' }}
                  >
                    <div className="flex items-center gap-1">
                      <span>Target Goal</span>
                      {sortBy === 'target_goal' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
                    </div>
                  </th>
                  <th 
                    onClick={() => {
                      if (sortBy === 'progress') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                      else { setSortBy('progress'); setSortOrder('desc'); }
                    }}
                    className="py-2.5 px-3.5 font-bold uppercase tracking-wider cursor-pointer hover:text-cyan-500 select-none transition-colors" 
                    style={{ color: sortBy === 'progress' ? 'var(--color-primary, #06b6d4)' : 'var(--text-muted)' }}
                  >
                    <div className="flex items-center gap-1">
                      <span>Progress</span>
                      {sortBy === 'progress' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
                    </div>
                  </th>
                  <th 
                    onClick={() => {
                      if (sortBy === 'donors') setSortOrder(prev => prev === 'asc' ? 'desc' : 'asc');
                      else { setSortBy('donors'); setSortOrder('desc'); }
                    }}
                    className="py-2.5 px-3.5 font-bold uppercase tracking-wider cursor-pointer hover:text-cyan-500 select-none transition-colors" 
                    style={{ color: sortBy === 'donors' ? 'var(--color-primary, #06b6d4)' : 'var(--text-muted)' }}
                  >
                    <div className="flex items-center gap-1">
                      <span>Donors</span>
                      {sortBy === 'donors' && (sortOrder === 'asc' ? <ArrowUp className="w-3 h-3" /> : <ArrowDown className="w-3 h-3" />)}
                    </div>
                  </th>
                  <th className="py-2.5 px-3.5 font-bold uppercase tracking-wider" style={{ color: 'var(--text-muted)' }}>Assigned Campaigns</th>
                  <th className="py-2.5 px-3.5 font-bold uppercase tracking-wider text-right" style={{ color: 'var(--text-muted)' }}>Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y" style={{ borderColor: 'var(--border-glass)' }}>
                {paginatedFundraisers.map(f => (
                  <tr key={f.id} className="hover:bg-slate-200/40 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="py-2.5 px-3.5 font-bold" style={{ color: 'var(--text-main)' }}>
                      <div className="flex items-center gap-2">
                        <div className="w-6 h-6 rounded-md bg-cyan-500/20 text-cyan-500 font-bold flex items-center justify-center text-[10px]">
                          {f.name.substring(0, 2).toUpperCase()}
                        </div>
                        <div>
                          <div>{f.name}</div>
                          <div className="text-[10px] font-normal" style={{ color: 'var(--text-sub)' }}>{f.email || 'No email'}</div>
                        </div>
                      </div>
                    </td>
                    <td className="py-2.5 px-3.5 font-semibold text-[11px]" style={{ color: 'var(--text-muted)' }}>
                      {f.first_donation_date && f.first_donation_date !== 'N/A' ? f.first_donation_date : (f.start_date || 'N/A')}
                    </td>
                    <td className="py-2.5 px-3.5 font-black text-emerald-600 dark:text-emerald-400">
                      £{f.total_raised_period.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-3.5 font-bold text-purple-600 dark:text-purple-400">
                      £{f.total_raised_all_time.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </td>
                    <td className="py-2.5 px-3.5 font-semibold" style={{ color: 'var(--text-main)' }}>
                      {f.target_goal > 0 ? `£${f.target_goal.toLocaleString()}` : '—'}
                    </td>
                    <td className="py-2.5 px-3.5">
                      {f.target_goal > 0 ? (
                        <div className="flex items-center gap-1.5">
                          <div className="w-14 rounded-full h-1.5 overflow-hidden" style={{ backgroundColor: 'var(--bg-card-inner)' }}>
                            <div 
                              className="bg-cyan-500 h-full rounded-full"
                              style={{ width: `${Math.min(f.progress_percentage, 100)}%` }}
                            />
                          </div>
                          <span className="font-bold text-[10px] text-cyan-600 dark:text-cyan-400">{f.progress_percentage}%</span>
                        </div>
                      ) : (
                        <span className="text-[10px]" style={{ color: 'var(--text-sub)' }}>—</span>
                      )}
                    </td>
                    <td className="py-2.5 px-3.5 font-semibold" style={{ color: 'var(--text-main)' }}>
                      {isDateFiltered ? `${f.period_donors} (period)` : f.total_donors}
                    </td>
                    <td className="py-2.5 px-3.5">
                      <div className="flex flex-wrap gap-1 max-w-[200px]">
                        {(f.assigned_campaigns || []).slice(0, 2).map((c, i) => (
                          <span key={i} className="px-1.5 py-0.5 rounded text-[9px] font-bold bg-cyan-500/10 text-cyan-700 dark:text-cyan-300 border border-cyan-500/20 truncate max-w-[110px]">
                            {c.campaign_name}
                          </span>
                        ))}
                        {(f.assigned_campaigns || []).length > 2 && (
                          <span className="text-[9px] font-bold self-center" style={{ color: 'var(--text-sub)' }}>
                            +{f.assigned_campaigns.length - 2}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="py-2.5 px-3.5 text-right">
                      <div className="flex items-center justify-end gap-1">
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
                          <Eye className="w-3 h-3" />
                        </button>
                        {isSuperAdmin && (
                          <>
                            <button
                              onClick={() => handleOpenEditModal(f)}
                              className="p-1 rounded hover:bg-slate-200 dark:hover:bg-slate-700/60 text-slate-400 hover:text-cyan-500 transition-colors"
                              title="Edit Fundraiser"
                            >
                              <Edit3 className="w-3 h-3" />
                            </button>
                            <button
                              onClick={() => setDeleteConfirm(f)}
                              className="p-1 rounded bg-rose-500/10 hover:bg-rose-500/20 text-rose-500 transition-colors"
                              title="Delete Fundraiser"
                            >
                              <Trash2 className="w-3 h-3" />
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

      {/* Bottom Pagination Controls */}
      {!loading && filteredFundraisers.length > 0 && renderPaginationControls(false)}

      {/* ── Super Admin: Create / Edit Modal ─────────────────────── */}
      {showModal && isSuperAdmin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm">
          <div 
            className="glass-panel w-full max-w-2xl max-h-[90vh] flex flex-col shadow-2xl rounded-2xl overflow-hidden animate-in fade-in zoom-in-95 duration-200 border"
            style={{ backgroundColor: 'var(--bg-card)', borderColor: 'var(--border-glass)', color: 'var(--text-main)' }}
          >
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b" style={{ borderColor: 'var(--border-glass)' }}>
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-xl bg-cyan-500/15 text-cyan-500">
                  <HeartHandshake className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-black" style={{ color: 'var(--text-main)' }}>
                    {editingFundraiser ? `Edit Fundraiser: ${editingFundraiser.name}` : 'Create New Fundraiser'}
                  </h3>
                  <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                    Assign campaigns &amp; multi-codes. A campaign can only be assigned to one fundraiser.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Body */}
            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar flex flex-col gap-3.5">
              {formMsg && (
                <div className={`p-2.5 rounded-lg text-xs font-bold border ${
                  formMsg.startsWith('✅') ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30' : 'bg-rose-500/10 text-rose-600 dark:text-rose-400 border-rose-500/30'
                }`}>
                  {formMsg}
                </div>
              )}

              <form onSubmit={handleSubmitModal} id="fundraiser-form" className="flex flex-col gap-3.5">
                {/* Row 1: Name & Target Goal */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
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
                      className="w-full rounded-lg px-3 py-1.5 text-xs focus:outline-none"
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
                      className="w-full rounded-lg px-3 py-1.5 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    />
                  </div>
                </div>

                {/* Row 2: Status & Optional Manual Start Date */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                      Status
                    </label>
                    <select
                      value={modalForm.status}
                      onChange={e => setModalForm(prev => ({ ...prev, status: e.target.value }))}
                      className="w-full rounded-lg px-3 py-1.5 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    >
                      <option value="ACTIVE">ACTIVE</option>
                      <option value="PAUSED">PAUSED</option>
                      <option value="COMPLETED">COMPLETED</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                      <Calendar className="w-3 h-3 inline mr-1 text-cyan-500" /> Manual Start Date (Optional)
                    </label>
                    <input
                      type="date"
                      value={modalForm.start_date}
                      onChange={e => setModalForm(prev => ({ ...prev, start_date: e.target.value }))}
                      className="w-full rounded-lg px-3 py-1.5 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    />
                    <span className="text-[10px] block mt-0.5" style={{ color: 'var(--text-sub)' }}>
                      Defaults automatically to the earliest donation date in dataset.
                    </span>
                  </div>
                </div>

                {/* Row 3: Email & Phone (Optional) */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                  <div>
                    <label className="block text-xs font-bold mb-1" style={{ color: 'var(--text-main)' }}>
                      Contact Email (Optional)
                    </label>
                    <input
                      type="email"
                      placeholder="fundraiser@example.com"
                      value={modalForm.email}
                      onChange={e => setModalForm(prev => ({ ...prev, email: e.target.value }))}
                      className="w-full rounded-lg px-3 py-1.5 text-xs focus:outline-none"
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
                      className="w-full rounded-lg px-3 py-1.5 text-xs focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    />
                  </div>
                </div>

                {/* ── Campaign & Code Assignment Section ──────────────── */}
                <div className="mt-1 border-t pt-3" style={{ borderColor: 'var(--border-glass)' }}>
                  <div className="flex items-center justify-between mb-1.5">
                    <div>
                      <label className="block text-xs font-black flex items-center gap-1.5" style={{ color: 'var(--text-main)' }}>
                        <Layers className="w-3.5 h-3.5 text-cyan-500" /> Assign Campaigns &amp; Multi-Codes *
                      </label>
                      <p className="text-[11px]" style={{ color: 'var(--text-muted)' }}>
                        Select the campaigns belonging to this fundraiser ({modalForm.assigned_campaigns.length} assigned)
                      </p>
                    </div>
                  </div>

                  {/* Selected Badges */}
                  {modalForm.assigned_campaigns.length > 0 && (
                    <div 
                      className="p-2.5 rounded-lg border mb-2.5 flex flex-wrap gap-1 max-h-24 overflow-y-auto custom-scrollbar"
                      style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}
                    >
                      {modalForm.assigned_campaigns.map((c, i) => (
                        <span 
                          key={i}
                          className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-[11px] font-bold bg-cyan-500/15 text-cyan-700 dark:text-cyan-300 border border-cyan-500/30"
                        >
                          <span className="truncate max-w-[180px]">{c.campaign_name}</span>
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
                    <div className="relative flex-1 min-w-[160px]">
                      <Search className="w-3 h-3 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
                      <input
                        type="text"
                        placeholder="Search available campaigns..."
                        value={campaignSearch}
                        onChange={e => setCampaignSearch(e.target.value)}
                        className="w-full pl-7 pr-3 py-1.5 text-xs rounded-lg focus:outline-none"
                        style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                      />
                    </div>

                    <select
                      value={platformFilter}
                      onChange={e => setPlatformFilter(e.target.value)}
                      className="px-2 py-1.5 text-xs rounded-lg focus:outline-none"
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
                      className="px-2 py-1.5 text-xs rounded-lg focus:outline-none"
                      style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                    >
                      <option value="ALL">All Campaigns</option>
                      <option value="UNASSIGNED">Unassigned Only</option>
                      <option value="ASSIGNED_THIS">Assigned to this Fundraiser</option>
                    </select>
                  </div>

                  {/* Available Campaigns Multi-Select List */}
                  <div 
                    className="border rounded-lg p-1.5 max-h-44 overflow-y-auto custom-scrollbar flex flex-col gap-1"
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
                            className={`p-1.5 rounded-md text-xs flex items-center justify-between gap-2 transition-colors ${
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
                              <div className={`w-3.5 h-3.5 rounded flex items-center justify-center text-[9px] font-bold shrink-0 ${
                                isAssignedToOther 
                                  ? 'bg-amber-500/20 text-amber-600 border border-amber-500/30'
                                  : isAssignedToThis 
                                  ? 'bg-cyan-500 text-white' 
                                  : 'border border-slate-400'
                              }`}>
                                {isAssignedToOther ? <Lock className="w-2.5 h-2.5" /> : isAssignedToThis ? <Check className="w-2.5 h-2.5 stroke-[3]" /> : null}
                              </div>
                              <div className="truncate">
                                <span className="font-semibold text-xs">{camp.campaign_name}</span>
                                <span 
                                  className="ml-1.5 px-1 py-0.5 rounded text-[9px] font-mono border"
                                  style={{ backgroundColor: 'var(--bg-card)', color: 'var(--accent-cyan)', borderColor: 'var(--border-glass)' }}
                                >
                                  {camp.code}
                                </span>
                              </div>
                            </div>

                            <div className="flex items-center gap-2 shrink-0">
                              {isAssignedToOther && (
                                <span className="px-1.5 py-0.2 rounded text-[8px] font-bold bg-amber-500/15 text-amber-700 dark:text-amber-300 border border-amber-500/30 flex items-center gap-1">
                                  <Lock className="w-2 h-2" /> {camp.assigned_to?.fundraiser_name}
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
            <div className="p-3.5 border-t flex items-center justify-end gap-2.5" style={{ borderColor: 'var(--border-glass)' }}>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                className="btn-secondary text-xs px-3.5 py-1.5"
              >
                Cancel
              </button>
              <button
                type="submit"
                form="fundraiser-form"
                disabled={submitting}
                className="btn-primary text-xs flex items-center gap-1.5 px-4 py-1.5 shadow-md shadow-cyan-500/20 font-bold"
              >
                {submitting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <CheckCircle2 className="w-3 h-3" />}
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
            className="glass-panel max-w-md w-full p-5 rounded-2xl border shadow-2xl animate-in zoom-in-95"
            style={{ backgroundColor: 'var(--bg-card)', borderColor: 'rgba(244,63,94,0.3)', color: 'var(--text-main)' }}
          >
            <div className="flex items-center gap-2.5 text-rose-500 mb-2.5">
              <ShieldAlert className="w-5 h-5" />
              <h3 className="text-sm font-extrabold">Confirm Delete Fundraiser</h3>
            </div>
            <p className="text-xs" style={{ color: 'var(--text-main)' }}>
              Are you sure you want to delete fundraiser <strong style={{ color: 'var(--text-main)' }}>"{deleteConfirm.name}"</strong>?
            </p>
            <p className="text-[11px] mt-1" style={{ color: 'var(--text-sub)' }}>
              This will remove the fundraiser profile and all campaign assignments. Underlying donor transactions will not be deleted.
            </p>
            <div className="flex items-center justify-end gap-2.5 mt-5">
              <button
                onClick={() => setDeleteConfirm(null)}
                className="btn-secondary text-xs px-3.5 py-1.5"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDeleteFundraiser(deleteConfirm.id)}
                disabled={deleting}
                className="px-3.5 py-1.5 rounded-lg text-xs font-bold bg-rose-500 hover:bg-rose-600 text-white transition-colors flex items-center gap-1.5 shadow-md shadow-rose-500/20"
              >
                {deleting ? <RefreshCw className="w-3 h-3 animate-spin" /> : <Trash2 className="w-3 h-3" />}
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
            className="w-full max-w-2xl h-full glass-panel border-l shadow-2xl flex flex-col overflow-hidden animate-in slide-in-from-right duration-300 rounded-none" 
            style={{ backgroundColor: 'var(--drawer-bg)', borderColor: 'var(--border-glass)', color: 'var(--text-main)' }}
          >
            
            {/* Drawer Header */}
            <div className="p-4 border-b flex items-center justify-between gap-3" style={{ borderColor: 'var(--border-glass)' }}>
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-cyan-500/20 text-cyan-500 font-black flex items-center justify-center text-xs border border-cyan-500/30">
                  {drilldownData?.fundraiser?.name?.substring(0, 2).toUpperCase() || 'FR'}
                </div>
                <div>
                  <h3 className="text-sm font-black" style={{ color: 'var(--text-main)' }}>
                    {drilldownData?.fundraiser?.name || 'Fundraiser Performance'}
                  </h3>
                  <div className="text-[11px] flex items-center gap-2 flex-wrap" style={{ color: 'var(--text-muted)' }}>
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
                className="p-1.5 rounded-lg text-slate-400 hover:text-slate-700 dark:hover:text-white hover:bg-slate-200 dark:hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Drawer Filter Sub-bar */}
            <div className="p-2.5 border-b flex items-center justify-between gap-2 flex-wrap text-xs" style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}>
              <div className="flex items-center gap-1.5 flex-wrap">
                <span className="font-bold flex items-center gap-1 text-[11px]" style={{ color: 'var(--text-muted)' }}>
                  <Calendar className="w-3 h-3 text-cyan-500" /> Filter:
                </span>
                <input
                  type="date"
                  value={drilldownStartDate}
                  onChange={e => setDrilldownStartDate(e.target.value)}
                  className="px-2 py-0.5 text-xs rounded-md focus:outline-none"
                  style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                />
                <span style={{ color: 'var(--text-sub)' }}>&rarr;</span>
                <input
                  type="date"
                  value={drilldownEndDate}
                  onChange={e => setDrilldownEndDate(e.target.value)}
                  className="px-2 py-0.5 text-xs rounded-md focus:outline-none"
                  style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', border: '1px solid var(--input-border)' }}
                />
                <button
                  onClick={() => loadDrilldown(selectedFundraiserId, drilldownStartDate, drilldownEndDate)}
                  className="btn-primary text-[11px] px-2 py-0.5 font-bold"
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
                    className="text-rose-500 font-bold hover:underline text-[11px] ml-1"
                  >
                    Reset
                  </button>
                )}
              </div>

              <div className="font-black text-emerald-600 dark:text-emerald-400 text-xs">
                {(drilldownStartDate || drilldownEndDate) ? (
                  <span>Period: £{drilldownData?.fundraiser?.total_raised_period?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                ) : (
                  <span>All-Time: £{drilldownData?.fundraiser?.total_raised_all_time?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
                )}
              </div>
            </div>

            {/* Drawer Body */}
            <div className="flex-1 overflow-y-auto p-4 custom-scrollbar flex flex-col gap-4">
              {loadingDrilldown ? (
                <div className="text-center py-10 flex flex-col items-center justify-center gap-2">
                  <RefreshCw className="w-7 h-7 text-cyan-500 animate-spin" />
                  <p className="text-xs" style={{ color: 'var(--text-muted)' }}>Loading campaign breakdown...</p>
                </div>
              ) : (
                <>
                  {/* Campaign Breakdown Table */}
                  <div>
                    <h4 className="text-xs font-extrabold uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                      <BarChart3 className="w-3.5 h-3.5 text-cyan-500" /> Assigned Campaign Performance
                    </h4>
                    <div className="border rounded-lg overflow-hidden" style={{ borderColor: 'var(--border-glass)' }}>
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b" style={{ backgroundColor: 'var(--table-header-bg)', borderColor: 'var(--border-glass)' }}>
                            <th className="py-2 px-3 font-bold" style={{ color: 'var(--text-muted)' }}>Campaign</th>
                            <th className="py-2 px-3 font-bold" style={{ color: 'var(--text-muted)' }}>Code</th>
                            <th className="py-2 px-3 font-bold" style={{ color: 'var(--text-muted)' }}>Category</th>
                            <th className="py-2 px-3 font-bold text-right" style={{ color: 'var(--text-muted)' }}>
                              {(drilldownStartDate || drilldownEndDate) ? 'Period Raised' : 'Gross Raised'}
                            </th>
                            <th className="py-2 px-3 font-bold text-right" style={{ color: 'var(--text-muted)' }}>Donors</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y" style={{ borderColor: 'var(--border-glass)' }}>
                          {(drilldownData?.campaign_breakdown || []).length === 0 ? (
                            <tr>
                              <td colSpan={5} className="py-3 text-center" style={{ color: 'var(--text-sub)' }}>
                                No donation activity recorded for assigned campaigns yet.
                              </td>
                            </tr>
                          ) : (
                            drilldownData.campaign_breakdown.map((cb, i) => (
                              <tr key={i} className="hover:bg-slate-200/40 dark:hover:bg-slate-800/40 transition-colors">
                                <td className="py-2 px-3 font-bold max-w-[180px] truncate" style={{ color: 'var(--text-main)' }} title={cb.campaign_name}>
                                  {cb.campaign_name}
                                </td>
                                <td className="py-2 px-3 font-mono text-cyan-600 dark:text-cyan-400 font-bold text-[10px]">
                                  {cb.code}
                                </td>
                                <td className="py-2 px-3 text-[10px]" style={{ color: 'var(--text-muted)' }}>
                                  {cb.heading}
                                </td>
                                <td className="py-2 px-3 font-black text-emerald-600 dark:text-emerald-400 text-right">
                                  £{cb.gross_raised.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                                </td>
                                <td className="py-2 px-3 text-right font-semibold" style={{ color: 'var(--text-main)' }}>
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
                      <h4 className="text-xs font-extrabold uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                        <TrendingUp className="w-3.5 h-3.5 text-purple-500" /> Monthly Growth Breakdown
                      </h4>
                      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                        {drilldownData.monthly_timeline.map((m, i) => (
                          <div 
                            key={i} 
                            className="p-2 rounded-lg border text-center transition-all"
                            style={{ backgroundColor: 'var(--bg-card-inner)', borderColor: 'var(--border-glass)' }}
                          >
                            <div className="text-[9px] font-bold uppercase" style={{ color: 'var(--text-sub)' }}>{m.month}</div>
                            <div className="text-[11px] font-black text-purple-600 dark:text-purple-400 mt-0.5">
                              £{m.amount.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Recent Donations Log */}
                  <div>
                    <h4 className="text-xs font-extrabold uppercase tracking-wider mb-2 flex items-center gap-1.5" style={{ color: 'var(--text-muted)' }}>
                      <Clock className="w-3.5 h-3.5 text-cyan-500" /> Recent Transactions ({drilldownData?.recent_transactions?.length || 0})
                    </h4>
                    <div className="border rounded-lg overflow-hidden max-h-52 overflow-y-auto custom-scrollbar" style={{ borderColor: 'var(--border-glass)' }}>
                      <table className="w-full text-left text-xs border-collapse">
                        <thead>
                          <tr className="border-b" style={{ backgroundColor: 'var(--table-header-bg)', borderColor: 'var(--border-glass)' }}>
                            <th className="py-1.5 px-2.5 font-bold" style={{ color: 'var(--text-muted)' }}>Date</th>
                            <th className="py-1.5 px-2.5 font-bold" style={{ color: 'var(--text-muted)' }}>Donor</th>
                            <th className="py-1.5 px-2.5 font-bold" style={{ color: 'var(--text-muted)' }}>Campaign</th>
                            <th className="py-1.5 px-2.5 font-bold text-right" style={{ color: 'var(--text-muted)' }}>Amount</th>
                          </tr>
                        </thead>
                        <tbody className="divide-y" style={{ borderColor: 'var(--border-glass)' }}>
                          {(drilldownData?.recent_transactions || []).map((tx, i) => (
                            <tr key={i} className="hover:bg-slate-200/40 dark:hover:bg-slate-800/40 transition-colors">
                              <td className="py-1.5 px-2.5 text-[10px]" style={{ color: 'var(--text-sub)' }}>{tx.date}</td>
                              <td className="py-1.5 px-2.5 font-bold" style={{ color: 'var(--text-main)' }}>{tx.donor_name}</td>
                              <td className="py-1.5 px-2.5 truncate max-w-[140px]" style={{ color: 'var(--text-muted)' }}>{tx.campaign_name}</td>
                              <td className="py-1.5 px-2.5 font-bold text-emerald-600 dark:text-emerald-400 text-right">£{tx.amount.toFixed(2)}</td>
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
