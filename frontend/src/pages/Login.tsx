import { useState } from 'react';
import toast from 'react-hot-toast';
import { useNavigate } from 'react-router-dom';
import { apiErrorMessage } from '../api/client';
import { authApi } from '../api/endpoints';
import { inputClass } from '../components/shared/Field';
import { useAuthStore } from '../store/authStore';

export function Login() {
  const [email, setEmail] = useState('admin@qa.local');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const login = useAuthStore((s) => s.login);
  const navigate = useNavigate();

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    try {
      const data = await authApi.login(email, password);
      login(data.access_token, data.user);
      navigate('/');
    } catch (error) {
      toast.error(apiErrorMessage(error));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-100 p-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-8 shadow-sm"
      >
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600 font-bold text-white">
            QA
          </span>
          <div>
            <h1 className="font-semibold">QA Task Assigner</h1>
            <p className="text-xs text-slate-500">Samsung Android QA · on-prem AI</p>
          </div>
        </div>
        <div className="space-y-3">
          <input
            type="text"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            autoFocus
            className={inputClass}
          />
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className={inputClass}
          />
          <button
            type="submit"
            disabled={busy || !email || !password}
            className="w-full rounded-lg bg-indigo-600 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {busy ? 'Signing in…' : 'Sign in'}
          </button>
        </div>
        <p className="mt-4 text-center text-xs text-slate-400">
          Demo: admin@qa.local / admin123 · priya@qa.local / tester123
        </p>
      </form>
    </div>
  );
}
