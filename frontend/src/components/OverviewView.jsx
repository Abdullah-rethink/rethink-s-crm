import React, { useEffect, useState } from 'react';
import { TrendingUp, PieChart, Award, Tag } from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function OverviewView({ filters }) {
  const [timeline, setTimeline] = useState([]);
  const [headings, setHeadings] = useState([]);
  const [campaigns, setCampaigns] = useState([]);
  const [subheadings, setSubheadings] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
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
    }
    const queryStr = params.toString() ? `?${params.toString()}` : '';

    Promise.all([
      fetch(`${API_BASE_URL}/api/overview/timeline${queryStr}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/overview/headings${queryStr}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/overview/campaigns${queryStr}`).then(r => r.json()),
      fetch(`${API_BASE_URL}/api/overview/subheadings${queryStr}`).then(r => r.json()),
    ]).then(([timeData, headData, campData, subData]) => {
      setTimeline(timeData);
      setHeadings(headData);
      setCampaigns(campData);
      setSubheadings(subData);
      setLoading(false);
    }).catch(err => {
      console.error('Error loading overview data:', err);
      setLoading(false);
    });
  }, [filters]);

  if (loading) {
    return (
      <div className="py-24 text-center text-slate-400 font-semibold animate-pulse">
        ⚡ Loading Executive Overview Analytics...
      </div>
    );
  }

  const maxCampaignRaised = campaigns.length > 0 ? Math.max(...campaigns.map(c => c.total_raised)) : 1;

  return (
    <div className="flex flex-col gap-6">
      {/* Section Header */}
      <div>
        <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
          <TrendingUp className="w-5 h-5 text-cyan-400" /> Executive Overview & Campaign Dynamics
        </h2>
        <p className="text-xs text-slate-400">High-level fundraising performance, category trends, and campaign leaderboards.</p>
      </div>

      {/* Row 1: Timeline & Category Distribution */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Timeline Panel */}
        <div className="glass-panel p-5 border-l-4 border-cyan-400 lg:col-span-2 flex flex-col gap-4">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
              <TrendingUp className="w-4 h-4 text-cyan-400" /> Fundraising Volume & Daily Timeline (UTC)
            </h3>
            <span className="badge badge-cyan">{timeline.length} Days Tracked</span>
          </div>

          <div className="flex flex-col gap-2 max-h-[300px] overflow-y-auto pr-1">
            {timeline.slice(-10).reverse().map((item, idx) => (
              <div key={idx} className="flex items-center justify-between text-xs py-2 px-3 rounded-lg bg-slate-800/40 border border-white/5">
                <span className="text-slate-400 font-semibold">{item.date}</span>
                <span className="text-slate-400">{item.donation_count} donations</span>
                <span className="font-extrabold text-cyan-400">£{item.total_raised?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
              </div>
            ))}
          </div>
        </div>

        {/* Category Distribution Panel */}
        <div className="glass-panel p-5 border-l-4 border-purple-400 flex flex-col gap-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <PieChart className="w-4 h-4 text-purple-400" /> Top Categories (Headings)
          </h3>

          <div className="flex flex-col gap-2.5">
            {headings.map((cat, idx) => (
              <div key={idx} className="flex flex-col gap-1">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-slate-300 truncate max-w-[160px]">{cat.category}</span>
                  <span className="text-purple-400 font-bold">£{cat.total_raised?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-purple-500 to-pink-500 rounded-full"
                    style={{ width: `${(cat.total_raised / (headings[0]?.total_raised || 1)) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Row 2: Top Campaigns & Sub-Headings */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top Campaigns */}
        <div className="glass-panel p-5 border-l-4 border-emerald-400 flex flex-col gap-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Award className="w-4 h-4 text-emerald-400" /> Top 10 Campaigns by Total Raised
          </h3>

          <div className="flex flex-col gap-3">
            {campaigns.map((camp, idx) => (
              <div key={idx} className="flex flex-col gap-1">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-slate-200 truncate max-w-[280px]">{camp.campaign}</span>
                  <span className="text-emerald-400 font-extrabold">£{camp.total_raised?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-emerald-500 to-teal-400 rounded-full"
                    style={{ width: `${(camp.total_raised / maxCampaignRaised) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* Sub-Heading Performance */}
        <div className="glass-panel p-5 border-l-4 border-pink-400 flex flex-col gap-4">
          <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
            <Tag className="w-4 h-4 text-pink-400" /> Sub-Heading Performance
          </h3>

          <div className="flex flex-col gap-3">
            {subheadings.map((sub, idx) => (
              <div key={idx} className="flex flex-col gap-1">
                <div className="flex items-center justify-between text-xs font-semibold">
                  <span className="text-slate-200 truncate max-w-[280px]">{sub.sub_heading}</span>
                  <span className="text-pink-400 font-extrabold">£{sub.total_raised?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                </div>
                <div className="w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                  <div 
                    className="h-full bg-gradient-to-r from-pink-500 to-purple-500 rounded-full"
                    style={{ width: `${(sub.total_raised / (subheadings[0]?.total_raised || 1)) * 100}%` }}
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
