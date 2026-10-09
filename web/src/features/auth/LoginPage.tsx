import { zodResolver } from '@hookform/resolvers/zod';
import { Fuel } from 'lucide-react';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { Navigate, useLocation } from 'react-router-dom';
import { z } from 'zod';
import { ApiError } from '@/api/errors';
import { useAuth } from '@/auth/AuthContext';
import { Button } from '@/components/ui/Button';
import { TextField } from '@/components/ui/Field';

const schema = z.object({
  username: z.string().trim().min(1, 'Enter your username.'),
  password: z.string().min(1, 'Enter your password.'),
});
type Values = z.infer<typeof schema>;

export function LoginPage() {
  const { user, login } = useAuth();
  const location = useLocation();
  const [formError, setFormError] = useState<string | null>(null);
  const {
    register,
    handleSubmit,
    formState: { errors, isSubmitting },
  } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { username: '', password: '' },
  });

  if (user) {
    const from = (location.state as { from?: string } | null)?.from ?? '/tanks';
    return <Navigate to={from} replace />;
  }

  const onSubmit = handleSubmit(async (values) => {
    setFormError(null);
    try {
      await login(values.username, values.password);
    } catch (error) {
      setFormError(
        error instanceof ApiError ? error.message : 'Could not sign in. Please try again.',
      );
    }
  });

  return (
    <div className="grid min-h-full lg:grid-cols-[1.1fr_1fr]">
      <section className="hidden flex-col justify-between bg-ink p-12 text-ink-fg lg:flex">
        <div className="flex items-center gap-3">
          <span className="flex size-12 items-center justify-center rounded-lg bg-primary text-primary-fg">
            <Fuel className="size-6" aria-hidden />
          </span>
          <span className="text-xl font-bold">Petrol Pump ERP</span>
        </div>
        <div>
          <h1 className="max-w-md text-4xl leading-tight font-bold">Every litre accounted for.</h1>
          <p className="mt-4 max-w-md text-ink-muted">
            Tanks, shifts, sales and cash in one place - working entirely on this PC, with no
            internet needed.
          </p>
        </div>
        <p className="text-xs text-ink-muted">Works offline. Your data stays on this computer.</p>
      </section>

      <main className="flex items-center justify-center p-6">
        <form
          onSubmit={onSubmit}
          noValidate
          className="flex w-full max-w-sm flex-col gap-5"
          aria-labelledby="login-title"
        >
          <div>
            <h2 id="login-title" className="text-2xl font-bold">
              Sign in
            </h2>
            <p className="mt-1 text-sm text-muted">
              Use the username and password your manager gave you.
            </p>
          </div>

          {formError && (
            <p
              role="alert"
              className="rounded-md border border-danger bg-danger-bg p-3 text-sm font-medium text-danger-fg"
            >
              {formError}
            </p>
          )}

          <TextField
            label="Username"
            autoComplete="username"
            autoFocus
            error={errors.username?.message}
            {...register('username')}
          />
          <TextField
            label="Password"
            type="password"
            autoComplete="current-password"
            error={errors.password?.message}
            {...register('password')}
          />
          <Button
            type="submit"
            variant="primary"
            loading={isSubmitting}
            className="min-h-[48px] text-base"
          >
            Sign in
          </Button>
        </form>
      </main>
    </div>
  );
}
