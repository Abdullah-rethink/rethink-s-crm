import React from 'react';
import { Zap, LogOut, User, Sun, Moon } from 'lucide-react';

export default function Navbar({ user, theme, onToggleTheme, onSignOut }) {
  const roleBadge = user?.role === 'super_admin' ? '⚡ SUPER ADMIN' : '👤 ADMIN';

  return (
    <header className="sticky top-0 z-40 w-full backdrop-blur-xl bg-slate-900/80 border-b border-white/10 shadow-2xl transition-all">
      <div className="max-w-7xl mx-auto px-6 py-3.5 flex items-center justify-between gap-4">
        
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

        {/* Right: User Profile & Actions */}
        <div className="flex items-center gap-3">
          {/* Theme Toggle Button */}
          <button 
            onClick={onToggleTheme}
            title={`Switch to ${theme === 'dark' ? 'Light Mode' : 'Dark Mode'}`}
            className="p-2.5 rounded-xl bg-slate-800/80 hover:bg-slate-700/80 border border-white/10 text-slate-200 text-xs font-bold transition-all flex items-center gap-1.5 shadow-md active:scale-95 cursor-pointer"
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
            className="p-2.5 sm:px-3.5 sm:py-2.5 rounded-xl bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 text-rose-400 text-xs font-bold transition-all flex items-center gap-1.5 active:scale-95 shadow-md cursor-pointer"
          >
            <LogOut className="w-4 h-4" />
            <span className="hidden sm:inline">Sign Out</span>
          </button>
        </div>

      </div>
    </header>
  );
}
