import { Suspense, useState } from 'react';
import { Outlet, Link, NavLink, useLocation } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthProvider';
import { LoadingScreen } from './LoadingScreen';

const navigation = [
  { path: '/', label: 'Overview', roles: ['creator', 'manager', 'reviewer', 'owner'], section: 'Workspace', icon: '◫' },
  { path: '/approvals', label: 'Approvals', roles: ['manager', 'owner'], section: 'Workspace', icon: '↗' },
  { path: '/review', label: 'Review queue', roles: ['reviewer', 'owner'], section: 'Workspace', icon: '⌁' },
  { path: '/kits', label: 'Brand systems', roles: ['owner'], section: 'Governance', icon: '▤' },
  { path: '/owner', label: 'Kit overview', roles: ['owner'], section: 'Governance', icon: '⌂' },
  { path: '/owner/confidentiality', label: 'Confidentiality', roles: ['owner'], section: 'Governance', icon: '◇' },
  { path: '/insights', label: 'Insights', roles: ['owner', 'manager', 'reviewer'], section: 'Intelligence', icon: '⌁' },
];

export function Layout() {
  const { session, signOut, getPrimaryRole, switchOrganization } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const visibleNav = navigation.filter(item =>
    session?.currentRoles.some((role: string) => item.roles.includes(role))
  );
  const sections = [...new Set(visibleNav.map(item => item.section))];
  const displayName = session?.profile?.display_name || session?.user?.email || 'User';
  const initial = displayName.charAt(0).toUpperCase();

  return (
    <div className="anchordraft-shell">
      <aside className={`anchordraft-sidebar ${menuOpen ? 'is-open' : ''}`}>
        <Link to="/" className="anchordraft-brand" aria-label="AnchorDraft home" onClick={() => setMenuOpen(false)}>
          <span className="anchordraft-brand-mark"><span /></span>
          <span className="anchordraft-brand-word">anchor<span>draft</span><small>CONTENT GOVERNANCE</small><span className="sr-only">AnchorDraft</span></span>
        </Link>
        <div className="anchordraft-workspace-label">YOUR WORKSPACE</div>
        {session?.organizations && session.organizations.length > 1 && (
          <label className="anchordraft-org-switch">
            <span className="anchordraft-org-avatar">{(session.organizations.find((o: {id:string}) => o.id === session.currentOrgId)?.name || 'O').charAt(0)}</span>
            <select value={session.currentOrgId || ''} onChange={e => switchOrganization(e.target.value)} aria-label="Select organization">
              {session.organizations.map((org: { id: string; name: string }) => <option key={org.id} value={org.id}>{org.name}</option>)}
            </select>
            <span className="anchordraft-chevron">⌄</span>
          </label>
        )}
        <nav className="anchordraft-navigation" aria-label="Main navigation">
          {sections.map(section => (
            <div className="anchordraft-nav-section" key={section}>
              <p className="anchordraft-nav-heading">{section}</p>
              {visibleNav.filter(item => item.section === section).map(item => (
                <NavLink key={item.path} to={item.path} end={item.path === '/'} onClick={() => setMenuOpen(false)}
                  className={({ isActive }) => `anchordraft-nav-link ${isActive ? 'active' : ''}`}>
                  <span className="anchordraft-nav-icon" aria-hidden="true">{item.icon}</span>
                  <span>{item.label}</span>
                  <span className="anchordraft-nav-arrow" aria-hidden="true">↗</span>
                </NavLink>
              ))}
            </div>
          ))}
        </nav>
        <div className="anchordraft-sidebar-bottom">
          <div className="anchordraft-trust-note"><span className="anchordraft-live-dot" /><div><strong>Review with confidence</strong><small>Every decision leaves a trail.</small></div></div>
          <div className="anchordraft-profile">
            <div className="anchordraft-avatar">{initial}</div>
            <div className="anchordraft-profile-copy"><strong>{displayName}</strong><small>{getPrimaryRole() || 'Member'}</small></div>
            <button className="anchordraft-signout" onClick={signOut} aria-label="Sign out" title="Sign out">↗</button>
          </div>
        </div>
      </aside>
      {menuOpen && <button className="anchordraft-scrim" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
      <div className="anchordraft-main">
        <header className="anchordraft-topbar">
          <button className="anchordraft-mobile-toggle" onClick={() => setMenuOpen(v => !v)} aria-label="Toggle navigation">☰</button>
          <div className="anchordraft-breadcrumb"><span>ANCHORDRAFT</span><i>/</i><strong>WORKSPACE</strong></div>
          <div className="anchordraft-topbar-right"><span className="anchordraft-secure"><span /> SECURE WORKSPACE</span><span className="anchordraft-top-avatar">{initial}</span></div>
        </header>
        <main className="anchordraft-page"><Suspense fallback={<LoadingScreen message="Loading workspace..." fullScreen={false} />}><div key={location.pathname} className="anchordraft-route-transition"><Outlet /></div></Suspense></main>
        <footer className="anchordraft-footer"><span>ANCHORDRAFT © 2026</span><span>Clarity before content goes live.</span></footer>
      </div>
    </div>
  );
}

export default Layout;
