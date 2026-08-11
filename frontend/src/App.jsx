import React, { useEffect, useState } from 'react';
import Navbar from './components/Navbar';
import Sidebar from './components/Sidebar';
import OverviewView from './components/OverviewView';
import LtvView from './components/LtvView';
import KanbanBoard from './components/KanbanBoard';
import ExplorerView from './components/ExplorerView';
import ClassificationView from './components/ClassificationView';
import ExpenseView from './components/ExpenseView';
import AdminView from './components/AdminView';
import TrackerView from './components/TrackerView';
import DonorDrawer from './components/DonorDrawer';
import LoginView from './components/LoginView';

import { TrendingUp, Crown, Columns, Table, Shield, CreditCard, Database, Target, Gift, Layers, DollarSign } from 'lucide-react';

import { API_BASE_URL } from './config';

const INITIAL_FILTERS = {
  payment_type: 'All Payment Types',
  tier: 'All Classifications',
  source: 'All Sources (Combined)',
  heading: 'All Headings',
  subheading: 'All Sub-Headings',
  country: 'All Project Countries',
  code: 'All Codes',
  zakat: 'All Zakat Status',
  donor_country: 'All Donor Countries',
  campaign_search: '',
  gift_aid: 'All Gift Aid Status',
  start_date: '',
  end_date: ''
};

export default function App() {
  const [user, setUser] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedDonor, setSelectedDonor] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [filters, setFilters] = useState(INITIAL_FILTERS);

  const [theme, setTheme] = useState(() => {
    const savedTheme = localStorage.getItem('crm_theme');
    if (savedTheme === 'light' || savedTheme === 'dark') return savedTheme;
    return window.matchMedia('(prefers-color-scheme: light)').matches ? 'light' : 'dark';
  });

  const handleSignOut = () => {
    setUser(null);
    localStorage.removeItem('analytics_user');
  };

  // Auto-restore session from localStorage
  useEffect(() => {
    const savedUser = localStorage.getItem('analytics_user');
    if (savedUser) {
      try {
        const parsed = JSON.parse(savedUser);
        
        // 1. Check Session Expiry (24 hours = 86400000 ms)
        const EXPIRY_MS = 24 * 60 * 60 * 1000;
        if (parsed.login_timestamp && (Date.now() - parsed.login_timestamp > EXPIRY_MS)) {
          console.warn("Session expired after 24 hours.");
          handleSignOut();
          return;
        }

        // Set user immediately for offline responsiveness
        setUser(parsed);

        // 2. Real-time verification & permission sync with backend
        fetch(`${API_BASE_URL}/api/auth/me?user_identity=${parsed.email || parsed.username}`)
          .then(res => {
            if (res.status === 401 || res.status === 404) {
              throw new Error('Invalid user session');
            }
            return res.json();
          })
          .then(data => {
            if (data.status === 'success' && data.user) {
              const updatedUser = {
                ...data.user,
                login_timestamp: parsed.login_timestamp || Date.now()
              };
              setUser(updatedUser);
              localStorage.setItem('analytics_user', JSON.stringify(updatedUser));
            } else {
              handleSignOut();
            }
          })
          .catch(err => {
            if (err.message === 'Invalid user session') {
              handleSignOut();
            }
          });
      } catch (e) {
        console.error("Error restoring session:", e);
        handleSignOut();
      }
    }
  }, []);

  // Update theme class on HTML root element
  useEffect(() => {
    document.documentElement.classList.remove('theme-light', 'theme-dark');
    document.documentElement.classList.add(theme === 'light' ? 'theme-light' : 'theme-dark');
    document.documentElement.style.colorScheme = theme;
    localStorage.setItem('crm_theme', theme);
  }, [theme]);

  const handleToggleTheme = () => {
    setTheme(prev => (prev === 'dark' ? 'light' : 'dark'));
  };

  // Fetch Live Summary Metrics
  useEffect(() => {
    if (!user) return;
    const params = new URLSearchParams();
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
      if (filters.gift_aid) params.append('gift_aid', filters.gift_aid);
      if (filters.start_date) params.append('start_date', filters.start_date);
      if (filters.end_date) params.append('end_date', filters.end_date);
    }
    fetch(`${API_BASE_URL}/api/metrics/summary?${params.toString()}`)
      .then(res => res.json())
      .then(data => setMetrics(data))
      .catch(err => console.error('Error fetching metrics summary:', err));
  }, [user, filters]);

  const handleFilterChange = (key, value) => {
    setFilters(prev => ({ ...prev, [key]: value }));
  };

  const handleResetFilters = () => {
    setFilters(INITIAL_FILTERS);
  };

  const handleLoginSuccess = (userData) => {
    const sessionData = {
      ...userData,
      login_timestamp: Date.now()
    };
    setUser(sessionData);
    localStorage.setItem('analytics_user', JSON.stringify(sessionData));
  };

  if (!user) {
    return <LoginView theme={theme} onToggleTheme={handleToggleTheme} onLoginSuccess={handleLoginSuccess} />;
  }

  const tabs = [
    { id: 'overview', label: 'Overview', icon: TrendingUp },
    { id: 'ltv', label: 'Lifetime LTV', icon: Crown },
    { id: 'kanban', label: 'Kanban Pipeline', icon: Columns },
    { id: 'explorer', label: 'Data Explorer', icon: Table },
    { id: 'tracker', label: 'Sponsorship Tracker', icon: Target },
    { id: 'classifications', label: 'Classifications', icon: Shield },
    { id: 'expenses', label: 'Expenses', icon: CreditCard },
    { id: 'admin', label: 'Admin & Data', icon: Database },
  ];

  return (
    <div className="min-h-screen flex flex-col pb-12">
      {/* Top Navbar */}
      <Navbar user={user} theme={theme} onToggleTheme={handleToggleTheme} onSignOut={handleSignOut} />

      {/* Main Container with Left Sidebar Layout */}
      <main className="px-6 max-w-7xl mx-auto w-full flex flex-col gap-6 pt-4">
        {/* Executive Summary Metrics Header Cards Bar - ALWAYS VISIBLE */}
        {metrics && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            {/* Total Raised */}
            <div className="glass-panel p-4 border-l-4 border-cyan-400 flex flex-col gap-1 relative overflow-hidden group hover:border-cyan-300 transition-all shadow-lg">
              <div className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400">Total Raised</div>
              <div className="text-2xl font-black text-cyan-400 font-mono tracking-tight">
                £{Number(metrics.total_raised || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="absolute right-3 top-3 opacity-10 group-hover:opacity-20 transition-opacity">
                <TrendingUp className="w-10 h-10 text-cyan-400" />
              </div>
            </div>

            {/* Gift Aid Estimate */}
            <div className="glass-panel p-4 border-l-4 border-amber-400 flex flex-col gap-1 relative overflow-hidden group hover:border-amber-300 transition-all shadow-lg">
              <div className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400">Gift Aid Estimate</div>
              <div className="text-2xl font-black text-amber-400 font-mono tracking-tight">
                £{Number(metrics.gift_aid_estimate || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="absolute right-3 top-3 opacity-10 group-hover:opacity-20 transition-opacity">
                <Gift className="w-10 h-10 text-amber-400" />
              </div>
            </div>

            {/* Donations Count */}
            <div className="glass-panel p-4 border-l-4 border-purple-400 flex flex-col gap-1 relative overflow-hidden group hover:border-purple-300 transition-all shadow-lg">
              <div className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400">Donations</div>
              <div className="text-2xl font-black text-purple-400 font-mono tracking-tight">
                {Number(metrics.total_txns || 0).toLocaleString()}
              </div>
              <div className="absolute right-3 top-3 opacity-10 group-hover:opacity-20 transition-opacity">
                <Layers className="w-10 h-10 text-purple-400" />
              </div>
            </div>

            {/* Avg Donation */}
            <div className="glass-panel p-4 border-l-4 border-emerald-400 flex flex-col gap-1 relative overflow-hidden group hover:border-emerald-300 transition-all shadow-lg">
              <div className="text-[11px] font-extrabold uppercase tracking-wider text-slate-400">Avg Donation</div>
              <div className="text-2xl font-black text-emerald-400 font-mono tracking-tight">
                £{Number(metrics.avg_donation || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
              </div>
              <div className="absolute right-3 top-3 opacity-10 group-hover:opacity-20 transition-opacity">
                <DollarSign className="w-10 h-10 text-emerald-400" />
              </div>
            </div>
          </div>
        )}
        {/* Navigation Tabs Bar */}
        <div className="glass-panel p-2 flex items-center gap-2 overflow-x-auto">
          {tabs.map(t => {
            const Icon = t.icon;
            const isActive = activeTab === t.id;
            return (
              <button
                key={t.id}
                onClick={() => setActiveTab(t.id)}
                className={`btn-secondary text-xs px-4 py-2.5 flex items-center gap-2 rounded-xl transition-all whitespace-nowrap ${
                  isActive 
                    ? 'border-cyan-400 text-cyan-400 bg-cyan-500/10 font-bold shadow-lg shadow-cyan-500/10' 
                    : 'hover:text-white'
                }`}
              >
                <Icon className="w-4 h-4" /> {t.label}
              </button>
            );
          })}
        </div>

        {/* Workspace Grid with Left Sidebar */}
        <div className="flex flex-col lg:flex-row gap-6 items-start">
          {/* Left Panel Sidebar Filters */}
          <Sidebar 
            filters={filters} 
            onFilterChange={handleFilterChange} 
            onResetFilters={handleResetFilters} 
          />

          {/* Active Tab Main Content */}
          <div className="flex-1 w-full min-w-0">
            {activeTab === 'overview' && <OverviewView filters={filters} />}
            {activeTab === 'ltv' && <LtvView filters={filters} />}
            {activeTab === 'kanban' && <KanbanBoard filters={filters} onSelectDonor={setSelectedDonor} />}
            {activeTab === 'explorer' && <ExplorerView user={user} filters={filters} onSelectDonor={setSelectedDonor} />}
            {activeTab === 'tracker' && <TrackerView user={user} filters={filters} onSelectDonor={setSelectedDonor} />}
            {activeTab === 'classifications' && <ClassificationView user={user} />}
            {activeTab === 'expenses' && <ExpenseView user={user} />}
            {activeTab === 'admin' && <AdminView user={user} />}
          </div>
        </div>
      </main>

      {/* Donor 360° Profile Drawer Modal */}
      <DonorDrawer donorId={selectedDonor} onClose={() => setSelectedDonor(null)} />
    </div>
  );
}
