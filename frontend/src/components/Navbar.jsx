import React from 'react';
import { Zap, LogOut, User, ShieldCheck, Sun, Moon } from 'lucide-react';

export default function Navbar({ user, metrics, theme, onToggleTheme, onSignOut }) {
  const roleBadge = user?.role === 'super_admin' ? '⚡ SUPER ADMIN' : '👤 ADMIN';

  return (
    <header className="glass-panel sticky top-0 z-40 px-6 py-3 mb-6 flex flex-wrap items-center justify-between gap-4 border-b border-white/10 rounded-none rounded-b-2xl">
      {/* Brand Logo */}
      <div className="flex items-center gap-3">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center text-slate-950 font-black shadow-lg shadow-cyan-500/20">
          <Zap className="w-6 h-6 fill-current" />
        </div>
        <div>
          <h1 className="text-lg font-extrabold tracking-tight text-white flex items-center gap-2">
            Crowdfunding Analytics Engine <span className="text-xs px-2 py-0.5 rounded-md bg-cyan-500/10 text-cyan-400 border border-cyan-500/30">v2.0 CRM</span>
          </h1>
          <p className="text-xs text-slate-400 font-medium">Unified Intelligence & Donor Lifetime Value Platform</p>
        </div>
      </div>

      {/* Live Header Metrics Cards View */}
      {metrics && (
        <div className="hidden lg:flex items-center gap-3">
          <div className="glass-panel px-3.5 py-1.5 border-l-2 border-cyan-400">
            <div className="text-[10px] uppercase font-bold text-slate-400">Total Raised</div>
            <div className="text-sm font-extrabold text-cyan-400">£{metrics.total_raised?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) || '0.00'}</div>
          </div>
          <div className="glass-panel px-3.5 py-1.5 border-l-2 border-purple-400">
            <div className="text-[10px] uppercase font-bold text-slate-400">Donations</div>
            <div className="text-sm font-extrabold text-purple-400">{metrics.total_txns?.toLocaleString() || 0}</div>
          </div>
          <div className="glass-panel px-3.5 py-1.5 border-l-2 border-emerald-400">
            <div className="text-[10px] uppercase font-bold text-slate-400">Avg Donation</div>
            <div className="text-sm font-extrabold text-emerald-400">£{metrics.avg_donation?.toFixed(2) || '0.00'}</div>
          </div>
        </div>
      )}

      {/* User Account Status & Theme Switcher & Sign Out */}
      <div className="flex items-center gap-3">
        {/* Theme Toggle Button */}
        <button 
          onClick={onToggleTheme}
          title={`Switch to ${theme === 'dark' ? 'Light Mode' : 'Dark Mode'}`}
          className="p-2 rounded-xl bg-slate-800/80 border border-white/10 text-slate-300 hover:text-cyan-400 hover:bg-slate-700 transition-all flex items-center gap-1.5 text-xs font-bold"
        >
          {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-400" />}
          <span className="hidden sm:inline">{theme === 'dark' ? 'Light Theme' : 'Dark Theme'}</span>
        </button>

        <div className="glass-panel px-3 py-1.5 flex items-center gap-2">
          <div className="w-7 h-7 rounded-full bg-slate-800 flex items-center justify-center text-cyan-400 font-bold border border-white/10">
            <User className="w-4 h-4" />
          </div>
          <div className="text-left">
            <div className="text-xs font-bold text-slate-200">{user?.email || user?.username || 'User'}</div>
            <span className="badge badge-cyan text-[9px] py-0 px-1.5">{roleBadge}</span>
          </div>
        </div>

        <button 
          onClick={onSignOut}
          title="Sign Out"
          className="btn-secondary text-xs flex items-center gap-1.5 text-rose-400 border-rose-500/30 hover:bg-rose-500/10"
        >
          <LogOut className="w-4 h-4" /> Sign Out
        </button>
      </div>
    </header>
  );
}
