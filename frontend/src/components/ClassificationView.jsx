import React, { useEffect, useState } from 'react';
import { Shield, Save, CheckCircle, AlertCircle, RefreshCw } from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function ClassificationView({ user }) {
  const [platform, setPlatform] = useState('launchgood'); // 'launchgood' or 'givebright'
  const [matrixData, setMatrixData] = useState({ total_campaigns: 0, classified_campaigns: 0, unassigned_campaigns: 0, rules: [] });
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [saveMsg, setSaveMsg] = useState('');

  const loadMatrix = () => {
    setLoading(true);
    setSaveMsg('');
    fetch(`${API_BASE_URL}/api/classifications/${platform}`)
      .then(res => res.json())
      .then(data => {
        setMatrixData(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error loading classification matrix:', err);
        setLoading(false);
      });
  };

  useEffect(() => {
    loadMatrix();
  }, [platform]);

  const handleCellChange = (idx, field, value) => {
    const updatedRules = [...matrixData.rules];
    updatedRules[idx] = { ...updatedRules[idx], [field]: value };
    setMatrixData(prev => ({ ...prev, rules: updatedRules }));
  };

  const handleSave = () => {
    const canEditMatrix = user?.role === 'super_admin' || user?.can_edit_matrix === 1;
    if (!canEditMatrix) return;
    setSaving(true);
    setSaveMsg('');

    fetch(`${API_BASE_URL}/api/classifications/save`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role,
        can_edit_matrix: canEditMatrix,
        platform: platform,
        rules: matrixData.rules
      })
    })
      .then(r => r.json())
      .then(res => {
        setSaving(false);
        if (res?.status === 'success') {
          setSaveMsg(`✅ ${res.message}`);
          loadMatrix();
        } else {
          setSaveMsg(`❌ ${res?.detail || 'Failed to save rules.'}`);
        }
      })
      .catch(err => {
        setSaving(false);
        setSaveMsg(`❌ Error: ${err.message}`);
      });
  };

  const canEditMatrix = user?.role === 'super_admin' || user?.can_edit_matrix === 1;

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            <Shield className="w-5 h-5 text-cyan-400" /> Campaign Classification Manager (Source of Truth)
          </h2>
          <p className="text-xs text-slate-400">Map Campaign Name & Community Name ➔ Heading, Sub-Heading, Country, Code, and Zakat Eligibility.</p>
        </div>

        {canEditMatrix && (
          <button onClick={handleSave} disabled={saving} className="btn-primary text-xs flex items-center gap-1.5">
            <Save className="w-4 h-4" /> {saving ? 'Saving Rules...' : '💾 Save & Apply Rules Now'}
          </button>
        )}
      </div>

      {saveMsg && <div className="text-xs font-bold text-emerald-400">{saveMsg}</div>}

      {/* Platform Toggle Pills */}
      <div className="flex items-center gap-3">
        <button 
          onClick={() => setPlatform('launchgood')}
          className={`btn-secondary text-xs px-4 py-2 flex items-center gap-2 ${platform === 'launchgood' ? 'border-cyan-400 text-cyan-400 bg-cyan-500/10' : ''}`}
        >
          ⚡ LaunchGood Matrix
        </button>
        <button 
          onClick={() => setPlatform('givebright')}
          className={`btn-secondary text-xs px-4 py-2 flex items-center gap-2 ${platform === 'givebright' ? 'border-purple-400 text-purple-400 bg-purple-500/10' : ''}`}
        >
          🎁 GiveBright Matrix
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-panel p-4 border-l-4 border-cyan-400">
          <div className="text-xs font-bold text-slate-400 uppercase">Total Tracked Campaigns</div>
          <div className="text-2xl font-black text-white mt-1">{matrixData.total_campaigns?.toLocaleString()}</div>
        </div>
        <div className="glass-panel p-4 border-l-4 border-emerald-400">
          <div className="text-xs font-bold text-slate-400 uppercase">Fully Classified Campaigns</div>
          <div className="text-2xl font-black text-emerald-400 mt-1">{matrixData.classified_campaigns?.toLocaleString()}</div>
        </div>
        <div className="glass-panel p-4 border-l-4 border-amber-400">
          <div className="text-xs font-bold text-slate-400 uppercase">Unassigned Campaigns</div>
          <div className="text-2xl font-black text-amber-400 mt-1">{matrixData.unassigned_campaigns?.toLocaleString()}</div>
        </div>
      </div>

      {/* Matrix Rules Grid */}
      {loading ? (
        <div className="py-24 text-center text-slate-400 font-semibold animate-pulse">
          ⚡ Loading {platform.toUpperCase()} Classification Rules...
        </div>
      ) : (
        <div className="glass-panel overflow-hidden">
          <div className="overflow-x-auto max-h-[580px]">
            <table className="crm-table">
              <thead>
                <tr>
                  <th>Campaign Name</th>
                  <th>Community Name</th>
                  <th>Heading</th>
                  <th>Sub-Heading</th>
                  <th>Country</th>
                  <th>Code</th>
                  <th>Zakat Eligibility</th>
                </tr>
              </thead>
              <tbody>
                {matrixData.rules?.map((r, idx) => (
                  <tr key={idx} className="hover:bg-cyan-500/5 transition-colors">
                    <td className="font-bold text-slate-200 text-xs max-w-[200px] truncate" title={r['Campaign Name']}>{r['Campaign Name']}</td>
                    <td className="text-slate-400 text-xs max-w-[160px] truncate" title={r['Community Name']}>{r['Community Name']}</td>

                    {/* Editable Heading */}
                    <td className="p-1.5">
                      <input 
                        type="text" 
                        disabled={!canEditMatrix}
                        value={r['Heading'] || ''} 
                        onChange={e => handleCellChange(idx, 'Heading', e.target.value)}
                        className="bg-slate-900/90 border border-white/10 rounded px-2.5 py-1 text-xs text-cyan-400 font-semibold w-full focus:outline-none focus:border-cyan-400 disabled:opacity-60"
                      />
                    </td>

                    {/* Editable Sub-Heading */}
                    <td className="p-1.5">
                      <input 
                        type="text" 
                        disabled={!canEditMatrix}
                        value={r['Sub-Heading'] || ''} 
                        onChange={e => handleCellChange(idx, 'Sub-Heading', e.target.value)}
                        className="bg-slate-900/90 border border-white/10 rounded px-2.5 py-1 text-xs text-purple-300 font-medium w-full focus:outline-none focus:border-purple-400 disabled:opacity-60"
                      />
                    </td>

                    {/* Editable Country */}
                    <td className="p-1.5">
                      <input 
                        type="text" 
                        disabled={!canEditMatrix}
                        value={r['Country'] || ''} 
                        onChange={e => handleCellChange(idx, 'Country', e.target.value)}
                        className="bg-slate-900/90 border border-white/10 rounded px-2.5 py-1 text-xs text-emerald-300 w-full focus:outline-none focus:border-emerald-400 disabled:opacity-60"
                      />
                    </td>

                    {/* Editable Code */}
                    <td className="p-1.5">
                      <input 
                        type="text" 
                        disabled={!canEditMatrix}
                        value={r['Code'] || ''} 
                        onChange={e => handleCellChange(idx, 'Code', e.target.value)}
                        className="bg-slate-900/90 border border-white/10 rounded px-2.5 py-1 text-xs font-mono text-slate-300 w-24 focus:outline-none focus:border-slate-400 disabled:opacity-60"
                      />
                    </td>

                    {/* Editable Zakat Eligibility */}
                    <td className="p-1.5">
                      <select 
                        disabled={!canEditMatrix}
                        value={r['Zakat Eligibility'] || 'Unassigned'} 
                        onChange={e => handleCellChange(idx, 'Zakat Eligibility', e.target.value)}
                        className="bg-slate-900/90 border border-white/10 rounded px-2 py-1 text-xs font-bold text-slate-200 focus:outline-none focus:border-cyan-400 disabled:opacity-60"
                      >
                        <option value="Unassigned">Unassigned</option>
                        <option value="Zakat">Zakat</option>
                        <option value="Zakat Eligible">Zakat Eligible</option>
                        <option value="Non-Zakat">Non-Zakat</option>
                      </select>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
