import { useCallback, useEffect, useRef, useState } from 'react';
import { Bell, Check, FileText, Mic, Upload } from 'lucide-react';
import { motion, AnimatePresence } from 'framer-motion';
import { getActivityTimeline } from '../api/client';
import { useAuth } from '../context/AuthContext';
import type { ActivityEvent } from '../api/types';

function eventIcon(type: string) {
  switch (type) {
    case 'session_created': return <Mic size={13} aria-hidden="true" />;
    case 'session_completed': return <Check size={13} aria-hidden="true" />;
    case 'report_generated': return <FileText size={13} aria-hidden="true" />;
    case 'resume_uploaded': return <Upload size={13} aria-hidden="true" />;
    default: return <Bell size={13} aria-hidden="true" />;
  }
}

function eventColor(type: string): string {
  switch (type) {
    case 'session_completed': return 'var(--success)';
    case 'report_generated': return 'var(--accent)';
    case 'resume_uploaded': return 'var(--warning)';
    default: return 'var(--primary)';
  }
}

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

export function NotificationBell() {
  const { token } = useAuth();
  const [open, setOpen] = useState(false);
  const [events, setEvents] = useState<ActivityEvent[]>([]);
  const [seen, setSeen] = useState(0);
  const panelRef = useRef<HTMLDivElement>(null);
  const btnRef = useRef<HTMLButtonElement>(null);

  const load = useCallback(async () => {
    if (!token) return;
    try {
      const res = await getActivityTimeline(token);
      setEvents(res.events.slice(0, 20));
    } catch {
      // notifications are non-critical — silent failure
    }
  }, [token]);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect -- standard data-fetching pattern
    load();
  }, [load]);

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

  const unread = Math.max(0, events.length - seen);

  function handleOpen() {
    if (!open) {
      setOpen(true);
      setSeen(events.length);
      if (events.length === 0) load();
    } else {
      setOpen(false);
    }
  }

  return (
    <div style={{ position: 'relative' }}>
      <button
        ref={btnRef}
        type="button"
        className="sb-topbar-icon-btn"
        aria-label={`Notifications${unread > 0 ? `, ${unread} unread` : ''}`}
        aria-expanded={open}
        aria-haspopup="dialog"
        onClick={handleOpen}
      >
        <Bell size={16} aria-hidden="true" />
        {unread > 0 && (
          <span
            aria-hidden="true"
            style={{
              position: 'absolute',
              top: 4,
              right: 4,
              width: 8,
              height: 8,
              borderRadius: '50%',
              background: 'var(--primary)',
              border: '1.5px solid var(--bg)',
            }}
          />
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            ref={panelRef}
            role="dialog"
            aria-label="Notifications"
            initial={{ opacity: 0, y: -8, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.97 }}
            transition={{ duration: 0.18 }}
            style={{
              position: 'absolute',
              top: 'calc(100% + 8px)',
              right: 0,
              width: 320,
              background: 'var(--surface)',
              border: '1px solid var(--border-strong)',
              borderRadius: 'var(--radius)',
              boxShadow: 'var(--shadow)',
              zIndex: 200,
              overflow: 'hidden',
            }}
          >
            <div style={{
              padding: '0.75rem 1rem',
              borderBottom: '1px solid var(--border)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}>
              <span style={{ fontWeight: 700, fontSize: '0.875rem', color: 'var(--text)' }}>
                Recent Activity
              </span>
              <button
                type="button"
                style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '0.78rem', color: 'var(--muted)', padding: '0.1rem 0.3rem' }}
                onClick={() => { load(); }}
                aria-label="Refresh notifications"
              >
                Refresh
              </button>
            </div>

            <div style={{ maxHeight: 360, overflowY: 'auto' }}>
              {events.length === 0 ? (
                <div style={{ padding: '2rem 1rem', textAlign: 'center', color: 'var(--muted)', fontSize: '0.875rem' }}>
                  No recent activity
                </div>
              ) : (
                events.map((ev, i) => (
                  <div
                    key={i}
                    style={{
                      display: 'flex',
                      gap: '0.75rem',
                      padding: '0.75rem 1rem',
                      borderBottom: i < events.length - 1 ? '1px solid var(--border)' : 'none',
                      alignItems: 'flex-start',
                    }}
                  >
                    <div style={{
                      width: 28,
                      height: 28,
                      borderRadius: 8,
                      background: `${eventColor(ev.event_type)}18`,
                      color: eventColor(ev.event_type),
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      flexShrink: 0,
                      marginTop: 1,
                    }}>
                      {eventIcon(ev.event_type)}
                    </div>
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: '0.83rem', fontWeight: 600, color: 'var(--text)', lineHeight: 1.35 }}>
                        {ev.title}
                      </div>
                      {ev.subtitle && (
                        <div style={{ fontSize: '0.78rem', color: 'var(--muted)', marginTop: '0.15rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                          {ev.subtitle}
                        </div>
                      )}
                      <div style={{ fontSize: '0.72rem', color: 'var(--muted)', marginTop: '0.2rem' }}>
                        {timeAgo(ev.created_at)}
                      </div>
                    </div>
                  </div>
                ))
              )}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
