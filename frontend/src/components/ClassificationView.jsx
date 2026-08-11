import React, { useEffect, useState, useRef } from 'react';
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
  CreditCard
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
  };

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
  const handleCellChange = (idx, field, value) => {
    if (!isSuperAdmin) return;
    const updatedRules = [...matrixData.rules];
    const currentRow = { ...updatedRules[idx], [field]: cleanText(value) };

    // When Code changes, automatically resolve & fill Heading, Sub-Heading, Country, and Zakat!
    if (field === 'Code' && value) {
      const codeKey = value.trim().toLowerCase();
      if (codeMap[codeKey]) {
        const info = codeMap[codeKey];
        if (info.Heading && info.Heading !== 'Unassigned') currentRow['Heading'] = info.Heading;
        if (info['Sub-Heading'] && info['Sub-Heading'] !== 'Unassigned') currentRow['Sub-Heading'] = info['Sub-Heading'];
        if (info.Country && info.Country !== 'Unassigned') currentRow['Country'] = info.Country;
        if (info['Zakat Eligibility'] && info['Zakat Eligibility'] !== 'Unassigned') currentRow['Zakat Eligibility'] = info['Zakat Eligibility'];
      }
    }

    updatedRules[idx] = currentRow;
    setMatrixData(prev => ({ ...prev, rules: updatedRules }));
  };

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
          setPlatform(p => p);
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

  const handleClearPlatform = async () => {
    if (!isSuperAdmin) return;
    if (!window.confirm(`🚨 DANGER: Are you sure you want to completely DELETE ALL classification rules for ${platform.toUpperCase()}?\n\nAll matching donor records will be reset to Unassigned.`)) {
      return;
    }

    try {
      const res = await fetch(`${API_BASE_URL}/api/classifications/clear-platform`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          user_role: user?.role,
          platform: platform
        })
      });
      const data = await res.json();
      if (data?.status === 'success') {
        setSaveMsg(`🗑️ ${data.message}`);
        setMatrixData({ total_campaigns: 0, classified_campaigns: 0, unassigned_campaigns: 0, rules: [] });
      } else {
        setSaveMsg(`❌ ${data?.detail || 'Failed to clear rules.'}`);
      }
    } catch (err) {
      setSaveMsg(`❌ Error: ${err.message}`);
    }
  };

  const handleExportClassifications = (format) => {
    window.open(`${API_BASE_URL}/api/classifications/export?platform=${platform}&format=${format}`, '_blank');
  };

  const handleImportSubmit = async (e) => {
    e.preventDefault();
    if (!isSuperAdmin || !importFile) return;
    setImporting(true);
    setImportMsg('');

    const formData = new FormData();
    formData.append('file', importFile);
    formData.append('platform', platform);
    formData.append('user_role', user?.role || 'admin');
    formData.append('mode', importMode);

    try {
      const res = await fetch(`${API_BASE_URL}/api/classifications/import`, {
        method: 'POST',
        body: formData
      });
      const data = await res.json();
      setImporting(false);
      if (data?.status === 'success') {
        setSaveMsg(`✅ ${data.message}`);
        setShowImportModal(false);
        setImportFile(null);
        setLoading(true);
        fetch(`${API_BASE_URL}/api/classifications/${platform}`)
          .then(r => r.json())
          .then(d => {
            setMatrixData(d);
            setLoading(false);
          });
      } else {
        setImportMsg(`❌ ${data?.detail || 'Failed to import file.'}`);
      }
    } catch (err) {
      setImporting(false);
      setImportMsg(`❌ Error: ${err.message}`);
    }
  };

  const knownCodes = Object.keys(codeMap).map(k => k.toUpperCase());

  // Dynamic Theme Palette Resolver for LaunchGood / GiveBright / Paysuite
  const getBannerStyles = () => {
    if (platform === 'launchgood') {
      return {
        container: 'bg-teal-50 border-teal-300 dark:bg-cyan-950/40 dark:border-cyan-500/40 shadow-sm',
        iconBg: 'bg-teal-600 dark:bg-cyan-500 text-white dark:text-slate-950',
        title: 'text-teal-950 dark:text-cyan-100 font-extrabold',
        subtitle: 'text-teal-800 dark:text-cyan-300 font-medium',
        activePill: 'bg-teal-600 text-white dark:bg-cyan-400 dark:text-slate-950',
        countPill: 'bg-teal-100/90 text-teal-900 border-teal-300 dark:bg-slate-900/90 dark:text-cyan-300 dark:border-cyan-500/30'
      };
    } else if (platform === 'givebright') {
      return {
        container: 'bg-purple-50 border-purple-300 dark:bg-purple-950/40 dark:border-purple-500/40 shadow-sm',
        iconBg: 'bg-purple-600 dark:bg-purple-500 text-white dark:text-slate-950',
        title: 'text-purple-950 dark:text-purple-100 font-extrabold',
        subtitle: 'text-purple-800 dark:text-purple-300 font-medium',
        activePill: 'bg-purple-600 text-white dark:bg-purple-400 dark:text-slate-950',
        countPill: 'bg-purple-100/90 text-purple-900 border-purple-300 dark:bg-slate-900/90 dark:text-purple-300 dark:border-purple-500/30'
      };
    } else {
      return {
        container: 'bg-amber-50 border-amber-300 dark:bg-amber-950/40 dark:border-amber-500/40 shadow-sm',
        iconBg: 'bg-amber-600 dark:bg-amber-500 text-white dark:text-slate-950',
        title: 'text-amber-950 dark:text-amber-100 font-extrabold',
        subtitle: 'text-amber-800 dark:text-amber-300 font-medium',
        activePill: 'bg-amber-600 text-white dark:bg-amber-400 dark:text-slate-950',
        countPill: 'bg-amber-100/90 text-amber-900 border-amber-300 dark:bg-slate-900/90 dark:text-amber-300 dark:border-amber-500/30'
      };
    }
  };

  const bStyles = getBannerStyles();

  return (
    <div className="flex flex-col gap-6">
      {/* Header Banner */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-extrabold text-slate-900 dark:text-white flex items-center gap-2">
            <Shield className="w-5 h-5 text-cyan-600 dark:text-cyan-400" /> Campaign Classification Manager (Source of Truth)
          </h2>
          <p className="text-xs text-slate-600 dark:text-slate-400">
            Define classification rules per platform. Changing a project code automatically populates headings, country, and Zakat eligibility.
          </p>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {/* Export Dropdown Group */}
          <div className="flex items-center gap-1 bg-white dark:bg-slate-900/90 border border-emerald-500/40 p-1 rounded-xl shadow-sm">
            <button 
              onClick={() => handleExportClassifications('csv')}
              className="text-xs font-bold text-emerald-700 dark:text-emerald-400 hover:bg-emerald-500/10 px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition-all"
              title="Export classification matrix as CSV"
            >
              <Download className="w-3.5 h-3.5" /> CSV
            </button>
            <span className="text-slate-300 dark:text-white/20 text-xs">|</span>
            <button 
              onClick={() => handleExportClassifications('xlsx')}
              className="text-xs font-bold text-emerald-700 dark:text-emerald-400 hover:bg-emerald-500/10 px-2.5 py-1.5 rounded-lg flex items-center gap-1 transition-all"
              title="Export classification matrix as Excel (.xlsx)"
            >
              <Download className="w-3.5 h-3.5" /> Excel (.xlsx)
            </button>
          </div>

          {/* Super Admin Action Controls */}
          {isSuperAdmin ? (
            <>
              {/* Import / Bulk Upload Button */}
              <button 
                onClick={() => { setShowImportModal(true); setImportMsg(''); }}
                className="btn-secondary text-xs px-3 py-2 flex items-center gap-1.5 border-purple-500/40 text-purple-700 dark:text-purple-300 hover:bg-purple-500/10 shadow-sm"
                title={`Upload CSV/Excel to bulk assign rules for ${platform.toUpperCase()}`}
              >
                <Upload className="w-3.5 h-3.5 text-purple-600 dark:text-purple-400" /> 📂 Import Rules
              </button>

              {/* Clear All Platform Rules Button */}
              <button 
                onClick={handleClearPlatform}
                className="btn-secondary text-xs px-3 py-2 flex items-center gap-1.5 border-rose-500/40 text-rose-600 dark:text-rose-400 hover:bg-rose-500/10 shadow-sm"
                title={`Delete all classification rules for ${platform.toUpperCase()}`}
              >
                <Trash2 className="w-3.5 h-3.5" /> Clear All Rules
              </button>

              {/* Save & Apply Rules Button */}
              <button 
                onClick={handleSave} 
                disabled={saving} 
                className="btn-primary text-xs flex items-center gap-1.5 shadow-lg shadow-cyan-500/10"
              >
                <Save className="w-4 h-4" /> {saving ? 'Saving Rules...' : '💾 Save & Apply Rules Now'}
              </button>
            </>
          ) : (
            <div className="flex items-center gap-1.5 px-3 py-1.5 bg-slate-100 dark:bg-slate-800/80 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-400 text-xs rounded-xl">
              <Lock className="w-3.5 h-3.5 text-amber-500 dark:text-amber-400" /> Read-Only Mode
            </div>
          )}
        </div>
      </div>

      {/* RBAC Notice for Non-Super-Admin */}
      {!isSuperAdmin && (
        <div className="bg-amber-500/10 border border-amber-500/30 text-amber-700 dark:text-amber-400 p-3 rounded-xl text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>
            <strong>Read-Only Access:</strong> Logged in as <strong>{user?.email || 'Admin'}</strong>. Modifying rules, bulk imports, and deleting classifications are restricted to <strong>Super Admin</strong> accounts.
          </span>
        </div>
      )}

      {saveMsg && <div className="text-xs font-bold text-emerald-800 dark:text-emerald-400 bg-emerald-500/10 border border-emerald-500/30 p-2.5 rounded-xl shadow-lg">{saveMsg}</div>}

      {/* 🌟 3-Segment Platform Selector with High-Contrast Light & Dark Styling */}
      <div className="glass-panel p-2 flex flex-wrap items-center gap-3 border border-slate-200 dark:border-white/10 shadow-lg rounded-2xl bg-white/70 dark:bg-slate-900/60">
        {/* LaunchGood Tab */}
        <button 
          onClick={() => handleSelectPlatform('launchgood')}
          className={`relative px-5 py-3 rounded-xl font-bold text-xs flex items-center gap-2.5 transition-all cursor-pointer ${
            platform === 'launchgood'
              ? 'bg-gradient-to-r from-teal-600 to-cyan-600 text-white shadow-md shadow-cyan-500/30 border border-teal-400 ring-2 ring-cyan-400/40'
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
      </div>

      {/* 🎯 High-Contrast Active Matrix Banner Indicator */}
      <div className={`p-4 rounded-2xl border flex flex-wrap items-center justify-between gap-4 transition-all ${bStyles.container}`}>
        <div className="flex items-center gap-3.5">
          <span className={`p-2.5 rounded-xl shadow-sm ${bStyles.iconBg}`}>
            {platform === 'launchgood' ? <Zap className="w-5 h-5" /> :
             platform === 'givebright' ? <Gift className="w-5 h-5" /> :
             <CreditCard className="w-5 h-5" />}
          </span>
          <div>
            <div className="text-xs uppercase tracking-wider flex items-center gap-2.5">
              <span className={bStyles.title}>
                ACTIVE MATRIX: {platform === 'launchgood' ? 'LaunchGood Campaign Master' : platform === 'givebright' ? 'GiveBright Campaign & URL Master' : 'Paysuite Direct Debit Master'}
              </span>
              <span className={`text-[10px] px-2.5 py-0.5 rounded-full font-extrabold uppercase shadow-sm ${bStyles.activePill}`}>
                ACTIVE
              </span>
            </div>
            <div className={`text-xs mt-0.5 ${bStyles.subtitle}`}>
              {platform === 'givebright'
                ? 'Hierarchy: Campaign Name ➔ Code ➔ (Heading, Sub-Heading, Country, Zakat Eligibility) with Campaign URLs'
                : 'Hierarchy: Campaign Name & Community Name ➔ Code ➔ (Heading, Sub-Heading, Country, Zakat Eligibility)'}
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
        <div className={`glass-panel p-4 border-l-4 ${platform === 'launchgood' ? 'border-teal-500 dark:border-cyan-400' : platform === 'givebright' ? 'border-purple-500 dark:border-purple-400' : 'border-amber-500 dark:border-amber-400'}`}>
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
                  
                  {/* GiveBright ONLY: Campaign URL Column */}
                  {platform === 'givebright' && (
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
                {matrixData.rules?.map((r, idx) => (
                  <tr key={idx} className="hover:bg-slate-50 dark:hover:bg-cyan-500/5 transition-colors border-b border-slate-200 dark:border-white/5">
                    {/* Campaign Name */}
                    <td className="font-bold text-slate-800 dark:text-slate-100 text-xs py-2.5 px-3 min-w-[200px] max-w-[280px]" title={r['Campaign Name']}>
                      <div className="truncate font-bold text-slate-900 dark:text-slate-100">{r['Campaign Name']}</div>
                    </td>

                    {/* GiveBright ONLY: Clickable Campaign URL Cell */}
                    {platform === 'givebright' && (
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
                            onChange={e => handleCellChange(idx, 'Campaign URL', e.target.value)}
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
                        onChange={e => handleCellChange(idx, 'Code', e.target.value)}
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
                        onChange={e => handleCellChange(idx, 'Heading', e.target.value)}
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
                        onChange={e => handleCellChange(idx, 'Sub-Heading', e.target.value)}
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
                        onChange={e => handleCellChange(idx, 'Country', e.target.value)}
                        className="bg-white dark:bg-slate-900/90 border border-slate-300 dark:border-white/10 rounded-lg px-2.5 py-1.5 text-xs text-emerald-800 dark:text-emerald-300 font-semibold w-full focus:outline-none focus:border-emerald-500 dark:focus:border-emerald-400 disabled:opacity-60 shadow-sm"
                        title={r['Country']}
                      />
                    </td>

                    {/* Editable Zakat Eligibility */}
                    <td className="py-2 px-2 w-40">
                      <select 
                        disabled={!isSuperAdmin}
                        value={r['Zakat Eligibility'] || 'Unassigned'} 
                        onChange={e => handleCellChange(idx, 'Zakat Eligibility', e.target.value)}
                        className="bg-white dark:bg-slate-900/90 border border-slate-300 dark:border-white/10 rounded-lg px-2 py-1.5 text-xs font-bold text-slate-800 dark:text-slate-200 w-full focus:outline-none focus:border-teal-500 dark:focus:border-cyan-400 disabled:opacity-60 cursor-pointer shadow-sm"
                      >
                        <option value="Unassigned">Unassigned</option>
                        <option value="Zakat">Zakat</option>
                        <option value="Zakat Eligible">Zakat Eligible</option>
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
                ))}
              </tbody>
            </table>
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
                  Bulk Import {platform === 'givebright' ? 'GiveBright' : platform === 'paysuite' ? 'Paysuite' : 'LaunchGood'} Rules
                </h3>
              </div>
              <button 
                onClick={() => { setShowImportModal(false); setImportFile(null); setImportMsg(''); }}
                className="text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors cursor-pointer"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form onSubmit={handleImportSubmit} className="flex flex-col gap-4 mt-4">
              <p className="text-xs text-slate-600 dark:text-slate-300">
                Upload a <strong>.csv</strong> or <strong>.xlsx</strong> spreadsheet. Column headers (<code className="text-cyan-700 dark:text-cyan-300 font-bold">Campaign Name</code>, <code className="text-cyan-700 dark:text-cyan-300 font-bold">Code</code>, <code className="text-cyan-700 dark:text-cyan-300 font-bold">Heading</code>, <code className="text-cyan-700 dark:text-cyan-300 font-bold">Sub-Heading</code>, <code className="text-cyan-700 dark:text-cyan-300 font-bold">Country</code>, <code className="text-cyan-700 dark:text-cyan-300 font-bold">Zakat Eligibility</code>) are automatically mapped.
              </p>

              {/* File Dropzone */}
              <div 
                onClick={() => fileInputRef.current?.click()}
                className="border-2 border-dashed border-purple-500/40 hover:border-purple-500 bg-purple-500/5 hover:bg-purple-500/10 rounded-xl p-6 text-center cursor-pointer transition-all flex flex-col items-center gap-2"
              >
                <Upload className="w-8 h-8 text-purple-600 dark:text-purple-400" />
                <div className="text-xs font-bold text-slate-900 dark:text-white">
                  {importFile ? importFile.name : 'Click to select CSV or Excel file'}
                </div>
                <div className="text-[11px] text-slate-500 dark:text-slate-400">
                  {importFile ? `${(importFile.size / 1024).toFixed(1)} KB` : 'Supports .csv, .xlsx, .xls'}
                </div>
                <input 
                  type="file" 
                  ref={fileInputRef} 
                  onChange={e => setImportFile(e.target.files?.[0] || null)}
                  accept=".csv,.xlsx,.xls" 
                  className="hidden" 
                />
              </div>

              {/* Import Mode Options */}
              <div className="flex flex-col gap-1.5 bg-slate-100 dark:bg-slate-900/60 p-3 rounded-xl border border-slate-200 dark:border-white/5">
                <label className="text-xs font-bold text-slate-800 dark:text-slate-300">Import Mode:</label>
                <div className="flex items-center gap-4">
                  <label className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
                    <input 
                      type="radio" 
                      name="importMode" 
                      value="merge" 
                      checked={importMode === 'merge'} 
                      onChange={() => setImportMode('merge')} 
                    />
                    Merge / Update Existing Rules
                  </label>
                  <label className="flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300 cursor-pointer">
                    <input 
                      type="radio" 
                      name="importMode" 
                      value="replace" 
                      checked={importMode === 'replace'} 
                      onChange={() => setImportMode('replace')} 
                    />
                    Replace Platform Matrix
                  </label>
                </div>
              </div>

              {importMsg && (
                <div className="text-xs font-bold text-rose-600 dark:text-rose-400 bg-rose-500/10 border border-rose-500/30 p-2.5 rounded-xl">
                  {importMsg}
                </div>
              )}

              {/* Modal Buttons */}
              <div className="flex items-center justify-end gap-3 pt-2">
                <button 
                  type="button" 
                  onClick={() => { setShowImportModal(false); setImportFile(null); }}
                  className="btn-secondary text-xs px-4 py-2 cursor-pointer"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  disabled={!importFile || importing}
                  className="btn-primary text-xs px-5 py-2 flex items-center gap-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-500 hover:to-indigo-500 cursor-pointer text-white"
                >
                  {importing ? (
                    <>
                      <RefreshCw className="w-3.5 h-3.5 animate-spin" /> Importing...
                    </>
                  ) : (
                    <>
                      <Upload className="w-3.5 h-3.5" /> Import & Apply Rules
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
