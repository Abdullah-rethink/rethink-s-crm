import React, { useEffect, useState } from 'react';
import { Database, HardDrive, Server, Trash2, Edit, ShieldCheck, UserCheck, Key, Check, X, ShieldAlert, Sparkles, Mail, Save } from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function AdminView({ user }) {
  const [status, setStatus] = useState(null);
  const [tags, setTags] = useState([]);
  const [usersList, setUsersList] = useState([]);
  const [loading, setLoading] = useState(true);
  
  const [oldTag, setOldTag] = useState('');
  const [newTag, setNewTag] = useState('');
  const [msg, setMsg] = useState('');
  const [userMsg, setUserMsg] = useState('');

  const [approvalEmail, setApprovalEmail] = useState('');
  const [emailSaveMsg, setEmailSaveMsg] = useState('');

  const isSuperAdmin = user?.role === 'super_admin';
  const canManageTags = isSuperAdmin || user?.can_manage_tags === 1;
  const canPurgeData = isSuperAdmin || user?.can_purge_data === 1;

  const loadAdminData = () => {
    setLoading(true);
    Promise.all([
      fetch(`${API_BASE_URL}/api/admin/status`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/admin/tags`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/admin/users`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/expenses/settings`).then(r => r.json()),
    ]).then(([stData, tagData, uData, expSettings]) => {
      setStatus(stData);
      setTags(tagData);
      setUsersList(uData || []);
      if (expSettings?.approval_email) setApprovalEmail(expSettings.approval_email);
      if (tagData.length > 0) setOldTag(tagData[0].source_tag);
      setLoading(false);
    }).catch(err => {
      console.error('Error loading admin status:', err);
      setLoading(false);
    });
  };

  useEffect(() => {
    loadAdminData();
  }, []);

  const handleTogglePermission = (u, field) => {
    if (!isSuperAdmin) return;
    setUserMsg('');

    const updated = {
      user_role: user?.role,
      target_email: u.email,
      new_role: u.role,
      can_edit_donors: field === 'can_edit_donors' ? !u.can_edit_donors : Boolean(u.can_edit_donors),
      can_edit_matrix: field === 'can_edit_matrix' ? !u.can_edit_matrix : Boolean(u.can_edit_matrix),
      can_manage_tags: field === 'can_manage_tags' ? !u.can_manage_tags : Boolean(u.can_manage_tags),
      can_purge_data: field === 'can_purge_data' ? !u.can_purge_data : Boolean(u.can_purge_data),
    };

    fetch(`${API_BASE_URL}/api/admin/users/permissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updated)
    })
      .then(r => r.json())
      .then(res => {
        if (res?.status === 'success') {
          setUserMsg(`✅ ${res.message}`);
          loadAdminData();
        } else {
          setUserMsg(`❌ ${res.detail || 'Failed to update user permissions.'}`);
        }
      });
  };

  const handleAssignPreset = (targetEmail, presetName) => {
    if (!isSuperAdmin) return;
    setUserMsg('');

    fetch(`${API_BASE_URL}/api/admin/users/preset`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role,
        target_email: targetEmail,
        preset_name: presetName
      })
    })
      .then(r => r.json())
      .then(res => {
        if (res?.status === 'success') {
          setUserMsg(`✅ ${res.message}`);
          loadAdminData();
        } else {
          setUserMsg(`❌ ${res.detail || 'Failed to assign preset.'}`);
        }
      });
  };

  const handleRenameTag = (e) => {
    e.preventDefault();
    if (!canManageTags) return;

    fetch(`${API_BASE_URL}/api/admin/tags/rename`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role,
        old_tag: oldTag,
        new_tag: newTag
      })
    })
      .then(r => r.json())
      .then(res => {
        if (res?.status === 'success') {
          setMsg(`✅ ${res.message}`);
          setNewTag('');
          loadAdminData();
        } else {
          setMsg(`❌ ${res.detail || 'Failed to rename tag.'}`);
        }
      });
  };

  const handleDeleteTag = () => {
    if (!canManageTags) return;

    fetch(`${API_BASE_URL}/api/admin/tags/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role,
        tag_name: oldTag
      })
    })
      .then(r => r.json())
      .then(res => {
        if (res?.status === 'success') {
          setMsg(`✅ ${res.message}`);
          loadAdminData();
        } else {
          setMsg(`❌ ${res.detail || 'Failed to delete tag.'}`);
        }
      });
  };

  const handleSaveApprovalEmail = (e) => {
    e.preventDefault();
    if (!isSuperAdmin) return;
    setEmailSaveMsg('');

    fetch(`${API_BASE_URL}/api/expenses/settings`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        user_role: user?.role,
        approval_email: approvalEmail
      })
    })
      .then(r => r.json())
      .then(res => {
        if (res?.status === 'success') {
          setEmailSaveMsg(`✅ ${res.message}`);
          setTimeout(() => setEmailSaveMsg(''), 3000);
        } else {
          setEmailSaveMsg(`❌ ${res?.detail || 'Failed to update email.'}`);
        }
      });
  };

  const predefinedRoles = [
    {
      name: 'Super Admin',
      preset: 'super_admin',
      badge: 'badge-purple',
      desc: 'Full System Authority. Edit Donors, Classification Matrix, Tags, and Purge Database.',
      donors: true, matrix: true, tags: true, purge: true
    },
    {
      name: 'Data Editor',
      preset: 'data_editor',
      badge: 'badge-cyan',
      desc: 'Operations & Maintenance. Edit Donor Records & Classification Matrix rules. No tag delete or purge.',
      donors: true, matrix: true, tags: false, purge: false
    },
    {
      name: 'Standard Admin',
      preset: 'admin',
      badge: 'badge-emerald',
      desc: 'Read-Only Analyst. View dashboards, search donors, export CSV data. Zero write permissions.',
      donors: false, matrix: false, tags: false, purge: false
    }
  ];

  return (
    <div className="flex flex-col gap-6">
      <div>
        <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
          <Database className="w-5 h-5 text-cyan-400" /> System Settings & Access Control Management
        </h2>
        <p className="text-xs text-slate-400">Configure role-based access control (RBAC), assign permissions, inspect storage engines, and manage dataset tags.</p>
      </div>

      {/* System Status Widgets */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="glass-panel p-4 border-l-4 border-cyan-400">
          <div className="text-xs font-bold text-slate-400 uppercase">Total Loaded Records</div>
          <div className="text-2xl font-black text-cyan-400 mt-1">{status?.total_records?.toLocaleString()}</div>
          <div className="text-[11px] text-slate-500 mt-0.5">Parquet & SQLite Query Engine</div>
        </div>

        <div className="glass-panel p-4 border-l-4 border-emerald-400">
          <div className="text-xs font-bold text-slate-400 uppercase">Parquet Storage Size</div>
          <div className="text-2xl font-black text-emerald-400 mt-1">{status?.parquet_size}</div>
          <div className="text-[11px] text-slate-500 mt-0.5">Binary Columnar File Cache</div>
        </div>

        <div className="glass-panel p-4 border-l-4 border-emerald-400">
          <div className="text-xs font-bold text-slate-400 uppercase">Cloud Sync Status</div>
          <div className={`text-2xl font-black mt-1 ${status?.cloud_sync_status === 'ERROR' ? 'text-rose-400' : 'text-emerald-400'}`}>
            {status?.cloud_sync_status === 'SUCCESS' ? 'ACTIVE' : (status?.cloud_sync_status || 'ACTIVE')}
          </div>
          <div className="text-[11px] text-slate-500 mt-0.5">Relational Engine Connected</div>
        </div>
      </div>

      {/* Expense Approval Notification Email Settings Card */}
      <div className="glass-panel p-5 border-l-4 border-cyan-400 flex flex-col gap-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <div>
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <Mail className="w-4 h-4 text-cyan-400" /> Expense Approval Notification Email Settings
            </h3>
            <p className="text-xs text-slate-400">Configure the Super Admin email address that receives expense approval notification links.</p>
          </div>
          {emailSaveMsg && <div className="text-xs font-bold text-emerald-400">{emailSaveMsg}</div>}
        </div>

        <form onSubmit={handleSaveApprovalEmail} className="flex items-center gap-3 max-w-lg">
          <input 
            type="email" 
            required
            disabled={!isSuperAdmin}
            value={approvalEmail}
            onChange={e => setApprovalEmail(e.target.value)}
            className="bg-slate-900 border border-white/15 rounded-lg px-3 py-2 text-xs text-cyan-300 font-medium flex-1 focus:outline-none focus:border-cyan-400 disabled:opacity-50"
            placeholder="superadmin@analytics.com"
          />
          {isSuperAdmin && (
            <button type="submit" className="btn-primary text-xs flex items-center gap-1.5 whitespace-nowrap">
              <Save className="w-4 h-4" /> Save Email Settings
            </button>
          )}
        </form>
      </div>

      {/* Predefined RBAC Roles Matrix Table */}
      <div className="glass-panel p-5 border-l-4 border-purple-400 flex flex-col gap-4">
        <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-purple-400" /> Predefined Role-Based Access Matrix Table
        </h3>

        <div className="overflow-x-auto">
          <table className="crm-table">
            <thead>
              <tr>
                <th>Role Profile</th>
                <th>Description</th>
                <th>Edit Donors</th>
                <th>Edit Matrix</th>
                <th>Manage Tags</th>
                <th>Purge Data</th>
              </tr>
            </thead>
            <tbody>
              {predefinedRoles.map((r, idx) => (
                <tr key={idx}>
                  <td>
                    <span className={`badge ${r.badge}`}>{r.name}</span>
                  </td>
                  <td className="text-xs text-slate-400 max-w-[280px]">{r.desc}</td>
                  <td>{r.donors ? <span className="text-emerald-400 font-bold text-xs flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Allowed</span> : <span className="text-slate-500 text-xs flex items-center gap-1"><X className="w-3.5 h-3.5" /> Restricted</span>}</td>
                  <td>{r.matrix ? <span className="text-emerald-400 font-bold text-xs flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Allowed</span> : <span className="text-slate-500 text-xs flex items-center gap-1"><X className="w-3.5 h-3.5" /> Restricted</span>}</td>
                  <td>{r.tags ? <span className="text-emerald-400 font-bold text-xs flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Allowed</span> : <span className="text-slate-500 text-xs flex items-center gap-1"><X className="w-3.5 h-3.5" /> Restricted</span>}</td>
                  <td>{r.purge ? <span className="text-emerald-400 font-bold text-xs flex items-center gap-1"><Check className="w-3.5 h-3.5" /> Allowed</span> : <span className="text-slate-500 text-xs flex items-center gap-1"><X className="w-3.5 h-3.5" /> Restricted</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* User Accounts & Granular Permission Assign/Revoke Section */}
      <div className="glass-panel p-5 border-l-4 border-cyan-400 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Key className="w-4 h-4 text-cyan-400" /> User Accounts & Access Control Settings
          </h3>

          {!isSuperAdmin && (
            <span className="badge badge-amber text-[10px]">🔒 Read-Only Access (Super Admin Only)</span>
          )}
        </div>

        {userMsg && <div className="text-xs font-bold text-emerald-400">{userMsg}</div>}

        <div className="overflow-x-auto">
          <table className="crm-table">
            <thead>
              <tr>
                <th>User Identity</th>
                <th>Role</th>
                <th>Edit Donors</th>
                <th>Edit Matrix</th>
                <th>Manage Tags</th>
                <th>Purge Data</th>
                <th>Assign Predefined Role</th>
              </tr>
            </thead>
            <tbody>
              {usersList.map((u, idx) => (
                <tr key={idx}>
                  <td className="font-bold text-slate-200">
                    <div>{u.email}</div>
                    <div className="text-[10px] text-slate-500 font-normal">@{u.username}</div>
                  </td>
                  <td>
                    <span className={`badge ${u.role === 'super_admin' ? 'badge-purple' : u.role === 'data_editor' ? 'badge-cyan' : 'badge-emerald'}`}>
                      {u.role}
                    </span>
                  </td>

                  {/* Toggle Granular Permissions */}
                  <td className="text-center">
                    <button 
                      disabled={!isSuperAdmin || u.role === 'super_admin'}
                      onClick={() => handleTogglePermission(u, 'can_edit_donors')}
                      className={`btn-secondary text-[11px] px-2.5 py-1 ${u.can_edit_donors || u.role === 'super_admin' ? 'text-emerald-400 border-emerald-500/30' : 'text-slate-500'}`}
                    >
                      {u.can_edit_donors || u.role === 'super_admin' ? '✓ YES' : '✗ NO'}
                    </button>
                  </td>

                  <td className="text-center">
                    <button 
                      disabled={!isSuperAdmin || u.role === 'super_admin'}
                      onClick={() => handleTogglePermission(u, 'can_edit_matrix')}
                      className={`btn-secondary text-[11px] px-2.5 py-1 ${u.can_edit_matrix || u.role === 'super_admin' ? 'text-emerald-400 border-emerald-500/30' : 'text-slate-500'}`}
                    >
                      {u.can_edit_matrix || u.role === 'super_admin' ? '✓ YES' : '✗ NO'}
                    </button>
                  </td>

                  <td className="text-center">
                    <button 
                      disabled={!isSuperAdmin || u.role === 'super_admin'}
                      onClick={() => handleTogglePermission(u, 'can_manage_tags')}
                      className={`btn-secondary text-[11px] px-2.5 py-1 ${u.can_manage_tags || u.role === 'super_admin' ? 'text-emerald-400 border-emerald-500/30' : 'text-slate-500'}`}
                    >
                      {u.can_manage_tags || u.role === 'super_admin' ? '✓ YES' : '✗ NO'}
                    </button>
                  </td>

                  <td className="text-center">
                    <button 
                      disabled={!isSuperAdmin || u.role === 'super_admin'}
                      onClick={() => handleTogglePermission(u, 'can_purge_data')}
                      className={`btn-secondary text-[11px] px-2.5 py-1 ${u.can_purge_data || u.role === 'super_admin' ? 'text-emerald-400 border-emerald-500/30' : 'text-slate-500'}`}
                    >
                      {u.can_purge_data || u.role === 'super_admin' ? '✓ YES' : '✗ NO'}
                    </button>
                  </td>

                  {/* Quick Preset Assignment */}
                  <td>
                    <div className="flex gap-1">
                      <button 
                        disabled={!isSuperAdmin}
                        onClick={() => handleAssignPreset(u.email, 'super_admin')}
                        className="btn-secondary text-[10px] px-2 py-1 text-purple-400 hover:bg-purple-500/20"
                      >
                        Super Admin
                      </button>
                      <button 
                        disabled={!isSuperAdmin}
                        onClick={() => handleAssignPreset(u.email, 'data_editor')}
                        className="btn-secondary text-[10px] px-2 py-1 text-cyan-400 hover:bg-cyan-500/20"
                      >
                        Data Editor
                      </button>
                      <button 
                        disabled={!isSuperAdmin}
                        onClick={() => handleAssignPreset(u.email, 'admin')}
                        className="btn-secondary text-[10px] px-2 py-1 text-emerald-400 hover:bg-emerald-500/20"
                      >
                        Analyst
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Dataset Tag Manager */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="glass-panel p-5 border-l-4 border-amber-400 flex flex-col gap-4">
          <h3 className="text-sm font-bold text-slate-200">🏷️ Active Dataset Source Tags ({tags.length})</h3>

          <div className="overflow-x-auto">
            <table className="crm-table">
              <thead>
                <tr>
                  <th>Source Tag</th>
                  <th>Record Count</th>
                </tr>
              </thead>
              <tbody>
                {tags.map((t, idx) => (
                  <tr key={idx}>
                    <td className="font-bold text-slate-200">{t.source_tag}</td>
                    <td className="font-semibold text-cyan-400">{t.record_count?.toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        {/* Tag Operations */}
        <div className="glass-panel p-5 border-l-4 border-cyan-400 flex flex-col gap-4">
          <h3 className="text-sm font-bold text-slate-200">✏️ Tag Operations & Batch Management</h3>

          {!canManageTags ? (
            <div className="p-4 rounded-xl bg-slate-900/60 border border-white/5 text-xs text-slate-400">
              🔒 <b>Read-Only Access:</b> Dataset tag renaming and dataset batch deletions are restricted to authorized accounts with <b>Manage Tags</b> permission.
            </div>
          ) : (
            <form onSubmit={handleRenameTag} className="flex flex-col gap-3">
              <div>
                <label className="text-xs text-slate-400 font-bold mb-1 block">Select Dataset Tag</label>
                <select 
                  value={oldTag} 
                  onChange={e => setOldTag(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-xl p-2 text-xs text-white"
                >
                  {tags.map((t, idx) => <option key={idx} value={t.source_tag}>{t.source_tag}</option>)}
                </select>
              </div>

              <div>
                <label className="text-xs text-slate-400 font-bold mb-1 block">New Corrected Tag Name</label>
                <input 
                  type="text"
                  placeholder="e.g. Ramadan 2025"
                  value={newTag}
                  onChange={e => setNewTag(e.target.value)}
                  className="w-full bg-slate-900 border border-white/10 rounded-xl p-2 text-xs text-white"
                />
              </div>

              <div className="flex gap-2 mt-2">
                <button type="submit" className="btn-primary text-xs flex-1">✏️ Rename Selected Tag</button>
                <button type="button" onClick={handleDeleteTag} className="btn-secondary text-xs hover:bg-rose-500/20 hover:text-rose-400">🗑️ Delete Batch</button>
              </div>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
