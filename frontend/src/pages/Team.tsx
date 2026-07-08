import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus } from 'lucide-react';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../api/client';
import { dashboardApi, usersApi } from '../api/endpoints';
import { Avatar } from '../components/shared/Avatar';
import { Badge } from '../components/shared/Badge';
import { Field, inputClass } from '../components/shared/Field';
import { Modal } from '../components/shared/Modal';
import { useAuthStore } from '../store/authStore';
import type { User, UserRole } from '../types';

const ROLES: UserRole[] = ['manager', 'tester', 'viewer'];

export function Team() {
  const queryClient = useQueryClient();
  const isManager = useAuthStore((s) => s.user?.role === 'manager');
  const [editing, setEditing] = useState<User | null | 'new'>(null);
  const [form, setForm] = useState<Partial<User> & { password?: string }>({});

  const { data: users, isLoading } = useQuery({ queryKey: ['users'], queryFn: usersApi.list });
  const { data: workload } = useQuery({
    queryKey: ['dashboard', 'team-workload'],
    queryFn: dashboardApi.teamWorkload,
  });

  useEffect(() => {
    if (editing === 'new') setForm({ role: 'tester', is_active: true, avatar_color: '#6366f1' });
    else if (editing) setForm({ ...editing, password: undefined });
  }, [editing]);

  const save = useMutation({
    mutationFn: (data: Partial<User> & { password?: string }) => {
      if (editing === 'new' || !editing) {
        return usersApi.create(data as Partial<User> & { password: string });
      }
      const payload = { ...data };
      if (!payload.password) delete payload.password;
      return usersApi.update(editing.id, payload);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['users'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      toast.success('Saved');
      setEditing(null);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const loadFor = (id: number) => (workload ?? []).find((w) => w.user_id === id);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Team</h1>
        {isManager && (
          <button
            onClick={() => setEditing('new')}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <Plus size={15} /> Add member
          </button>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {(users ?? []).map((u) => {
          const load = loadFor(u.id);
          return (
            <button
              key={u.id}
              onClick={() => isManager && setEditing(u)}
              disabled={!isManager}
              className="rounded-xl border border-slate-200 bg-white p-4 text-left hover:border-slate-300 disabled:cursor-default"
            >
              <div className="flex items-center gap-3">
                <Avatar name={u.name} color={u.avatar_color} />
                <div className="min-w-0">
                  <p className="truncate font-medium">{u.name}</p>
                  <p className="truncate text-xs text-slate-400">{u.email}</p>
                </div>
                <span className="ml-auto flex flex-col items-end gap-1">
                  <Badge
                    className={
                      u.role === 'manager'
                        ? 'bg-purple-100 text-purple-700'
                        : u.role === 'tester'
                          ? 'bg-blue-100 text-blue-700'
                          : 'bg-slate-100 text-slate-500'
                    }
                  >
                    {u.role}
                  </Badge>
                  {!u.is_active && <Badge className="bg-red-100 text-red-600">inactive</Badge>}
                </span>
              </div>
              {load && u.role !== 'viewer' && (
                <p className="mt-2.5 text-xs text-slate-500">
                  {load.active_tasks} active tasks · {load.estimated_hours}h estimated
                </p>
              )}
            </button>
          );
        })}
      </div>

      <Modal
        open={!!editing}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'Add team member' : `Edit ${(editing as User)?.name}`}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!form.name || !form.email || (editing === 'new' && !form.password)) {
              toast.error('Name, email and password are required');
              return;
            }
            save.mutate(form);
          }}
          className="space-y-3"
        >
          <Field label="Name">
            <input className={inputClass} value={form.name ?? ''} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} autoFocus />
          </Field>
          <Field label="Email">
            <input className={inputClass} value={form.email ?? ''} onChange={(e) => setForm((f) => ({ ...f, email: e.target.value }))} />
          </Field>
          <Field label={editing === 'new' ? 'Password' : 'New password (leave blank to keep)'}>
            <input type="password" className={inputClass} value={form.password ?? ''} onChange={(e) => setForm((f) => ({ ...f, password: e.target.value || undefined }))} />
          </Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="Role">
              <select className={inputClass} value={form.role ?? 'tester'} onChange={(e) => setForm((f) => ({ ...f, role: e.target.value as UserRole }))}>
                {ROLES.map((r) => (
                  <option key={r} value={r}>{r}</option>
                ))}
              </select>
            </Field>
            <Field label="Color">
              <input type="color" className="h-9 w-full cursor-pointer rounded-lg border border-slate-300" value={form.avatar_color ?? '#6366f1'} onChange={(e) => setForm((f) => ({ ...f, avatar_color: e.target.value }))} />
            </Field>
            <Field label="Active">
              <select className={inputClass} value={form.is_active ? 'yes' : 'no'} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.value === 'yes' }))}>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </Field>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setEditing(null)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">Cancel</button>
            <button type="submit" disabled={save.isPending} className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </Modal>
    </div>
  );
}
