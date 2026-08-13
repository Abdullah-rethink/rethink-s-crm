import React, { useEffect, useState, useRef, useMemo } from 'react';
import { 
  Shield, 
  Save, 
  CheckCircle, 
  AlertCircle, 
  RefreshCw, 
  Download, 
  Upload, 
  Trash2, 
  X, 
  FileSpreadsheet, 
  Lock,
  ExternalLink,
  Zap,
  Gift,
  CreditCard,
  Globe,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  Filter
} from 'lucide-react';
import { API_BASE_URL } from '../config';

// Robust frontend text cleaner to repair mojibake / corrupted UTF-8 and strip zero-width characters
function cleanText(val) {
  if (!val || typeof val !== 'string') return val || '';
  let s = val.trim();
  s = s.replace(/\u00AD/g, '').replace(/[\u200B-\u200D\uFEFF]/g, '');
  s = s.replace(/AshbÄ\xad/gi, 'Ashbā')
       .replace(/AshbÄ/gi, 'Ashbā')
       .replace(/â€“/g, '–')
       .replace(/â€”/g, '—')
       .replace(/â€™/g, "’")
       .replace(/â€œ/g, '“')
       .replace(/â€/g, '”')
       .replace(/Ã©/g, 'é')
       .replace(/Ã /g, 'à');
  return s;
}

export default function ClassificationView({ user }) {
  // Persist selected platform in localStorage so it NEVER resets unexpectedly!
  const [platform, setPlatform] = useState(() => {
    return localStorage.getItem('selected_classification_platform') || 'launchgood';
  });

  const [matrixData, setMatrixData] = useState({ total_campaigns: 0, classified_campaigns: 0, unassigned_campaigns: 0, rules: [] });
  const [codeMap, setCodeMap] = useState({});
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  // 🚀 Fast Client-Side Search & Pagination State
  const [searchQuery, setSearchQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('ALL'); // 'ALL', 'CLASSIFIED', 'UNASSIGNED'
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(50); // 25, 50, 100, 250, 'All'
  const [jumpPage, setJumpPage] = useState('');
  
  // Importer Modal State
  const [showImportModal, setShowImportModal] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importMode, setImportMode] = useState('merge'); // 'merge' or 'replace'
  const [importing, setImporting] = useState(false);
  const [importMsg, setImportMsg] = useState('');
  const fileInputRef = useRef(null);

  const isSuperAdmin = user?.role === 'super_admin';

  // Update platform handler with localStorage persistence
  const handleSelectPlatform = (newPlat) => {
    if (newPlat === platform) return;
    setPlatform(newPlat);
    localStorage.setItem('selected_classification_platform', newPlat);
    setCurrentPage(1);
  };

  // Reset page to 1 whenever search, status filter, or page size changes
  useEffect(() => {
    setCurrentPage(1);
  }, [platform, statusFilter, searchQuery, pageSize]);

  // Fetch Code Map for dynamic Code -> Heading, Sub-Heading, Country, Zakat auto-fill
  useEffect(() => {
    fetch(`${API_BASE_URL}/api/classifications/code-map`)
      .then(res => res.json())
      .then(data => {
        if (data && typeof data === 'object') {
          setCodeMap(data);
        }
      })
      .catch(err => console.error('Error fetching code map:', err));
  }, []);

  // Race-Condition-Free Data Loading with Cancellation Cleanup
  useEffect(() => {
    let isCurrent = true;
    setLoading(true);
    setSaveMsg('');

    fetch(`${API_BASE_URL}/api/classifications/${platform}`)
      .then(res => res.json())
      .then(data => {
        if (!isCurrent) return; // Discard response if user already switched platforms!
        
        let rules = (data.rules || []).map(r => ({
          ...r,
          'Campaign Name': cleanText(r['Campaign Name']),
          'Community Name': cleanText(r['Community Name']),
          'Heading': cleanText(r['Heading']),
          'Sub-Heading': cleanText(r['Sub-Heading']),
          'Country': cleanText(r['Country']),
          'Code': cleanText(r['Code']),
          'Zakat Eligibility': cleanText(r['Zakat Eligibility']),
          'Campaign URL': r['Campaign URL'] || r['campaign_url'] || ''
        }));

        // Deduplicate GiveBright by Campaign Name
        if (platform === 'givebright') {
          const seen = new Set();
          rules = rules.filter(r => {
            const cName = String(r['Campaign Name'] || '').trim().toLowerCase();
            if (!cName || seen.has(cName)) return false;
            seen.add(cName);
            return true;
          });
        }

        setMatrixData({
          ...data,
          total_campaigns: rules.length,
          classified_campaigns: rules.filter(r => r['Heading'] && r['Heading'] !== 'Unassigned').length,
          unassigned_campaigns: rules.filter(r => !r['Heading'] || r['Heading'] === 'Unassigned').length,
          rules: rules
        });
        setLoading(false);
      })
      .catch(err => {
        if (!isCurrent) return;
        console.error('Error loading classification matrix:', err);
        setLoading(false);
      });

    return () => {
      isCurrent = false; // Cancel stale promise resolution
    };
  }, [platform]);

  // Dynamic cell change handler with Code -> Classification Auto-Fill
  const handleCellChange = (campaignKey, field, value) => {
    if (!isSuperAdmin) return;
    const valClean = cleanText(value);
    setMatrixData(prev => {
      const updatedRules = prev.rules.map(r => {
        const cName = r['Campaign Name'] || r['campaign_name'];
        if (cName === campaignKey) {
          const currentRow = { ...r, [field]: valClean };

          // When Code changes, automatically resolve & fill Heading, Sub-Heading, Country, and Zakat!
          if (field === 'Code' && valClean) {
            const codeKey = valClean.trim().toLowerCase();
            if (codeMap[codeKey]) {
              const info = codeMap[codeKey];
              if (info.Heading && info.Heading !== 'Unassigned') currentRow['Heading'] = info.Heading;
              if (info['Sub-Heading'] && info['Sub-Heading'] !== 'Unassigned') currentRow['Sub-Heading'] = info['Sub-Heading'];
              if (info.Country && info.Country !== 'Unassigned') currentRow['Country'] = info.Country;
              if (info['Zakat Eligibility'] && info['Zakat Eligibility'] !== 'Unassigned') currentRow['Zakat Eligibility'] = info['Zakat Eligibility'];
            }
          }
          return currentRow;
        }
        return r;
      });

      return {
        ...prev,
        classified_campaigns: updatedRules.filter(r => r['Heading'] && r['Heading'] !== 'Unassigned').length,
        unassigned_campaigns: updatedRules.filter(r => !r['Heading'] || r['Heading'] === 'Unassigned').length,
        rules: updatedRules
      };
    });
  };

  // 🔍 Filtered Rules Calculation (Status + Live Search)
  const filteredRules = useMemo(() => {
    let list = matrixData.rules || [];

    // 1. Status Filter
    if (statusFilter === 'CLASSIFIED') {
      list = list.filter(r => r['Heading'] && r['Heading'] !== 'Unassigned');
    } else if (statusFilter === 'UNASSIGNED') {
      list = list.filter(r => !r['Heading'] || r['Heading'] === 'Unassigned');
    }

    // 2. Search Query Filter
    if (searchQuery && searchQuery.trim()) {
      const q = searchQuery.trim().toLowerCase();
      list = list.filter(r => {
        return (
          (r['Campaign Name'] && String(r['Campaign Name']).toLowerCase().includes(q)) ||
          (r['Community Name'] && String(r['Community Name']).toLowerCase().includes(q)) ||
          (r['Code'] && String(r['Code']).toLowerCase().includes(q)) ||
          (r['Heading'] && String(r['Heading']).toLowerCase().includes(q)) ||
          (r['Sub-Heading'] && String(r['Sub-Heading']).toLowerCase().includes(q)) ||
          (r['Country'] && String(r['Country']).toLowerCase().includes(q)) ||
          (r['Zakat Eligibility'] && String(r['Zakat Eligibility']).toLowerCase().includes(q)) ||
          (r['Campaign URL'] && String(r['Campaign URL']).toLowerCase().includes(q))
        );
      });
    }

    return list;
  }, [matrixData.rules, statusFilter, searchQuery]);

  // 📑 Pagination Bounds & Slices
  const effectivePageSize = pageSize === 'All' ? Math.max(1, filteredRules.length) : Number(pageSize);
  const totalPages = Math.max(1, Math.ceil(filteredRules.length / effectivePageSize));
  const safePage = Math.min(Math.max(1, currentPage), totalPages);

  const paginatedRules = useMemo(() => {
    if (pageSize === 'All') return filteredRules;
    const start = (safePage - 1) * effectivePageSize;
    return filteredRules.slice(start, start + effectivePageSize);
  }, [filteredRules, safePage, effectivePageSize, pageSize]);

  const handleSave = () => {
    if (!isSuperAdmin) return;
    setSaving(true);
    setSaveMsg('');

    fetch(`${API_BASE_URL}/api/classifications/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role,
        can_edit_matrix: true,
        platform: platform,
        rules: matrixData.rules
      })
    })
      .then(r => r.json())
      .then(res => {
        setSaving(false);
        if (res?.status === 'success') {
          setSaveMsg(`✅ ${res.message}`);
        } else {
          setSaveMsg(`❌ ${res?.detail || 'Failed to save rules.'}`);
        }
      })
      .catch(err => {
        setSaving(false);
        setSaveMsg(`❌ Error: ${err.message}`);
      });
  };

  const handleDeleteRule = async (rule) => {
    if (!isSuperAdmin) return;
    const cName = rule['Campaign Name'] || rule['campaign_name'];
    if (!window.confirm(`Are you sure you want to delete the classification rule for "${cName}"?\n\nMatching donor records will be reset to Unassigned.`)) {
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/classifications/delete-rule`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_role: user?.role,
          platform: platform,
          campaign_name: cName,
          community_name: rule['Community Name'] || rule['community_name'] || null
        })
      });
      const data = await res.json();
      if (data?.status === 'success') {
        setSaveMsg(`🗑️ ${data.message}`);
        setMatrixData(prev => {
          const filtered = prev.rules.filter(r => (r['Campaign Name'] || r['campaign_name']) !== cName);
          return {
            ...prev,
            total_campaigns: filtered.length,
            classified_campaigns: filtered.filter(r => r['Heading'] && r['Heading'] !== 'Unassigned').length,
            unassigned_campaigns: filtered.filter(r => !r['Heading'] || r['Heading'] === 'Unassigned').length,
            rules: filtered
          };
        });
      } else {
        setSaveMsg(`❌ ${data?.detail || 'Failed to delete rule.'}`);
      }
    } catch (err) {
      setSaveMsg(`❌ Error: ${err.message}`);
    }
  };

  const handleExport = (format = 'csv') => {
    const url = `${API_BASE_URL}/api/classifications/export?platform=${platform}&format=${format}`;
    window.open(url, '_blank');
  };

  const handleImportSubmit = async (e) => {
    e.preventDefault();
    if (!importFile) {
      setImportMsg('Please select a CSV or Excel file.');
      return;
    }

    setImporting(true);
    setImportMsg('');

    const formData = new FormData();
    formData.append('file', importFile);
    formData.append('platform', platform);
    formData.append('mode', importMode);
    formData.append('user_role', user?.role || 'user');

    try {
      const res = await fetch(`${API_BASE_URL}/api/classifications/bulk-import`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      setImporting(false);

      if (res.ok && data?.status === 'success') {
        setImportMsg(`✅ ${data.message}`);
        setTimeout(() => {
          setShowImportModal(false);
          setImportFile(null);
          setImportMsg('');
          // Re-fetch active matrix
          setLoading(true);
          fetch(`${API_BASE_URL}/api/classifications/${platform}`)
            .then(r => r.json())
            .then(d => {
              let rules = (d.rules || []).map(r => ({
                ...r,
                'Campaign Name': cleanText(r['Campaign Name']),
                'Community Name': cleanText(r['Community Name']),
                'Heading': cleanText(r['Heading']),
                'Sub-Heading': cleanText(r['Sub-Heading']),
                'Country': cleanText(r['Country']),
                'Code': cleanText(r['Code']),
                'Zakat Eligibility': cleanText(r['Zakat Eligibility']),
                'Campaign URL': r['Campaign URL'] || r['campaign_url'] || ''
              }));
              setMatrixData({
                ...d,
                total_campaigns: rules.length,
                classified_campaigns: rules.filter(r => r['Heading'] && r['Heading'] !== 'Unassigned').length,
                unassigned_campaigns: rules.filter(r => !r['Heading'] || r['Heading'] === 'Unassigned').length,
                rules: rules
              });
              setLoading(false);
            });
        }, 1500);
      } else {
        setImportMsg(`❌ ${data?.detail || 'Bulk import failed.'}`);
      }
    } catch (err) {
      setImporting(false);
      setImportMsg(`❌ Error uploading file: ${err.message}`);
    }
  };

  // Known valid Codes for the datalist autocomplete dropdown
  const knownCodes = Object.keys(codeMap).map(k => k.toUpperCase());

  // Visual Theme Badges per platform
  const bannerStyles = {
    launchgood: {
      container: 'bg-gradient-to-r from-teal-500/15 via-cyan-500/10 to-transparent border-teal-500/30 text-teal-900 dark:text-teal-200',
      iconBg: 'bg-teal-500 text-white',
      title: 'text-teal-700 dark:text-teal-300 font-extrabold',
      subtitle: 'text-slate-600 dark:text-slate-400 font-medium',
      activePill: 'bg-teal-600 text-white shadow-teal-500/30',
      countPill: 'border-teal-500/40 text-teal-700 dark:text-teal-300 bg-teal-50 dark:bg-teal-950/40'
    },
    givebright: {
      container: 'bg-gradient-to-r from-purple-500/15 via-indigo-500/10 to-transparent border-purple-500/30 text-purple-900 dark:text-purple-200',
      iconBg: 'bg-purple-600 text-white',
      title: 'text-purple-700 dark:text-purple-300 font-extrabold',
      subtitle: 'text-slate-600 dark:text-slate-400 font-medium',
      activePill: 'bg-purple-600 text-white shadow-purple-500/30',
      countPill: 'border-purple-500/40 text-purple-700 dark:text-purple-300 bg-purple-50 dark:bg-purple-950/40'
    },
    paysuite: {
      container: 'bg-gradient-to-r from-amber-500/15 via-orange-500/10 to-transparent border-amber-500/30 text-amber-900 dark:text-amber-200',
      iconBg: 'bg-amber-600 text-white',
      title: 'text-amber-700 dark:text-amber-300 font-extrabold',
      subtitle: 'text-slate-600 dark:text-slate-400 font-medium',
      activePill: 'bg-amber-600 text-white shadow-amber-500/30',
      countPill: 'border-amber-500/40 text-amber-700 dark:text-amber-300 bg-amber-50 dark:bg-amber-950/40'
    },
    website: {
      container: 'bg-gradient-to-r from-blue-500/15 via-cyan-500/10 to-transparent border-blue-500/30 text-blue-900 dark:text-blue-200',
      iconBg: 'bg-blue-600 text-white',
      title: 'text-blue-700 dark:text-blue-300 font-extrabold',
      subtitle: 'text-slate-600 dark:text-slate-400 font-medium',
      activePill: 'bg-blue-600 text-white shadow-blue-500/30',
      countPill: 'border-blue-500/40 text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-950/40'
    }
  };

  const bStyles = bannerStyles[platform] || bannerStyles.launchgood;

  return (
    <div className="flex flex-col gap-6 animate-fade-in pb-16">
      {/* Top Header & Platform Selector Bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-white/10">
        <div className="flex items-center gap-3">
          <div className="p-3 bg-gradient-to-tr from-teal-600 to-cyan-500 rounded-2xl shadow-lg shadow-cyan-500/20 text-white">
            <Shield className="w-6 h-6" />
          </div>
          <div>
            <h1 className="text-xl font-black tracking-tight text-slate-900 dark:text-white flex items-center gap-2">
              Campaign Classifications
              <span className="text-xs px-2.5 py-0.5 rounded-full font-bold uppercase bg-cyan-100 text-cyan-800 dark:bg-cyan-500/20 dark:text-cyan-400">
                Master Matrix
              </span>
            </h1>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5 font-medium">
              Dynamic classification rules with instant auto-fill, pagination, and multi-platform sync
            </p>
          </div>
        </div>

        {/* Global Action Buttons */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Save & Sync Matrix Button */}
          {isSuperAdmin && (
            <button
              onClick={handleSave}
              disabled={saving}
              className="px-4 py-2 text-xs font-extrabold rounded-xl text-white bg-gradient-to-r from-emerald-600 to-teal-600 hover:from-emerald-500 hover:to-teal-500 shadow-md shadow-emerald-500/20 transition-all flex items-center gap-2 cursor-pointer disabled:opacity-50"
              title="Save matrix edits and sync classification rules across all donor records"
            >
              {saving ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-white" />
                  <span>Saving & Syncing...</span>
                </>
              ) : (
                <>
                  <Save className="w-3.5 h-3.5 text-white" />
                  <span>Save Matrix & Sync</span>
                </>
              )}
            </button>
          )}

          {/* Export Dropdown */}
          <div className="flex items-center rounded-xl overflow-hidden border border-slate-200 dark:border-white/10 bg-slate-100 dark:bg-slate-800/60 shadow-sm">
            <button 
              onClick={() => handleExport('csv')}
              className="px-3 py-2 text-xs font-bold text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors flex items-center gap-1.5 cursor-pointer"
              title="Download Classification Rules as CSV"
            >
              <Download className="w-3.5 h-3.5 text-cyan-600 dark:text-cyan-400" />
              <span>CSV</span>
            </button>
            <div className="w-[1px] h-4 bg-slate-300 dark:bg-white/10"></div>
            <button 
              onClick={() => handleExport('xlsx')}
              className="px-3 py-2 text-xs font-bold text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors flex items-center gap-1.5 cursor-pointer"
              title="Download Classification Rules as Excel Spreadsheet"
            >
              <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-600 dark:text-emerald-400" />
              <span>Excel</span>
            </button>
          </div>
        </div>
      </div>

      {/* 🚀 Platform Selector Pill Buttons */}
      <div className="flex flex-wrap items-center gap-3">
        {/* LaunchGood Tab */}
        <button 
          onClick={() => handleSelectPlatform('launchgood')}
          className={`relative px-5 py-3 rounded-xl font-bold text-xs flex items-center gap-2.5 transition-all cursor-pointer ${
            platform === 'launchgood'
              ? 'bg-gradient-to-r from-teal-600 to-cyan-600 text-white shadow-md shadow-cyan-500/30 border border-cyan-400 ring-2 ring-cyan-400/40'
              : 'bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-900/60 dark:hover:bg-slate-800/80 dark:text-slate-300 border border-slate-300 dark:border-white/5'
          }`}
        >
          <Zap className={`w-4 h-4 ${platform === 'launchgood' ? 'text-white' : 'text-teal-600 dark:text-cyan-400'}`} />
          <span className="font-bold">LaunchGood Matrix</span>
          {platform === 'launchgood' && (
            <span className="flex h-2.5 w-2.5 relative ml-1">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
            </span>
          )}
        </button>

        {/* GiveBright Tab */}
        <button 
          onClick={() => handleSelectPlatform('givebright')}
          className={`relative px-5 py-3 rounded-xl font-bold text-xs flex items-center gap-2.5 transition-all cursor-pointer ${
            platform === 'givebright'
              ? 'bg-gradient-to-r from-purple-700 to-indigo-600 text-white shadow-md shadow-purple-500/30 border border-purple-400 ring-2 ring-purple-400/40'
              : 'bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-900/60 dark:hover:bg-slate-800/80 dark:text-slate-300 border border-slate-300 dark:border-white/5'
          }`}
        >
          <Gift className={`w-4 h-4 ${platform === 'givebright' ? 'text-white' : 'text-purple-600 dark:text-purple-400'}`} />
          <span className="font-bold">GiveBright Matrix</span>
          {platform === 'givebright' && (
            <span className="flex h-2.5 w-2.5 relative ml-1">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
            </span>
          )}
        </button>

        {/* Paysuite Tab */}
        <button 
          onClick={() => handleSelectPlatform('paysuite')}
          className={`relative px-5 py-3 rounded-xl font-bold text-xs flex items-center gap-2.5 transition-all cursor-pointer ${
            platform === 'paysuite'
              ? 'bg-gradient-to-r from-amber-600 to-orange-600 text-white shadow-md shadow-amber-500/30 border border-amber-400 ring-2 ring-amber-400/40'
              : 'bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-900/60 dark:hover:bg-slate-800/80 dark:text-slate-300 border border-slate-300 dark:border-white/5'
          }`}
        >
          <CreditCard className={`w-4 h-4 ${platform === 'paysuite' ? 'text-white' : 'text-amber-600 dark:text-amber-400'}`} />
          <span className="font-bold">Paysuite Matrix</span>
          {platform === 'paysuite' && (
            <span className="flex h-2.5 w-2.5 relative ml-1">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
            </span>
          )}
        </button>

        {/* Website Tab */}
        <button 
          onClick={() => handleSelectPlatform('website')}
          className={`relative px-5 py-3 rounded-xl font-bold text-xs flex items-center gap-2.5 transition-all cursor-pointer ${
            platform === 'website'
              ? 'bg-gradient-to-r from-blue-600 to-cyan-600 text-white shadow-md shadow-blue-500/30 border border-blue-400 ring-2 ring-blue-400/40'
              : 'bg-slate-100 hover:bg-slate-200 text-slate-700 dark:bg-slate-900/60 dark:hover:bg-slate-800/80 dark:text-slate-300 border border-slate-300 dark:border-white/5'
          }`}
        >
          <Globe className={`w-4 h-4 ${platform === 'website' ? 'text-white' : 'text-blue-600 dark:text-blue-400'}`} />
          <span className="font-bold">Website Matrix</span>
          {platform === 'website' && (
            <span className="flex h-2.5 w-2.5 relative ml-1">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-white opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-white"></span>
            </span>
          )}
        </button>
      </div>

      {/* 🎯 High-Contrast Active Matrix Banner Indicator */}
      <div className={`p-4 rounded-2xl border flex flex-wrap items-center justify-between gap-4 transition-all ${bStyles.container}`}>
        <div className="flex items-center gap-3.5">
          <span className={`p-2.5 rounded-xl shadow-sm ${bStyles.iconBg}`}>
            {platform === 'launchgood' ? <Zap className="w-5 h-5" /> :
             platform === 'givebright' ? <Gift className="w-5 h-5" /> :
             platform === 'paysuite' ? <CreditCard className="w-5 h-5" /> :
             <Globe className="w-5 h-5" />}
          </span>
          <div>
            <div className="text-xs uppercase tracking-wider flex items-center gap-2.5">
              <span className={bStyles.title}>
                ACTIVE MATRIX: {platform === 'launchgood' ? 'LaunchGood Campaign Master' : platform === 'givebright' ? 'GiveBright Campaign & URL Master' : platform === 'paysuite' ? 'Paysuite Direct Debit Master' : 'Rethink Website Project Master'}
              </span>
              <span className={`text-[10px] px-2.5 py-0.5 rounded-full font-extrabold uppercase shadow-sm ${bStyles.activePill}`}>
                ACTIVE
              </span>
            </div>
            <div className={`text-xs mt-0.5 ${bStyles.subtitle}`}>
              {platform === 'givebright'
                ? 'Hierarchy: Campaign Name & URL ➔ Code ➔ (Heading, Sub-Heading, Country, Zakat Eligibility)'
                : platform === 'paysuite'
                ? 'Hierarchy: Direct Debit Ref (Bank Ref) ➔ Code ➔ (Heading, Sub-Heading, Country, Zakat Eligibility)'
                : platform === 'website'
                ? 'Hierarchy: Project Name (Campaign) ➔ Appeal Name (Community) ➔ Location (Country)'
                : 'Hierarchy: Campaign Name ➔ Code ➔ (Heading, Sub-Heading, Country, Zakat Eligibility)'}
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <span className={`text-xs font-mono font-extrabold px-3.5 py-1.5 rounded-xl border shadow-sm ${bStyles.countPill}`}>
            {matrixData.total_campaigns?.toLocaleString()} Rules Active
          </span>
        </div>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className={`glass-panel p-4 border-l-4 ${platform === 'launchgood' ? 'border-teal-500 dark:border-cyan-400' : platform === 'givebright' ? 'border-purple-500 dark:border-purple-400' : platform === 'paysuite' ? 'border-amber-500 dark:border-amber-400' : 'border-blue-500 dark:border-blue-400'}`}>
          <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">
            {platform === 'paysuite' ? 'Total Tracked Direct Debits' : 'Unique Tracked Campaigns'}
          </div>
          <div className="text-2xl font-black text-slate-900 dark:text-white mt-1">{matrixData.total_campaigns?.toLocaleString()}</div>
        </div>
        <div className="glass-panel p-4 border-l-4 border-emerald-500 dark:border-emerald-400">
          <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">
            {platform === 'paysuite' ? 'Fully Classified Debits' : 'Fully Classified Campaigns'}
          </div>
          <div className="text-2xl font-black text-emerald-600 dark:text-emerald-400 mt-1">{matrixData.classified_campaigns?.toLocaleString()}</div>
        </div>
        <div className="glass-panel p-4 border-l-4 border-amber-500 dark:border-amber-400">
          <div className="text-xs font-bold text-slate-500 dark:text-slate-400 uppercase">
            {platform === 'paysuite' ? 'Unassigned Debits' : 'Unassigned Campaigns'}
          </div>
          <div className="text-2xl font-black text-amber-600 dark:text-amber-400 mt-1">{matrixData.unassigned_campaigns?.toLocaleString()}</div>
        </div>
      </div>

      {/* 🚀 Search, Filter & Quick Pagination Controls Bar */}
      <div className="glass-panel p-3.5 rounded-2xl border flex flex-wrap items-center justify-between gap-3 shadow-sm" style={{ borderColor: 'var(--border-glass)' }}>
        {/* Search Box */}
        <div className="relative flex-1 min-w-[260px] max-w-md">
          <Search className="w-4 h-4 text-slate-400 absolute left-3.5 top-1/2 -translate-y-1/2" />
          <input 
            type="text"
            value={searchQuery}
            onChange={e => setSearchQuery(e.target.value)}
            placeholder={`Search ${matrixData.total_campaigns?.toLocaleString() || 0} ${platform} rules (Name, Code, Country)...`}
            className="w-full pl-9 pr-8 py-2 rounded-xl text-xs border focus:outline-none focus:border-cyan-500 transition-all font-medium"
            style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', borderColor: 'var(--input-border)' }}
          />
          {searchQuery && (
            <button 
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200 p-1 cursor-pointer"
              title="Clear search"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>

        {/* Status Filter Badges */}
        <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-100 dark:bg-slate-900/60 border border-slate-200 dark:border-white/5">
          <button
            onClick={() => setStatusFilter('ALL')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              statusFilter === 'ALL'
                ? 'bg-cyan-500 text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
            }`}
          >
            All ({matrixData.total_campaigns?.toLocaleString() || 0})
          </button>
          <button
            onClick={() => setStatusFilter('CLASSIFIED')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              statusFilter === 'CLASSIFIED'
                ? 'bg-emerald-600 text-white shadow-sm'
                : 'text-emerald-600 dark:text-emerald-400 hover:bg-emerald-500/10'
            }`}
          >
            Classified ({matrixData.classified_campaigns?.toLocaleString() || 0})
          </button>
          <button
            onClick={() => setStatusFilter('UNASSIGNED')}
            className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all cursor-pointer ${
              statusFilter === 'UNASSIGNED'
                ? 'bg-amber-600 text-white shadow-sm'
                : 'text-amber-600 dark:text-amber-400 hover:bg-amber-500/10'
            }`}
          >
            Unassigned ({matrixData.unassigned_campaigns?.toLocaleString() || 0})
          </button>
        </div>

        {/* Rows Per Page Selector */}
        <div className="flex items-center gap-2">
          <span className="text-xs font-bold text-slate-500 dark:text-slate-400">Rows per page:</span>
          <select
            value={pageSize}
            onChange={e => setPageSize(e.target.value === 'All' ? 'All' : Number(e.target.value))}
            className="border rounded-xl px-2.5 py-1.5 text-xs font-bold focus:outline-none focus:border-cyan-500 transition-all cursor-pointer"
            style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', borderColor: 'var(--input-border)' }}
          >
            <option value={25}>25</option>
            <option value={50}>50</option>
            <option value={100}>100</option>
            <option value={250}>250</option>
          </select>
        </div>
      </div>

      {/* Matrix Rules Grid */}
      {loading ? (
        <div className="py-24 text-center text-slate-500 dark:text-slate-400 font-semibold animate-pulse flex flex-col items-center gap-3">
          <RefreshCw className="w-8 h-8 animate-spin text-teal-600 dark:text-cyan-400" />
          <span>⚡ Loading {platform.toUpperCase()} Classification Rules...</span>
        </div>
      ) : (
        <div className="glass-panel overflow-hidden border border-slate-200 dark:border-white/10 shadow-lg">
          <div className="overflow-x-auto max-h-[640px]">
            <datalist id="known-codes-list">
              {knownCodes.map((c, i) => <option key={i} value={c} />)}
            </datalist>

            <table className="crm-table w-full">
              <thead>
                <tr>
                  <th className="min-w-[200px] text-left">{platform === 'paysuite' ? 'Direct Debit Ref (Bank Ref)' : 'Campaign Name'}</th>
                  
                  {/* Paysuite: Donor Name and Email columns */}
                  {platform === 'paysuite' && (
                    <>
                      <th className="min-w-[120px] text-left">Donor Name</th>
                      <th className="min-w-[150px] text-left">Donor Email</th>
                    </>
                  )}

                  {/* LaunchGood & GiveBright: Campaign URL Column */}
                  {platform !== 'paysuite' && (
                    <th className="w-28 text-center">Campaign URL</th>
                  )}

                  {/* LaunchGood & Paysuite: Community Name column */}
                  {platform !== 'givebright' && (
                    <th className="min-w-[160px] text-left">{platform === 'paysuite' ? 'Platform Source' : 'Community Name'}</th>
                  )}
                  
                  <th className="w-36 text-left">Code (Master Link)</th>
                  <th className="min-w-[170px] text-left">Heading</th>
                  <th className="min-w-[190px] text-left">Sub-Heading</th>
                  <th className="min-w-[150px] text-left">Country</th>
                  <th className="w-40 text-left">Zakat Eligibility</th>
                  {isSuperAdmin && <th className="text-center w-16">Action</th>}
                </tr>
              </thead>
              <tbody>
                {paginatedRules.length === 0 ? (
                  <tr>
                    <td colSpan={platform === 'paysuite' ? 7 : 8} className="py-12 text-center text-slate-500 dark:text-slate-400 text-xs font-bold">
                      No classification rules match the active search or status filter.
                    </td>
                  </tr>
                ) : (
                  paginatedRules.map((r, idx) => {
                    const cKey = r['Campaign Name'] || r['campaign_name'];
                    return (
                      <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-cyan-500/5 transition-colors border-b border-slate-200 dark:border-white/5">
                        {/* Campaign Name */}
                        <td className="font-bold text-slate-800 dark:text-slate-100 text-xs py-2.5 px-3 min-w-[200px] max-w-[280px]" title={r['Campaign Name']}>
                          <div className="truncate font-bold text-slate-900 dark:text-slate-100">{r['Campaign Name']}</div>
                        </td>

                        {/* Paysuite: Donor Name and Email */}
                        {platform === 'paysuite' && (
                          <>
                            <td className="text-slate-600 dark:text-slate-400 text-xs py-2.5 px-3 min-w-[120px] max-w-[150px]" title={r['Donor Name']}>
                              <div className="truncate font-medium">{r['Donor Name'] || 'N/A'}</div>
                            </td>
                            <td className="text-slate-600 dark:text-slate-400 text-xs py-2.5 px-3 min-w-[150px] max-w-[200px]" title={r['Donor Email']}>
                              <div className="truncate font-medium">{r['Donor Email'] || 'N/A'}</div>
                            </td>
                          </>
                        )}

                        {/* LaunchGood & GiveBright: Clickable Campaign URL Cell */}
                        {platform !== 'paysuite' && (
                          <td className="py-2 px-2 text-center w-28">
                            {r['Campaign URL'] && r['Campaign URL'] !== '' && r['Campaign URL'] !== 'Unassigned' && r['Campaign URL'] !== 'None' ? (
                              <a 
                                href={r['Campaign URL'].startsWith('http') ? r['Campaign URL'] : `https://${r['Campaign URL']}`} 
                                target="_blank" 
                                rel="noreferrer" 
                                className="inline-flex items-center gap-1 px-2.5 py-1 bg-cyan-100 text-cyan-800 dark:bg-cyan-500/10 dark:text-cyan-400 hover:bg-cyan-200 dark:hover:bg-cyan-500/20 border border-cyan-300 dark:border-cyan-500/30 rounded-lg text-[11px] font-bold transition-all max-w-[110px] truncate shadow-sm"
                                title={r['Campaign URL']}
                              >
                                <ExternalLink className="w-3 h-3 shrink-0" />
                                <span className="truncate">Open Link</span>
                              </a>
                            ) : (
                              <input
                                type="text"
                                disabled={!isSuperAdmin}
                                value={r['Campaign URL'] || ''}
                                onChange={e => handleCellChange(cKey, 'Campaign URL', e.target.value)}
                                placeholder="Paste URL..."
                                className="bg-white dark:bg-slate-900/90 border border-slate-300 dark:border-white/10 rounded-lg px-2 py-1 text-[11px] text-slate-800 dark:text-slate-300 w-24 focus:outline-none focus:border-cyan-500 disabled:opacity-60 font-mono"
                                title="Paste or edit campaign URL"
                              />
                            )}
                          </td>
                        )}

                        {/* LaunchGood & Paysuite: Community Name Cell */}
                        {platform !== 'givebright' && (
                          <td className="text-slate-600 dark:text-slate-400 text-xs py-2.5 px-3 min-w-[160px] max-w-[220px]" title={r['Community Name']}>
                            <div className="truncate font-medium">{r['Community Name']}</div>
                          </td>
                        )}

                        {/* Editable Code with Datalist & Instant Auto-Fill */}
                        <td className="py-2 px-2 w-36">
                          <input 
                            type="text" 
                            list="known-codes-list"
                            disabled={!isSuperAdmin}
                            value={r['Code'] || ''} 
                            onChange={e => handleCellChange(cKey, 'Code', e.target.value)}
                            placeholder="Type Code..."
                            className="bg-white dark:bg-slate-900/90 border border-cyan-400 dark:border-cyan-500/40 rounded-lg px-2.5 py-1.5 text-xs font-mono text-cyan-800 dark:text-cyan-300 font-extrabold w-full focus:outline-none focus:border-cyan-500 disabled:opacity-60 uppercase shadow-sm"
                            title="Changing Code automatically auto-fills Heading, Sub-Heading, Country, and Zakat!"
                          />
                        </td>

                        {/* Editable Heading */}
                        <td className="py-2 px-2 min-w-[170px]">
                          <input 
                            type="text" 
                            disabled={!isSuperAdmin}
                            value={r['Heading'] || ''} 
                            onChange={e => handleCellChange(cKey, 'Heading', e.target.value)}
                            className="bg-white dark:bg-slate-900/90 border border-slate-300 dark:border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-slate-800 dark:text-slate-200 font-semibold w-full focus:outline-none focus:border-teal-500 dark:focus:border-cyan-400 disabled:opacity-60 shadow-sm"
                            title={r['Heading']}
                          />
                        </td>

                        {/* Editable Sub-Heading */}
                        <td className="py-2 px-2 min-w-[190px]">
                          <input 
                            type="text" 
                            disabled={!isSuperAdmin}
                            value={r['Sub-Heading'] || ''} 
                            onChange={e => handleCellChange(cKey, 'Sub-Heading', e.target.value)}
                            className="bg-white dark:bg-slate-900/90 border border-slate-300 dark:border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-purple-800 dark:text-purple-300 font-semibold w-full focus:outline-none focus:border-purple-500 dark:focus:border-purple-400 disabled:opacity-60 shadow-sm"
                            title={r['Sub-Heading']}
                          />
                        </td>

                        {/* Editable Country */}
                        <td className="py-2 px-2 min-w-[150px]">
                          <input 
                            type="text" 
                            disabled={!isSuperAdmin}
                            value={r['Country'] || ''} 
                            onChange={e => handleCellChange(cKey, 'Country', e.target.value)}
                            className="bg-white dark:bg-slate-900/90 border border-slate-300 dark:border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-emerald-800 dark:text-emerald-300 font-semibold w-full focus:outline-none focus:border-emerald-500 dark:focus:border-emerald-400 disabled:opacity-60 shadow-sm"
                            title={r['Country']}
                          />
                        </td>

                        {/* Editable Zakat Eligibility */}
                        <td className="py-2 px-2 w-40">
                          <select 
                            disabled={!isSuperAdmin}
                            value={r['Zakat Eligibility'] || 'Unassigned'} 
                            onChange={e => handleCellChange(cKey, 'Zakat Eligibility', e.target.value)}
                            className="bg-white dark:bg-slate-900/90 border border-slate-300 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs font-bold text-slate-800 dark:text-slate-200 w-full focus:outline-none focus:border-teal-500 dark:focus:border-cyan-400 disabled:opacity-60 cursor-pointer shadow-sm"
                          >
                            <option value="Unassigned">Unassigned</option>
                            <option value="Zakat">Zakat</option>
                            <option value="Non-Zakat">Non-Zakat</option>
                          </select>
                        </td>

                        {/* Super Admin Delete Single Rule Action */}
                        {isSuperAdmin && (
                          <td className="text-center py-2 px-2 w-16">
                            <button 
                              onClick={() => handleDeleteRule(r)}
                              className="p-1.5 text-rose-500 hover:text-rose-700 hover:bg-rose-500/10 rounded-lg transition-colors cursor-pointer"
                              title="Delete this classification rule"
                            >
                              <Trash2 className="w-4 h-4" />
                            </button>
                          </td>
                        )}
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>

          {/* 📑 Bottom Pagination Footer */}
          <div className="p-4 border-t border-slate-200 dark:border-white/10 flex flex-wrap items-center justify-between gap-4 bg-slate-50/50 dark:bg-slate-900/50">
            <div className="text-xs font-bold text-slate-500 dark:text-slate-400">
              {filteredRules.length === 0 ? (
                'No matching campaigns found'
              ) : (
                <>
                  Showing <span className="text-slate-900 dark:text-white font-black">{((safePage - 1) * effectivePageSize) + 1}</span> to <span className="text-slate-900 dark:text-white font-black">{Math.min(safePage * effectivePageSize, filteredRules.length)}</span> of <span className="text-cyan-600 dark:text-cyan-400 font-black">{filteredRules.length.toLocaleString()}</span> rules
                  {searchQuery && <span className="ml-1 text-[11px] text-slate-400 font-normal">(filtered from {matrixData.total_campaigns?.toLocaleString()} total)</span>}
                </>
              )}
            </div>

            {pageSize !== 'All' && totalPages > 1 && (
              <div className="flex items-center gap-2">
                {/* First Page */}
                <button
                  onClick={() => setCurrentPage(1)}
                  disabled={safePage === 1}
                  className="p-2 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-200 dark:hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all cursor-pointer text-slate-700 dark:text-slate-300"
                  title="First Page"
                >
                  <ChevronsLeft className="w-3.5 h-3.5" />
                </button>

                {/* Previous Page */}
                <button
                  onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                  disabled={safePage === 1}
                  className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-200 dark:hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all cursor-pointer text-xs font-bold flex items-center gap-1 text-slate-700 dark:text-slate-300"
                >
                  <ChevronLeft className="w-3.5 h-3.5" /> Prev
                </button>

                {/* Page Numbers */}
                <div className="flex items-center gap-1">
                  {Array.from({ length: Math.min(5, totalPages) }, (_, i) => {
                    let pNum;
                    if (totalPages <= 5) {
                      pNum = i + 1;
                    } else if (safePage <= 3) {
                      pNum = i + 1;
                    } else if (safePage >= totalPages - 2) {
                      pNum = totalPages - 4 + i;
                    } else {
                      pNum = safePage - 2 + i;
                    }
                    return (
                      <button
                        key={pNum}
                        onClick={() => setCurrentPage(pNum)}
                        className={`w-8 h-8 rounded-xl text-xs font-black transition-all cursor-pointer ${
                          safePage === pNum
                            ? 'bg-gradient-to-r from-teal-500 to-cyan-500 text-white shadow-md shadow-cyan-500/20 ring-2 ring-cyan-400/50'
                            : 'border border-slate-200 dark:border-white/10 hover:bg-slate-200 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
                        }`}
                      >
                        {pNum}
                      </button>
                    );
                  })}
                </div>

                {/* Next Page */}
                <button
                  onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                  disabled={safePage === totalPages}
                  className="px-3 py-1.5 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-200 dark:hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all cursor-pointer text-xs font-bold flex items-center gap-1 text-slate-700 dark:text-slate-300"
                >
                  Next <ChevronRight className="w-3.5 h-3.5" />
                </button>

                {/* Last Page */}
                <button
                  onClick={() => setCurrentPage(totalPages)}
                  disabled={safePage === totalPages}
                  className="p-2 rounded-xl border border-slate-200 dark:border-white/10 hover:bg-slate-200 dark:hover:bg-slate-800 disabled:opacity-30 disabled:cursor-not-allowed transition-all cursor-pointer text-slate-700 dark:text-slate-300"
                  title="Last Page"
                >
                  <ChevronsRight className="w-3.5 h-3.5" />
                </button>

                {/* Jump To Page */}
                <div className="flex items-center gap-1.5 ml-2 pl-2 border-l border-slate-200 dark:border-white/10">
                  <span className="text-xs text-slate-400 font-semibold">Go to:</span>
                  <input
                    type="number"
                    min={1}
                    max={totalPages}
                    value={jumpPage}
                    onChange={e => setJumpPage(e.target.value)}
                    onKeyDown={e => {
                      if (e.key === 'Enter') {
                        const val = Number(jumpPage);
                        if (val >= 1 && val <= totalPages) {
                          setCurrentPage(val);
                          setJumpPage('');
                        }
                      }
                    }}
                    placeholder={String(safePage)}
                    className="w-12 border rounded-lg px-1.5 py-1 text-xs text-center font-bold focus:outline-none focus:border-cyan-500"
                    style={{ backgroundColor: 'var(--input-bg)', color: 'var(--input-text)', borderColor: 'var(--input-border)' }}
                  />
                  <span className="text-xs text-slate-400">/ {totalPages}</span>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* 📂 Bulk Upload / Importer Modal */}
      {showImportModal && isSuperAdmin && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-fade-in">
          <div className="glass-panel p-6 max-w-lg w-full rounded-2xl border border-white/20 shadow-2xl relative bg-white dark:bg-slate-900">
            <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-white/10">
              <div className="flex items-center gap-2">
                <FileSpreadsheet className="w-5 h-5 text-purple-600 dark:text-purple-400" />
                <h3 className="text-base font-extrabold text-slate-900 dark:text-white">
                  Bulk Import {platform.toUpperCase()} Rules
                </h3>
              </div>
              <button 
                onClick={() => setShowImportModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleImportSubmit} className="mt-4 flex flex-col gap-4">
              <div className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                Upload a CSV or Excel file containing classification rules. Required headers include:
                <div className="mt-1.5 font-mono text-[11px] p-2 bg-slate-100 dark:bg-slate-800 rounded-lg text-slate-800 dark:text-slate-200">
                  {platform === 'paysuite' 
                    ? 'Direct Debit Ref (Bank Ref), Platform Source, Code, Heading, Sub-Heading, Country, Zakat Eligibility'
                    : 'Campaign Name, Community Name, Campaign URL, Code, Heading, Sub-Heading, Country, Zakat Eligibility'}
                </div>
              </div>

              {/* Import Mode Selection */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-slate-700 dark:text-slate-300">Import Strategy</label>
                <div className="grid grid-cols-2 gap-2">
                  <label className={`flex items-center gap-2 p-2.5 rounded-xl border text-xs font-semibold cursor-pointer transition-all ${
                    importMode === 'merge' 
                      ? 'bg-purple-500/10 border-purple-500/40 text-purple-700 dark:text-purple-300 font-bold' 
                      : 'border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-400'
                  }`}>
                    <input 
                      type="radio" 
                      name="importMode" 
                      value="merge" 
                      checked={importMode === 'merge'} 
                      onChange={() => setImportMode('merge')}
                      className="text-purple-600"
                    />
                    <span>Merge / Upsert (Recommended)</span>
                  </label>

                  <label className={`flex items-center gap-2 p-2.5 rounded-xl border text-xs font-semibold cursor-pointer transition-all ${
                    importMode === 'replace' 
                      ? 'bg-rose-500/10 border-rose-500/40 text-rose-700 dark:text-rose-300 font-bold' 
                      : 'border-slate-200 dark:border-white/10 text-slate-600 dark:text-slate-400'
                  }`}>
                    <input 
                      type="radio" 
                      name="importMode" 
                      value="replace" 
                      checked={importMode === 'replace'} 
                      onChange={() => setImportMode('replace')}
                      className="text-rose-600"
                    />
                    <span>Replace Entire Matrix</span>
                  </label>
                </div>
              </div>

              {/* File Input */}
              <div className="flex flex-col gap-1.5">
                <label className="text-xs font-bold text-slate-700 dark:text-slate-300">Choose File (.csv, .xlsx, .xls)</label>
                <input 
                  type="file" 
                  ref={fileInputRef}
                  accept=".csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet, application/vnd.ms-excel"
                  onChange={e => setImportFile(e.target.files[0] || null)}
                  className="text-xs border border-slate-300 dark:border-white/10 rounded-xl p-2 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 file:mr-3 file:py-1 file:px-3 file:rounded-lg file:border-0 file:text-xs file:font-bold file:bg-purple-600 file:text-white hover:file:bg-purple-700 cursor-pointer"
                />
              </div>

              {importMsg && (
                <div className={`p-3 rounded-xl text-xs font-bold ${
                  importMsg.includes('✅') 
                    ? 'bg-emerald-500/10 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30'
                    : 'bg-rose-500/10 text-rose-700 dark:text-rose-300 border border-rose-500/30'
                }`}>
                  {importMsg}
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-200 dark:border-white/10">
                <button
                  type="button"
                  onClick={() => setShowImportModal(false)}
                  className="px-4 py-2 text-xs font-bold text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-xl transition-colors cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={importing || !importFile}
                  className="px-4 py-2 text-xs font-bold bg-gradient-to-r from-purple-600 to-indigo-600 text-white rounded-xl shadow-lg shadow-purple-500/20 hover:opacity-90 disabled:opacity-50 flex items-center gap-2 cursor-pointer"
                >
                  {importing ? <RefreshCw className="w-3.5 h-3.5 animate-spin" /> : <Upload className="w-3.5 h-3.5" />}
                  <span>{importing ? 'Importing...' : 'Upload & Process'}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
