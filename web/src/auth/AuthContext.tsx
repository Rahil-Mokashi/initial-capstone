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
  login: (username: string, password: string) => Promise<User>;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const queryClient = useQueryClient();

  const clear = useCallback(() => {
    session.set(null);
    setUser(null);
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
      async login(username, password) {
        const result = await api.post<LoginResult>('/auth/login', { username, password });
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
        setUser(await api.get<User>('/auth/me'));
      },
    }),
    [user, clear],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside <AuthProvider>');
  return value;
}
