import { useQueryClient } from '@tanstack/react-query';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import { api } from '@/api/client';
import { session } from '@/api/session';
import type { LoginResult, User } from '@/api/types';

interface AuthValue {
  user: User | null;
  /** Hiding is for clarity only; the server re-checks every call. */
  can: (permission: string) => boolean;
  login: (username: string, credential: string, usePin?: boolean) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
  /** The Lock screen: the session stays valid, but nothing can be used until the person re-confirms. */
  locked: boolean;
  lock: () => void;
  /** Re-confirm with password (or PIN); throws an ApiError with the server's message when wrong. */
  unlock: (credential: string, usePin?: boolean) => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [locked, setLocked] = useState(false);
  const queryClient = useQueryClient();

  const clear = useCallback(() => {
    session.set(null);
    setUser(null);
    setLocked(false);
    queryClient.clear();
  }, [queryClient]);

  useEffect(() => {
    session.onLost(clear);
    return () => session.onLost(null);
  }, [clear]);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      can: (permission) => user?.permissions.includes(permission) ?? false,
      async login(username, credential, usePin = false) {
        const result = await api.post<LoginResult>('/auth/login', {
          username,
          password: credential,
          use_pin: usePin,
        });
        session.set(result.token);
        setUser(result.user);
        return result.user;
      },
      async logout() {
        try {
          await api.post('/auth/logout');
        } catch {
          // Already signed out server-side; nothing more to do.
        }
        clear();
      },
      async refreshUser() {
        const fresh = await api.get<User>('/auth/me');
        // /auth/me reports this session's own sign-in; the account menu wants the PREVIOUS one.
        setUser((old) => ({ ...fresh, last_login: old?.last_login ?? fresh.last_login }));
      },
      locked,
      lock: () => setLocked(true),
      async unlock(credential, usePin = false) {
        await api.post('/auth/reauthenticate', { credential, use_pin: usePin });
        setLocked(false);
      },
    }),
    [user, locked, clear],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>');
  return value;
}
