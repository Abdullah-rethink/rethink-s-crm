import React, { useEffect, useState } from 'react';
import { Columns, User, DollarSign, Layers, ChevronRight, Hash } from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function KanbanBoard({ filters, onSelectDonor }) {
  const [kanbanData, setKanbanData] = useState({});
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

    fetch(`${API_BASE_URL}/api/donors/kanban?${params.toString()}`)
      .then(res => res.json())
      .then(data => {
        setKanbanData(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching Kanban pipeline:', err);
        setLoading(false);
      });
  }, [filters]);

  const tierColors = {
    'Super High': 'border-purple-500/50 bg-purple-500/10 text-purple-400',
    'High': 'border-pink-500/50 bg-pink-500/10 text-pink-400',
    'Medium': 'border-cyan-500/50 bg-cyan-500/10 text-cyan-400',
    'Medium Low': 'border-emerald-500/50 bg-emerald-500/10 text-emerald-400',
    'Low End': 'border-amber-500/50 bg-amber-500/10 text-amber-400'
  };

  const columns = ['Super High', 'High', 'Medium', 'Medium Low', 'Low End'];

  return (
    <div className="flex flex-col gap-6">
      {/* Kanban Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-extrabold text-white flex items-center gap-2">
            <Columns className="w-5 h-5 text-cyan-400" /> Donor Segmentation Kanban Pipeline
          </h2>
          <p className="text-xs text-slate-400">Visual pipeline of donors organized by Lifetime Value (LTV) segments with column total sum amounts.</p>
        </div>
      </div>

      {loading ? (
        <div className="py-24 text-center text-slate-400 font-semibold animate-pulse">
          ⚡ Loading Kanban Pipeline Board...
        </div>
      ) : (
        /* Non-Overlapping Horizontal Column Container */
        <div className="flex gap-4 overflow-x-auto pb-6 w-full min-h-[640px]">
          {columns.map(tier => {
            const col = kanbanData[tier] || { total_donors: 0, total_sum_amount: 0.0, cards: [] };
            const badgeClass = tierColors[tier] || 'border-slate-500 bg-slate-500/10 text-slate-400';

            return (
              <div key={tier} className="glass-panel p-4 flex flex-col gap-3 min-w-[310px] w-[310px] shrink-0 border border-white/10 rounded-2xl shadow-xl">
                {/* Column Header with TOTAL SUM AMOUNT */}
                <div className="flex flex-col gap-1 border-b border-white/10 pb-3">
                  <div className="flex items-center justify-between">
                    <span className={`text-[10px] font-extrabold px-3 py-1 rounded-full border ${badgeClass}`}>
                      {tier}
                    </span>
                    <span className="text-xs font-bold text-slate-400 bg-slate-800 px-2.5 py-0.5 rounded-md border border-white/5">
                      {col.total_donors} donors
                    </span>
                  </div>

                  {/* COLUMN TOTAL SUM AMOUNT (£) */}
                  <div className="flex items-center justify-between mt-1 text-xs">
                    <span className="text-slate-400 font-semibold">Column Total:</span>
                    <span className="font-black text-cyan-400 text-sm">
                      £{col.total_sum_amount?.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                    </span>
                  </div>
                </div>

                {/* Cards Container */}
                <div className="flex flex-col gap-3 max-h-[600px] overflow-y-auto pr-1">
                  {col.cards.length === 0 ? (
                    <div className="py-12 text-center text-xs text-slate-500 italic">No donors match applied filters</div>
                  ) : (
                    col.cards.map((card, idx) => (
                      <div 
                        key={idx}
                        onClick={() => onSelectDonor(card.email || card.name)}
                        className="glass-panel p-3.5 cursor-pointer hover:border-cyan-400/50 hover:bg-slate-800/90 transition-all group flex flex-col gap-2 border border-white/5 rounded-xl"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="flex items-center gap-2.5 min-w-0">
                            <div className="w-8 h-8 rounded-lg bg-slate-800 flex items-center justify-center text-cyan-400 text-xs font-bold shrink-0 border border-white/10">
                              <User className="w-4 h-4" />
                            </div>
                            <div className="truncate min-w-0">
                              <div className="text-xs font-extrabold text-slate-200 group-hover:text-cyan-400 transition-colors truncate">
                                {card.name || 'Anonymous Donor'}
                              </div>
                              <div className="text-[10px] text-slate-400 truncate">{card.email}</div>
                            </div>
                          </div>

                          <ChevronRight className="w-4 h-4 text-slate-500 group-hover:text-cyan-400 transition-colors shrink-0 mt-1" />
                        </div>

                        <div className="pt-2 border-t border-white/5 flex items-center justify-between text-[11px]">
                          <span className="text-slate-400 font-medium">{card.donation_count} txns</span>
                          <span className="font-black text-cyan-400">£{card.total_ltv?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                        </div>
                      </div>
                    ))
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
