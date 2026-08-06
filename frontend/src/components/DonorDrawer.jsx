import React, { useEffect, useState } from 'react';
import { X, User, DollarSign, Calendar, MapPin, Tag, CreditCard, ShieldCheck, Mail, Phone, Globe, FileText, Gift, CheckCircle, PieChart, Layers } from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function DonorDrawer({ donorId, onClose }) {
  const [profile, setProfile] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!donorId) return;
    setLoading(true);
    fetch(`${API_BASE_URL}/api/donors/profile/${encodeURIComponent(donorId)}`)
      .then(res => res.json())
      .then(data => {
        setProfile(data);
        setLoading(false);
      })
      .catch(err => {
        console.error('Error fetching donor profile:', err);
        setLoading(false);
      });
  }, [donorId]);

  if (!donorId) return null;

  const getTierBadge = (tier) => {
    switch (tier) {
      case 'Super High': return 'badge-purple';
      case 'High': return 'badge-pink';
      case 'Medium': return 'badge-cyan';
      case 'Medium Low': return 'badge-emerald';
      default: return 'badge-amber';
    }
  };

  return (
    <>
      {/* Backdrop */}
      <div className="drawer-backdrop" onClick={onClose} />

      {/* Drawer Panel */}
      <div className="drawer-content p-6 flex flex-col gap-6 w-full max-w-2xl">
        {/* Header */}
        <div className="flex items-center justify-between border-b border-white/10 pb-4">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 rounded-2xl bg-gradient-to-br from-cyan-400/20 to-purple-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400 font-extrabold text-lg">
              <User className="w-6 h-6" />
            </div>
            <div>
              <h2 className="text-xl font-extrabold text-white">{profile?.display_name || donorId}</h2>
              <div className="flex flex-wrap items-center gap-2 mt-1">
                <span className={`badge ${getTierBadge(profile?.lifetime_tier)}`}>Lifetime: {profile?.lifetime_tier}</span>
                <span className={`badge ${getTierBadge(profile?.transaction_tier)}`}>Transaction: {profile?.transaction_tier}</span>
              </div>
            </div>
          </div>

          <button 
            onClick={onClose}
            className="w-8 h-8 rounded-full bg-slate-800 hover:bg-slate-700 flex items-center justify-center text-slate-400 hover:text-white transition-all"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {loading ? (
          <div className="py-20 text-center text-slate-400 font-semibold animate-pulse">
            ⚡ Loading Complete Donor 360° Profile...
          </div>
        ) : (
          <div className="flex flex-col gap-6 overflow-y-auto pr-1">
            {/* Key Metrics Cards */}
            <div className="grid grid-cols-3 gap-3">
              <div className="glass-panel p-3.5 border-l-4 border-cyan-400">
                <div className="text-[10px] font-bold text-slate-400 uppercase">Total Lifetime Raised</div>
                <div className="text-xl font-black text-cyan-400 mt-1">£{profile?.total_ltv?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">{profile?.total_donations_count} total donations</div>
              </div>

              <div className="glass-panel p-3.5 border-l-4 border-emerald-400">
                <div className="text-[10px] font-bold text-slate-400 uppercase">Average Donation</div>
                <div className="text-xl font-black text-emerald-400 mt-1">£{profile?.avg_donation?.toFixed(2)}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">Per transaction</div>
              </div>

              <div className="glass-panel p-3.5 border-l-4 border-purple-400">
                <div className="text-[10px] font-bold text-slate-400 uppercase">Payment Frequency</div>
                <div className="text-sm font-extrabold text-purple-300 mt-1.5">{profile?.payment_frequency}</div>
                <div className="text-[10px] text-slate-400 mt-0.5">{profile?.settlement_currency || 'GBP'}</div>
              </div>
            </div>

            {/* Category & Sub-Heading Payment Breakdown Card */}
            {profile?.category_breakdown?.length > 0 && (
              <div className="glass-panel p-4 flex flex-col gap-3 border-l-4 border-purple-400">
                <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wider flex items-center gap-1.5">
                  <PieChart className="w-3.5 h-3.5 text-purple-400" /> Payment Breakdown by Heading & Sub-Heading
                </h3>

                <div className="flex flex-col gap-2.5 mt-1">
                  {profile.category_breakdown.map((item, idx) => (
                    <div key={idx} className="flex flex-col gap-1.5 p-2.5 rounded-xl bg-slate-900/60 border border-white/5">
                      <div className="flex items-center justify-between text-xs">
                        <div className="flex items-center gap-2">
                          <span className="font-extrabold text-cyan-400">{item.heading}</span>
                          <span className="text-slate-500">•</span>
                          <span className="font-semibold text-purple-300">{item.subheading}</span>
                        </div>

                        <div className="flex items-center gap-2">
                          <span className="text-[11px] text-slate-400 font-mono">({item.count} txns)</span>
                          <span className="font-black text-emerald-400 text-xs">£{item.total_amount?.toLocaleString(undefined, { minimumFractionDigits: 2 })}</span>
                        </div>
                      </div>

                      {/* Percentage Progress Bar */}
                      <div className="flex items-center gap-2">
                        <div className="w-full h-1.5 rounded-full bg-slate-800 overflow-hidden">
                          <div 
                            className="h-full bg-gradient-to-r from-cyan-400 to-purple-500 rounded-full" 
                            style={{ width: `${Math.min(100, item.percentage)}%` }}
                          />
                        </div>
                        <span className="text-[10px] font-bold text-slate-400 shrink-0 w-9 text-right">{item.percentage}%</span>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {/* Complete Contact & Billing Information */}
            <div className="glass-panel p-4 flex flex-col gap-3">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <User className="w-3.5 h-3.5 text-cyan-400" /> Contact & Billing Profile
              </h3>

              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Donor ID</span>
                  <span className="font-mono text-cyan-400 font-bold">{profile?.donor_id}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Email</span>
                  <span className="font-semibold text-slate-200">{profile?.email}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Phone</span>
                  <span className="font-semibold text-slate-200">{profile?.phone}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Billing Address</span>
                  <span className="font-semibold text-slate-200 truncate max-w-[180px]">{profile?.billing_address_1}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">City / Postcode</span>
                  <span className="font-semibold text-slate-200">{profile?.billing_city !== 'N/A' ? `${profile?.billing_city}, ` : ''}{profile?.billing_postcode}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Billing Country</span>
                  <span className="font-semibold text-slate-200">{profile?.billing_country}</span>
                </div>
              </div>
            </div>

            {/* Compliance, Tax & Marketing Flags */}
            <div className="glass-panel p-4 flex flex-col gap-3">
              <h3 className="text-xs font-bold text-slate-400 uppercase tracking-wider flex items-center gap-1.5">
                <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" /> Compliance & Tax Declarations
              </h3>

              <div className="grid grid-cols-2 gap-x-6 gap-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Gift Aid Claimed</span>
                  <span className={`font-bold ${profile?.gift_aid === 'Yes' ? 'text-emerald-400' : 'text-slate-400'}`}>{profile?.gift_aid}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Marketing Consent</span>
                  <span className="font-semibold text-slate-200">{profile?.marketing_consent}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Tax Receipt Requested</span>
                  <span className="font-semibold text-slate-200">{profile?.tax_receipt_requested}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Visibility Flag</span>
                  <span className="font-semibold text-slate-200">{profile?.anonymous_public}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Data Source</span>
                  <span className="font-semibold text-cyan-400">{profile?.source}</span>
                </div>
                <div className="flex justify-between py-1 border-b border-white/5">
                  <span className="text-slate-400">Platform</span>
                  <span className="font-semibold text-purple-300">{profile?.platform}</span>
                </div>
              </div>
            </div>

            {/* Complete Transaction History Table */}
            <div>
              <h3 className="text-xs font-extrabold text-white mb-3 uppercase tracking-wider flex items-center gap-2">
                <Calendar className="w-4 h-4 text-cyan-400" /> Complete Transaction History ({profile?.history?.length || 0})
              </h3>

              <div className="glass-panel overflow-hidden">
                <div className="overflow-x-auto max-h-[300px]">
                  <table className="crm-table">
                    <thead>
                      <tr>
                        <th>Date (UTC)</th>
                        <th>Campaign</th>
                        <th>Category Heading</th>
                        <th>Sub-Heading</th>
                        <th>Net Settled Amount</th>
                      </tr>
                    </thead>
                    <tbody>
                      {profile?.history?.map((txn, i) => (
                        <tr key={i}>
                          <td className="text-xs text-slate-400 font-mono">{txn['Created Date (UTC)'] ? String(txn['Created Date (UTC)']).split('T')[0] : 'N/A'}</td>
                          <td className="text-xs font-bold text-slate-200 max-w-[160px] truncate">{txn['Campaign Name'] || 'N/A'}</td>
                          <td className="text-xs text-cyan-400 font-semibold">{txn['Heading'] || 'Unassigned'}</td>
                          <td className="text-xs text-purple-300">{txn['Sub-Heading'] || 'Unassigned'}</td>
                          <td className="text-xs font-black text-cyan-400">£{txn['Total Online Donations Net Amount in Settled Currency']?.toFixed(2) || '0.00'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </>
  );
}
