import { type ReactNode } from 'react'
import { useAppData } from '../store/AppDataContext'

/**
 * v1.40.1 auth gate. The SPA no longer "fails open" to demo/mock mode: nothing below
 * this component mounts until AppDataContext confirms a live, authenticated session.
 *
 *   'loading' → a bare full-screen spinner (no app chrome, no menus, no data).
 *   'live'    → render the app.
 *   'mock'    → the session check failed for a NON-auth reason (backend unreachable).
 *               A 401/403 already redirected to the server /login inside AppDataContext,
 *               so reaching here means "can't reach the server" — show a reconnect panel.
 *
 * The unauthenticated → /login redirect is enforced twice: server-side (the /mes-app/*
 * shell gate in main.py — the hard guarantee) and client-side (AppDataContext).
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { apiMode } = useAppData()

  if (apiMode === 'live') return <>{children}</>

  const offline = apiMode === 'mock'
  return (
    <div
      role="status"
      aria-live="polite"
      style={{
        position: 'fixed', inset: 0, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center', gap: 16,
        background: '#0f1115', color: '#c8ccd4',
        fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif',
      }}
    >
      {offline ? (
        <>
          <div style={{ fontSize: 15 }}>Can’t reach the server.</div>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: '8px 18px', borderRadius: 6, border: '1px solid #2a2f3a',
              background: '#1a1d24', color: '#c8ccd4', cursor: 'pointer', fontSize: 13,
            }}
          >
            Retry
          </button>
        </>
      ) : (
        <div
          aria-label="Loading"
          style={{
            width: 34, height: 34, borderRadius: '50%',
            border: '3px solid #2a2f3a', borderTopColor: '#6ea8fe',
            animation: 'authgate-spin 0.8s linear infinite',
          }}
        />
      )}
      <style>{'@keyframes authgate-spin{to{transform:rotate(360deg)}}'}</style>
    </div>
  )
}
