import React from 'react';
import { Zap, LogOut, User, ShieldCheck, Sun, Moon, TrendingUp, Gift, Layers, DollarSign, Activity } from 'lucide-react';

export default function Navbar({ user, metrics, theme, onToggleTheme, onSignOut }) {
  const roleBadge = user?.role === 'super_admin' ? '⚡ SUPER ADMIN' : '👤 ADMIN';

  const formatCompactCurrency = (value) => {
    const amount = Number(value || 0);
    if (Math.abs(amount) >= 1_000_000) return `£${(amount / 1_000_000).toFixed(2)}M`;
    if (Math.abs(amount) >= 1_000) return `£${(amount / 1_000).toFixed(1)}K`;
    return `£${amount.toFixed(2)}`;
  };

  return (
    <header className="sticky top-0 z-40 w-full backdrop-blur-xl bg-slate-900/80 border-b border-white/10 shadow-2xl transition-all">
      <div className="max-w-7xl mx-auto px-6 py-3.5 flex flex-wrap items-center justify-between gap-4">
        
        {/* Left: Brand Identity & Live Sync Status */}
        <div className="flex items-center gap-3.5">
          <div className="relative group">
            <div className="absolute -inset-0.5 bg-gradient-to-r from-cyan-500 to-blue-600 rounded-2xl blur opacity-60 group-hover:opacity-100 transition duration-300"></div>
            <div className="relative w-11 h-11 rounded-2xl bg-slate-950 flex items-center justify-center text-cyan-400 font-black shadow-xl">
              <Zap className="w-6 h-6 fill-current animate-pulse" />
            </div>
          </div>

          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base font-black tracking-tight text-white flex items-center gap-2">
                Crowdfunding Intelligence CRM
              </h1>
              <span className="text-[10px] font-extrabold px-2 py-0.5 rounded-full bg-gradient-to-r from-cyan-500/20 to-blue-500/20 text-cyan-300 border border-cyan-400/30 shadow-sm">
                v2.0 Enterprise
              </span>
            </div>
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <span className="flex items-center gap-1.5 text-[11px] font-medium text-emerald-400">
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping inline-block" />
                Live Sync Active
              </span>
              <span className="text-slate-600">•</span>
              <span className="text-[11px]">360° Analytics Engine</span>
            </div>
          </div>
        </div>

        {/* Center: Live Executive KPI Metrics Dashboard */}
        {metrics && (
          <div className="hidden xl:flex items-center gap-2.5 bg-slate-950/60 p-1.5 rounded-2xl border border-white/10 shadow-inner">
            {/* Total Raised */}
            <div className="px-3.5 py-1.5 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-cyan-500/20 flex items-center justify-center text-cyan-400">
                <TrendingUp className="w-4 h-4" />
              </div>
              <div>
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Total Raised</div>
                <div className="text-xs font-black text-cyan-300 font-mono">{formatCompactCurrency(metrics.total_raised)}</div>
              </div>
            </div>

            {/* Gift Aid Estimate */}
            <div className="px-3.5 py-1.5 rounded-xl bg-amber-500/10 border border-amber-500/20 flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-amber-500/20 flex items-center justify-center text-amber-400">
                <Gift className="w-4 h-4" />
              </div>
              <div>
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Gift Aid (+25%)</div>
                <div className="text-xs font-black text-amber-300 font-mono">{formatCompactCurrency(metrics.gift_aid_estimate)}</div>
              </div>
            </div>

            {/* Total Donations */}
            <div className="px-3.5 py-1.5 rounded-xl bg-purple-500/10 border border-purple-500/20 flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-purple-500/20 flex items-center justify-center text-purple-400">
                <Layers className="w-4 h-4" />
              </div>
              <div>
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Donations</div>
                <div className="text-xs font-black text-purple-300 font-mono">{metrics.total_txns?.toLocaleString() || 0}</div>
              </div>
            </div>

            {/* Avg Donation */}
            <div className="px-3.5 py-1.5 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center gap-2.5">
              <div className="w-7 h-7 rounded-lg bg-emerald-500/20 flex items-center justify-center text-emerald-400">
                <DollarSign className="w-4 h-4" />
              </div>
              <div>
                <div className="text-[10px] font-bold text-slate-400 uppercase tracking-wider">Avg Donation</div>
                <div className="text-xs font-black text-emerald-300 font-mono">{formatCompactCurrency(metrics.avg_donation)}</div>
              </div>
            </div>
          </div>
        )}

        {/* Right: User Profile & Actions */}
        <div className="flex items-center gap-3">
          {/* Theme Toggle Button */}
          <button 
            onClick={onToggleTheme}
            title={`Switch to ${theme === 'dark' ? 'Light Mode' : 'Dark Mode'}`}
            className="p-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 border border-white/10 text-slate-200 text-xs font-bold transition-all flex items-center gap-1.5 shadow-md active:scale-95"
          >
            {theme === 'dark' ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-400" />}
            <span className="hidden sm:inline text-xs">{theme === 'dark' ? 'Light' : 'Dark'}</span>
          </button>

          {/* User Account Badge */}
          <div className="flex items-center gap-2.5 px-3 py-1.5 rounded-xl bg-slate-950/70 border border-white/10 shadow-md">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-cyan-500 to-blue-500 flex items-center justify-center text-slate-950 font-bold shadow-sm">
              <User className="w-4 h-4" />
            </div>
            <div className="text-left min-w-0">
              <div className="text-xs font-extrabold text-white truncate max-w-[140px]">
                {user?.email || user?.username || 'Admin'}
              </div>
              <span className="text-[9px] font-black uppercase text-cyan-400 tracking-wider block">
                {roleBadge}
              </span>
            </div>
          </div>

          {/* Sign Out Button */}
          <button 
            onClick={onSignOut}
            title="Sign Out of Session"
            className="p-2.5 sm:px-3.5 sm:py-2.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 text-xs font-bold transition-all flex items-center gap-1.5 active:scale-95 shadow-md"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Sign Out</span>
          </button>
        </div>

      </div>
    </header>
  );
}
