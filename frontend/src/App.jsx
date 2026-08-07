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
import DonorDrawer from './components/DonorDrawer';
import LoginView from './components/LoginView';

import { TrendingUp, Crown, Columns, Table, Shield, CreditCard, Database } from 'lucide-react';

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
  gift_aid: 'All Gift Aid Status'
};

export default function App() {
  const [user, setUser] = useState(null);
  const [activeTab, setActiveTab] = useState('overview');
  const [selectedDonor, setSelectedDonor] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [filters, setFilters] = useState(INITIAL_FILTERS);

  const [theme, setTheme] = useState(() => localStorage.getItem('crm_theme') || 'dark');

  // Auto-restore session from localStorage
  useEffect(() => {
    const savedUser = localStorage.getItem('analytics_user');
    if (savedUser) {
      try {
        setUser(JSON.parse(savedUser));
      } catch (e) {
        console.error(e);
      }
    }
  }, []);

  // Update theme class on HTML root element
  useEffect(() => {
    document.documentElement.className = theme === 'light' ? 'theme-light' : 'theme-dark';
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
    setUser(userData);
    localStorage.setItem('analytics_user', JSON.stringify(userData));
  };

  const handleSignOut = () => {
    setUser(null);
    localStorage.removeItem('analytics_user');
  };

  if (!user) {
    return <LoginView onLoginSuccess={handleLoginSuccess} />;
  }

  const tabs = [
    { id: 'overview', label: '📈 Overview', icon: TrendingUp },
    { id: 'ltv', label: '👑 Lifetime LTV', icon: Crown },
    { id: 'kanban', label: '📋 Kanban Pipeline', icon: Columns },
    { id: 'explorer', label: '📊 Data Explorer', icon: Table },
    { id: 'classifications', label: '🏷️ Classifications', icon: Shield },
    { id: 'expenses', label: '💳 Expenses', icon: CreditCard },
    { id: 'admin', label: '⚙️ Admin & Data', icon: Database },
  ];

  return (
    <div className="min-h-screen flex flex-col pb-12">
      {/* Top Navbar */}
      <Navbar user={user} metrics={metrics} theme={theme} onToggleTheme={handleToggleTheme} onSignOut={handleSignOut} />

      {/* Main Container with Left Sidebar Layout */}
      <main className="px-6 max-w-7xl mx-auto w-full flex flex-col gap-6">
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
