import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Clock, ShieldAlert, ArrowRight, UserCheck, Shield, User } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export const Login: React.FC = () => {
  const { login } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      await login(email, password);
      navigate('/');
    } catch (err: any) {
      if (!err.response) {
        setError('Cannot connect to backend server. Please verify your network connection or VITE_API_URL.');
      } else if (err.response.status === 404) {
        setError('API service endpoint not found (404). Check backend deployment and VITE_API_URL.');
      } else if (err.response.status === 500) {
        setError('Internal server error (500). Please check backend logs and database connection.');
      } else {
        setError(err.response?.data?.detail || 'Invalid email or password. Please try again.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleDemoFill = (demoEmail: string, demoPass: string) => {
    setEmail(demoEmail);
    setPassword(demoPass);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center p-6">
      <div className="w-full max-w-md">
        {/* Brand Header */}
        <div className="flex flex-col items-center mb-8">
          <div className="w-12 h-12 rounded-xl bg-primary flex items-center justify-center text-white shadow-md mb-3">
            <Clock className="w-7 h-7" />
          </div>
          <h1 className="text-2xl font-bold text-dark tracking-tight">AttendAI</h1>
          <p className="text-xs font-medium text-secondary mt-1">Intelligent Workforce. Smarter Decisions.</p>
        </div>

        {/* Card */}
        <div className="bg-card border border-border rounded-xl shadow-card p-8">
          <h2 className="text-base font-semibold text-dark mb-1">Sign in to your account</h2>
          <p className="text-xs text-secondary mb-6">Enter your credentials to access the workforce portal.</p>

          {error && (
            <div className="mb-4 p-3 rounded-lg bg-red-50 border border-red-200 text-danger text-xs flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 flex-shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-xs font-medium text-dark mb-1">Work Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@company.com"
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-border rounded-lg text-dark focus:outline-none focus:ring-1 focus:ring-primary focus:bg-white"
              />
            </div>

            <div>
              <div className="flex justify-between items-center mb-1">
                <label className="text-xs font-medium text-dark">Password</label>
                <a href="#forgot" className="text-[11px] text-primary hover:underline">
                  Forgot password?
                </a>
              </div>
              <input
                type="password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full px-3 py-2 text-xs bg-slate-50 border border-border rounded-lg text-dark focus:outline-none focus:ring-1 focus:ring-primary focus:bg-white"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full mt-2 py-2.5 px-4 bg-primary hover:bg-primary-hover text-white rounded-lg text-xs font-semibold shadow-sm transition-colors flex items-center justify-center gap-2 disabled:opacity-60"
            >
              {loading ? (
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
              ) : (
                <>
                  <span>Sign in</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </>
              )}
            </button>
          </form>

          {/* Quick-Fill Demo Credentials */}
          <div className="mt-8 pt-6 border-t border-border">
            <span className="block text-[11px] font-semibold text-secondary uppercase tracking-wider mb-2.5">
              Quick Demo Accounts
            </span>
            <div className="grid grid-cols-3 gap-2">
              <button
                type="button"
                onClick={() => handleDemoFill('admin@attendai.com', 'Admin@123')}
                className="p-2 rounded-lg border border-border hover:border-purple-300 hover:bg-purple-50/50 text-left transition-colors flex flex-col gap-1"
              >
                <div className="flex items-center gap-1.5 text-purple-700">
                  <Shield className="w-3.5 h-3.5" />
                  <span className="text-[11px] font-bold">Admin</span>
                </div>
                <span className="text-[10px] text-secondary">Full Org Access</span>
              </button>

              <button
                type="button"
                onClick={() => handleDemoFill('hrmanager@attendai.com', 'HRManager@123')}
                className="p-2 rounded-lg border border-border hover:border-blue-300 hover:bg-blue-50/50 text-left transition-colors flex flex-col gap-1"
              >
                <div className="flex items-center gap-1.5 text-blue-700">
                  <UserCheck className="w-3.5 h-3.5" />
                  <span className="text-[11px] font-bold">HR Mgr</span>
                </div>
                <span className="text-[10px] text-secondary">Workforce HR</span>
              </button>

              <button
                type="button"
                onClick={() => handleDemoFill('employee@attendai.com', 'Employee@123')}
                className="p-2 rounded-lg border border-border hover:border-emerald-300 hover:bg-emerald-50/50 text-left transition-colors flex flex-col gap-1"
              >
                <div className="flex items-center gap-1.5 text-emerald-700">
                  <User className="w-3.5 h-3.5" />
                  <span className="text-[11px] font-bold">Employee</span>
                </div>
                <span className="text-[10px] text-secondary">Portal Access</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
