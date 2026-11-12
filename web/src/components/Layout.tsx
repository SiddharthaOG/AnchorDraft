import { useState } from 'react';
import { Outlet, Link, NavLink } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthProvider';

const navigation = [
  { path: '/', label: 'Overview', roles: ['creator', 'manager', 'reviewer', 'owner'], section: 'Workspace', icon: '◫' },
  { path: '/approvals', label: 'Approvals', roles: ['manager', 'owner'], section: 'Workspace', icon: '↗' },
  { path: '/review', label: 'Review queue', roles: ['reviewer', 'owner'], section: 'Workspace', icon: '⌁' },
  { path: '/kits', label: 'Brand systems', roles: ['owner'], section: 'Governance', icon: '▤' },
  { path: '/owner', label: 'Kit overview', roles: ['owner'], section: 'Governance', icon: '⌂' },
  { path: '/insights', label: 'Insights', roles: ['owner', 'manager', 'reviewer'], section: 'Intelligence', icon: '⌁' },
];

export function Layout() {
  const { session, signOut, getPrimaryRole, switchOrganization } = useAuth();
  const [menuOpen, setMenuOpen] = useState(false);
  const visibleNav = navigation.filter(item =>
    session?.currentRoles.some((role: string) => item.roles.includes(role))
  );
  const sections = [...new Set(visibleNav.map(item => item.section))];
  const displayName = session?.profile?.display_name || session?.user?.email || 'User';
  const initial = displayName.charAt(0).toUpperCase();

  return (
    <div className="ad-shell">
      <aside className={`ad-sidebar ${menuOpen ? 'is-open' : ''}`}>
        <Link to="/" className="ad-brand" aria-label="AnchorDraft home" onClick={() => setMenuOpen(false)}>
          <span className="ad-brand-mark"><span /></span>
          <span className="ad-brand-word">anchor<span>draft</span><small>CONTENT GOVERNANCE</small><span className="sr-only">AnchorDraft</span></span>
        </Link>

        <div className="ad-workspace-label">YOUR WORKSPACE</div>
        {session?.organizations && session.organizations.length > 1 && (
          <label className="ad-org-switch">
            <span className="ad-org-avatar">{(session.organizations.find((o: {id:string}) => o.id === session.currentOrgId)?.name || 'O').charAt(0)}</span>
            <select value={session.currentOrgId || ''} onChange={e => switchOrganization(e.target.value)} aria-label="Select organization">
              {session.organizations.map((org: { id: string; name: string }) => <option key={org.id} value={org.id}>{org.name}</option>)}
            </select>
            <span className="ad-chevron">⌄</span>
          </label>
        )}

        <nav className="ad-navigation" aria-label="Main navigation">
          {sections.map(section => (
            <div className="ad-nav-section" key={section}>
              <p className="ad-nav-heading">{section}</p>
              {visibleNav.filter(item => item.section === section).map(item => (
                <NavLink key={item.path} to={item.path} end={item.path === '/'} onClick={() => setMenuOpen(false)}
                  className={({ isActive }) => `ad-nav-link ${isActive ? 'active' : ''}`}>
                  <span className="ad-nav-icon" aria-hidden="true">{item.icon}</span>
                  <span>{item.label}</span>
                  <span className="ad-nav-arrow" aria-hidden="true">↗</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>

        <div className="ad-sidebar-bottom">
          <div className="ad-trust-note">
            <span className="ad-live-dot" />
            <div><strong>Review with confidence</strong><small>Every decision leaves a trail.</small></div>
          </div>
          <div className="ad-profile">
            <div className="ad-avatar">{initial}</div>
            <div className="ad-profile-copy"><strong>{displayName}</strong><small>{getPrimaryRole() || 'Member'}</small></div>
            <button className="ad-signout" onClick={signOut} aria-label="Sign out" title="Sign out">↗</button>
          </div>
        </div>
      </aside>

      {menuOpen && <button className="ad-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <div className="ad-main">
        <header className="ad-topbar">
          <button className="ad-mobile-toggle" onClick={() => setMenuOpen(v => !v)} aria-label="Toggle navigation">☰</button>
          <div className="ad-breadcrumb"><span>ANCHORDRAFT</span><i>/</i><strong>WORKSPACE</strong></div>
          <div className="ad-topbar-right"><span className="ad-secure"><span /> SECURE WORKSPACE</span><span className="ad-top-avatar">{initial}</span></div>
        </header>
        <main className="ad-page"><Outlet /></main>
        <footer className="ad-footer"><span>ANCHORDRAFT © 2026</span><span>Clarity before content goes live.</span></footer>
      </div>
    </div>
  );
}

export default Layout;
