/** Owner (Guideline Owner) landing page - for brand kit management. */

import React from 'react';
import { Link } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';

interface StatCardProps {
  label: string;
  value: string | number;
  icon: React.ReactNode;
  href?: string;
}

function StatCard({ label, value, icon, href }: StatCardProps) {
  const content = (
    <div className="bg-white rounded-lg shadow p-6">
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium text-gray-500">{label}</p>
          <p className="text-2xl font-bold text-gray-900 mt-1">{value}</p>
        </div>
        <div className="p-3 bg-primary-light rounded-lg text-primary">
          {icon}
        </div>
      </div>
      {href && (
        <Link
          to={href}
          className="mt-4 inline-flex items-center text-sm font-medium text-primary hover:text-primary-dark"
        >
          View all →
        </Link>
      )}
    </div>
  );

  return href ? <Link to={href}>{content}</Link> : content;
}

/** Owner dashboard landing page. */
export function OwnerLanding() {
  const { session, isLoading } = useAuth();

  if (isLoading || !session) {
    return <LoadingScreen message="Loading dashboard..." />;
  }

  return (
    <div className="space-y-8">
      {/* Welcome header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Welcome, {session.profile?.display_name?.split(' ')[0] || 'Guideline Owner'}
        </h1>
        <p className="text-gray-600 mt-1">
          Manage brand kits, rules, and approved facts for your organization.
        </p>
      </div>

      {/* Quick stats */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
        <StatCard
          label="Active Kit"
          value="1"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2h12z" />
            </svg>
          }
          href="/kits"
        />
        <StatCard
          label="Draft Kits"
          value="0"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
          }
          href="/kits"
        />
        <StatCard
          label="Rules"
          value="0"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
          }
          href="/kits"
        />
        <StatCard
          label="Approved Facts"
          value="0"
          icon={
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          }
          href="/kits"
        />
      </div>

      {/* Quick actions */}
      <div className="bg-white rounded-lg shadow p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Link
            to="/kits/new"
            className="p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-gray-50 transition-colors text-center"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
            </svg>
            <p className="font-medium text-gray-900">Create Brand Kit</p>
            <p className="text-sm text-gray-500 mt-1">Start a new kit version</p>
          </Link>

          <Link
            to="/kits"
            className="p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-gray-50 transition-colors text-center"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
            </svg>
            <p className="font-medium text-gray-900">Manage Kits</p>
            <p className="text-sm text-gray-500 mt-1">View and edit kits</p>
          </Link>

          <Link
            to="/kits/lint"
            className="p-4 border border-gray-200 rounded-lg hover:border-primary hover:bg-gray-50 transition-colors text-center"
          >
            <svg className="w-10 h-10 mx-auto text-gray-400 mb-2" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            <p className="font-medium text-gray-900">Lint Kit</p>
            <p className="text-sm text-gray-500 mt-1">Check for issues before activation</p>
          </Link>
        </div>
      </div>

      {/* Brand kits overview */}
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Brand Kits</h2>
          <Link to="/kits" className="text-sm font-medium text-primary hover:text-primary-dark">
            View all →
          </Link>
        </div>
        <div className="text-center py-8">
          <svg className="w-12 h-12 text-gray-300 mx-auto mb-3" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2h12z" />
          </svg>
          <p className="text-gray-500 mb-4">No brand kits yet</p>
          <Link to="/kits/new" className="inline-flex items-center px-4 py-2 bg-primary text-white rounded-lg font-medium hover:bg-primary-dark">
            Create your first brand kit
          </Link>
        </div>
      </div>

      {/* Guidelines */}
      <div className="bg-gray-50 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 mb-2">Kit Guidelines</h3>
        <ul className="text-gray-600 text-sm space-y-1">
          <li>• Rules and facts are versioned with each kit — old findings stay explainable</li>
          <li>• Only draft kits can be edited; activate to make it the live standard</li>
          <li>• Use the lint endpoint to check for issues before activating</li>
          <li>• Rules use stable keys (e.g., TERM-01) so insights work across versions</li>
        </ul>
      </div>
    </div>
  );
}

export default OwnerLanding;