import { useEffect, useRef, useState } from 'react';
import { LogOut, User as UserIcon } from 'lucide-react';
import { AnimatePresence, motion } from 'framer-motion';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

function initialsFor(name: string | undefined, email: string | undefined): string {
  if (name && name.trim()) {
    const parts = name.trim().split(/\s+/);
    const first = parts[0]?.[0] ?? '';
    const last = parts.length > 1 ? (parts[parts.length - 1]?.[0] ?? '') : '';
    return (first + last).toUpperCase() || '?';
  }
  return email?.[0]?.toUpperCase() ?? '?';
}

export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const panelRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const initials = initialsFor(user?.full_name, user?.email);

  // Close panel on outside click
  useEffect(() => {
    if (!open) return;
    function handler(e: MouseEvent) {
      if (
        panelRef.current && !panelRef.current.contains(e.target as Node) &&
        btnRef.current && !btnRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [open]);

  // Close on Escape
  useEffect(() => {
    if (!open) return;
    function handler(e: KeyboardEvent) {
      if (e.key === 'Escape') { setOpen(false); btnRef.current?.focus(); }
    }
    document.addEventListener('keydown', handler);
    return () => document.removeEventListener('keydown', handler);
  }, [open]);

  function handleProfile() {
    setOpen(false);
    navigate('/profile');
  }

  function handleLogout() {
    setOpen(false);
    logout();
    navigate('/login');
  }

  return (
    <div style={{ position: 'relative' }}>
      <button
        ref={btnRef}
        type="button"
        className="sb-avatar"
        style={{ border: 'none' }}
        aria-label="Profile menu"
        aria-expanded={open}
        aria-haspopup="menu"
        onClick={() => setOpen((v) => !v)}
      >
        {initials}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            ref={panelRef}
            role="menu"
            aria-label="Account"
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.18 }}
            className="notif-panel"
            style={{ width: 240 }}
          >
            <div className="notif-panel-header" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '0.15rem' }}>
              <p className="notif-panel-title" style={{ maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.full_name || 'Your account'}
              </p>
              <span style={{ fontSize: '0.75rem', color: 'var(--muted)', maxWidth: '100%', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                {user?.email}
              </span>
            </div>
            <div style={{ padding: '0.4rem' }}>
              <button
                type="button"
                role="menuitem"
                className="user-menu-item"
                onClick={handleProfile}
              >
                <UserIcon size={15} aria-hidden="true" />
                Profile &amp; Settings
              </button>
              <button
                type="button"
                role="menuitem"
                className="user-menu-item"
                onClick={handleLogout}
              >
                <LogOut size={15} aria-hidden="true" />
                Log out
              </button>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
