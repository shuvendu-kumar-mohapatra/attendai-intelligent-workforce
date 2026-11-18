import React, { useState } from 'react';
import { Outlet, Navigate } from 'react-router-dom';
import { Sidebar } from './Sidebar';
import { TopNavbar } from './TopNavbar';
import { useAuth } from '../../context/AuthContext';

export const AppLayout: React.FC = () => {
  const { isAuthenticated, isLoading } = useAuth();
  const [collapsed, setCollapsed] = useState(false);

  if (isLoading) {
    return (
      <div className="min-h-screen bg-background flex flex-col items-center justify-center">
        <div className="w-10 h-10 border-4 border-primary border-t-transparent rounded-full animate-spin"></div>
        <span className="mt-4 text-xs font-semibold text-secondary">Loading AttendAI...</span>
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return (
    <div className="min-h-screen bg-background text-dark">
      {/* Sidebar (fixed positioning) */}
      <Sidebar collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />

      {/* Main Area: automatically spans (100% - sidebar width) with zero horizontal overflow */}
      <div
        className={`min-h-screen flex flex-col transition-all duration-300 min-w-0 ${
          collapsed ? 'ml-20' : 'ml-64'
        }`}
      >
        <TopNavbar collapsed={collapsed} />

        {/* Content container */}
        <main className="flex-1 mt-16 p-4 sm:p-6 min-w-0 max-w-full">
          <Outlet />
        </main>
      </div>
    </div>
  );
};
