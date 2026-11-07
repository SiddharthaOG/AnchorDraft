/** Brand Kits overview list page. */

import { useEffect, useState, useRef } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../../features/auth/AuthProvider';
import { LoadingScreen } from '../../components/LoadingScreen';
import {
  getBrandKits,
  cloneKit,
  type BrandKit,
  getKitRules,
  getKitFacts,
} from '../../lib/data';

interface KitListItemProps {
  kit: BrandKit;
  ruleCount: number;
  factCount: number;
  isActive: boolean;
  onClone: (kitId: string) => Promise<void>;
}

function KitListItem({ kit, ruleCount, factCount, isActive, onClone }: KitListItemProps) {
  const statusColors = {
    draft: 'bg-yellow-100 text-yellow-800',
    active: 'bg-green-100 text-green-800',
    archived: 'bg-gray-100 text-gray-800',
  };

  const handleClone = async () => {
    await onClone(kit.id);
  };

  return (
    <div className="bg-white border border-gray-200 rounded-lg p-6 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-3 mb-2">
            <h3 className="font-semibold text-gray-900 truncate">{kit.name}</h3>
            <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${statusColors[kit.status]}`}>
              {kit.status.charAt(0).toUpperCase() + kit.status.slice(1)}
            </span>
            {isActive && (
              <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-primary text-white">
                Active
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500">Version {kit.version}</p>
          <div className="mt-3 flex flex-wrap gap-4 text-sm text-gray-600">
            <span>{ruleCount} rules</span>
            <span>{factCount} approved facts</span>
          </div>
          <div className="mt-3 text-xs text-gray-400">
            Created {new Date(kit.created_at).toLocaleDateString()}
            {kit.activated_at && ` • Activated ${new Date(kit.activated_at).toLocaleDateString()}`}
            {kit.source_kit_id && ` • Cloned from kit v${kit.version - 1}`}
          </div>
        </div>
        <div className="flex items-center gap-2 ml-4">
          <Link
            to={`/kits/${kit.id}`}
            className="px-3 py-1.5 text-sm font-medium text-primary hover:text-primary-dark border border-primary rounded-lg hover:bg-primary-light transition-colors"
          >
            {kit.status === 'draft' ? 'Edit' : 'View'}
          </Link>
          {kit.status === 'draft' && !isActive && (
            <button
              onClick={handleClone}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 hover:text-gray-900 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Clone
            </button>
          )}
          {kit.status !== 'draft' && (
            <button
              onClick={handleClone}
              className="px-3 py-1.5 text-sm font-medium text-gray-700 hover:text-gray-900 border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
            >
              Clone
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="bg-red-50 border border-red-200 rounded-lg p-6">
      <div className="flex items-center justify-between">
        <div>
          <h3 className="font-semibold text-red-800">Unable to load brand kits</h3>
          <p className="text-red-600 text-sm mt-1">{message}</p>
        </div>
        <button
          onClick={onRetry}
          className="px-3 py-1.5 bg-red-600 text-white text-sm rounded-lg hover:bg-red-700"
        >
          Retry
        </button>
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="text-center py-12">
      <svg className="w-16 h-16 text-gray-300 mx-auto mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2h12z" />
      </svg>
      <h3 className="text-lg font-medium text-gray-900 mb-2">No brand kits yet</h3>
      <p className="text-gray-500 mb-6">Create your first brand kit by cloning an existing kit once one exists, or contact your administrator to set up an initial kit.</p>
    </div>
  );
}

/** Brand Kits overview page. */
export function KitList() {
  const { session, isLoading: authLoading } = useAuth();
  const navigate = useNavigate();
  const [kits, setKits] = useState<BrandKit[]>([]);
  const [kitStats, setKitStats] = useState<Map<string, { rules: number; facts: number }>>(new Map());
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Request ID for stale-request protection
  const requestIdRef = useRef(0);

  const loadData = async () => {
    const orgId = session?.currentOrgId;
    if (!orgId) {
      setKits([]);
      setKitStats(new Map());
      setIsLoading(false);
      return;
    }

    const currentRequestId = ++requestIdRef.current;
    setIsLoading(true);
    setError(null);

    try {
      const kitList = await getBrandKits(orgId);

      // Stale request check
      if (currentRequestId !== requestIdRef.current) return;

      // Fetch rule/fact counts for each kit in parallel
      const statsMap = new Map<string, { rules: number; facts: number }>();
      await Promise.all(
        kitList.map(async (kit) => {
          const [rules, facts] = await Promise.all([
            getKitRules(kit.id),
            getKitFacts(kit.id),
          ]);
          statsMap.set(kit.id, { rules: rules.length, facts: facts.length });
        })
      );

      // Stale request check after parallel fetches
      if (currentRequestId !== requestIdRef.current) return;

      setKits(kitList);
      setKitStats(statsMap);
    } catch (err) {
      if (currentRequestId !== requestIdRef.current) return;
      setError(err instanceof Error ? err.message : 'Failed to load brand kits');
    } finally {
      if (currentRequestId === requestIdRef.current) {
        setIsLoading(false);
      }
    }
  };

  const handleClone = async (kitId: string) => {
    try {
      const result = await cloneKit(kitId);
      navigate(`/kits/${result.kit_id}`);
      await loadData();
    } catch (err) {
      // Error will be shown inline or via toast in a real app
      console.error('Clone failed:', err);
      alert(`Failed to clone kit: ${err instanceof Error ? err.message : 'Unknown error'}`);
    }
  };

  // Refetch when orgId changes
  useEffect(() => {
    if (!authLoading && session) {
      loadData();
    }
  }, [authLoading, session, session?.currentOrgId]);

  if (authLoading || !session) {
    return <LoadingScreen message="Loading authentication..." />;
  }

  if (isLoading) {
    return <LoadingScreen message="Loading brand kits..." />;
  }

  if (error) {
    return <ErrorState message={error} onRetry={loadData} />;
  }

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Brand Kits</h1>
          <p className="text-gray-600 mt-1">Manage brand kit versions, rules, and approved facts.</p>
        </div>
      </div>

      {/* Kit list */}
      {kits.length === 0 ? (
        <EmptyState />
      ) : (
        <div className="space-y-4">
          {kits.map(kit => {
            const stats = kitStats.get(kit.id) || { rules: 0, facts: 0 };
            const isActive = kit.status === 'active';
            return (
              <KitListItem
                key={kit.id}
                kit={kit}
                ruleCount={stats.rules}
                factCount={stats.facts}
                isActive={isActive}
                onClone={handleClone}
              />
            );
          })}
        </div>
      )}

      {/* Guidelines */}
      <div className="bg-gray-50 rounded-lg p-6">
        <h3 className="font-semibold text-gray-900 mb-2">Kit Guidelines</h3>
        <ul className="text-gray-600 text-sm space-y-1">
          <li>• Each organization has one active kit used for reviews</li>
          <li>• Edit draft kits; clone to create new versions preserving rule/fact keys</li>
          <li>• Run lint before activating to catch configuration issues</li>
          <li>• Activation archives the previous active kit automatically</li>
        </ul>
      </div>
    </div>
  );
}

export default KitList;