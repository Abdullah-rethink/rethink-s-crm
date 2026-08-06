import React, { useState } from 'react';
import { ShieldCheck, Lock, User, KeyRound } from 'lucide-react';
import { API_BASE_URL } from '../config';

export default function LoginView({ onLoginSuccess }) {
  const [identity, setIdentity] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!identity.trim() || !password.trim()) {
      setError('Please enter both email/username and password.');
      return;
    }

    setLoading(true);
    setError('');

    fetch(`${API_BASE_URL}/api/auth/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ identity, password })
    })
      .then(r => r.json())
      .then(res => {
        setLoading(false);
        if (res?.status === 'success') {
          onLoginSuccess(res.user);
        } else {
          setError(res?.detail || 'Invalid credentials or user not found.');
        }
      })
      .catch(err => {
        setLoading(false);
        setError(`Connection error: ${err.message}`);
      });
  };

  return (
    <div className="min-h-screen flex items-center justify-center p-4">
      <div className="glass-panel p-8 w-full max-w-md border-l-4 border-cyan-400 flex flex-col gap-6 shadow-2xl">
        <div className="text-center flex flex-col items-center gap-2">
          <div className="w-14 h-14 rounded-2xl bg-gradient-to-br from-cyan-400 to-blue-600 flex items-center justify-center text-slate-950 font-black shadow-xl shadow-cyan-500/20">
            <ShieldCheck className="w-8 h-8 fill-current" />
          </div>
          <h2 className="text-2xl font-black text-white">Secure Access Control</h2>
          <p className="text-xs text-slate-400">Please log in to access the Crowdfunding Analytics Platform.</p>
        </div>

        {error && <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/30 text-xs font-bold text-rose-400 text-center">{error}</div>}

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div>
            <label className="text-xs text-slate-400 font-bold mb-1.5 block">Email or Username</label>
            <div className="relative">
              <User className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input 
                type="text"
                placeholder="e.g. superadmin@analytics.com"
                value={identity}
                onChange={e => setIdentity(e.target.value)}
                className="w-full bg-slate-900/90 border border-white/10 rounded-xl pl-9 pr-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>

          <div>
            <label className="text-xs text-slate-400 font-bold mb-1.5 block">Password</label>
            <div className="relative">
              <Lock className="w-4 h-4 text-slate-400 absolute left-3 top-3" />
              <input 
                type="password"
                placeholder="Enter your password..."
                value={password}
                onChange={e => setPassword(e.target.value)}
                className="w-full bg-slate-900/90 border border-white/10 rounded-xl pl-9 pr-4 py-2.5 text-xs text-white placeholder-slate-500 focus:outline-none focus:border-cyan-500"
              />
            </div>
          </div>

          <button 
            type="submit" 
            disabled={loading}
            className="btn-primary py-3 text-sm flex items-center justify-center gap-2 mt-2"
          >
            <KeyRound className="w-4 h-4" /> {loading ? 'Authenticating...' : '🚀 Log In to Dashboard'}
          </button>
        </form>

        <div className="text-center text-[11px] text-slate-500 border-t border-white/5 pt-4">
          Default Super Admin: <code className="text-cyan-400 font-bold">superadmin@analytics.com</code> / <code className="text-cyan-400 font-bold">SuperAdmin@123</code>
        </div>
      </div>
    </div>
  );
}
