import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Check, Plus, Trash2, X } from 'lucide-react';
import { useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../api/client';
import { leavesApi, usersApi } from '../api/endpoints';
import { Avatar } from '../components/shared/Avatar';
import { Badge } from '../components/shared/Badge';
import { ConfirmDialog } from '../components/shared/ConfirmDialog';
import { Field, inputClass } from '../components/shared/Field';
import { Modal } from '../components/shared/Modal';
import { useAuthStore } from '../store/authStore';
import type { Leave, LeaveType } from '../types';

const LEAVE_TYPES: LeaveType[] = ['planned', 'sick', 'emergency', 'comp_off'];
const LEAVE_STATUS_COLORS = {
  pending: 'bg-amber-100 text-amber-700',
  approved: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
} as const;

export function Leaves() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const isManager = user?.role === 'manager';
  const [creating, setCreating] = useState(false);
  const [deleting, setDeleting] = useState<Leave | null>(null);
  const [form, setForm] = useState<Partial<Leave>>({});

  const { data: leaves, isLoading } = useQuery({ queryKey: ['leaves'], queryFn: () => leavesApi.list() });
  const { data: users } = useQuery({ queryKey: ['users'], queryFn: usersApi.list, enabled: isManager });

  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['leaves'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };

  const create = useMutation({
    mutationFn: (data: Partial<Leave>) => leavesApi.create(data),
    onSuccess: () => {
      invalidate();
      toast.success('Leave requested');
      setCreating(false);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const decide = useMutation({
    mutationFn: ({ id, status }: { id: number; status: 'approved' | 'rejected' }) =>
      leavesApi.approve(id, status),
    onSuccess: () => invalidate(),
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const remove = useMutation({
    mutationFn: (id: number) => leavesApi.remove(id),
    onSuccess: () => {
      invalidate();
      toast.success('Leave deleted');
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const openCreate = () => {
    setForm({ user_id: user?.id, leave_type: 'planned' });
    setCreating(true);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Leaves</h1>
        {user?.role !== 'viewer' && (
          <button
            onClick={openCreate}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <Plus size={15} /> Request leave
          </button>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500 uppercase">
              <th className="px-3 py-2.5">Member</th>
              <th className="px-3 py-2.5">From</th>
              <th className="px-3 py-2.5">To</th>
              <th className="px-3 py-2.5">Type</th>
              <th className="px-3 py-2.5">Reason</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {(leaves ?? []).map((l) => (
              <tr key={l.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-3 py-2">
                  <span className="flex items-center gap-1.5">
                    <Avatar name={l.user?.name ?? '?'} color={l.user?.avatar_color} size="sm" />
                    {l.user?.name}
                  </span>
                </td>
                <td className="px-3 py-2 text-xs">{l.start_date}</td>
                <td className="px-3 py-2 text-xs">{l.end_date}</td>
                <td className="px-3 py-2 text-xs">{l.leave_type.replace('_', ' ')}</td>
                <td className="max-w-52 truncate px-3 py-2 text-xs text-slate-500">{l.reason ?? '—'}</td>
                <td className="px-3 py-2">
                  <Badge className={LEAVE_STATUS_COLORS[l.status]}>{l.status}</Badge>
                </td>
                <td className="px-3 py-2">
                  <span className="flex items-center justify-end gap-1">
                    {isManager && l.status === 'pending' && (
                      <>
                        <button
                          onClick={() => decide.mutate({ id: l.id, status: 'approved' })}
                          className="rounded p-1 text-green-600 hover:bg-green-50"
                          aria-label="Approve"
                          title="Approve"
                        >
                          <Check size={15} />
                        </button>
                        <button
                          onClick={() => decide.mutate({ id: l.id, status: 'rejected' })}
                          className="rounded p-1 text-red-500 hover:bg-red-50"
                          aria-label="Reject"
                          title="Reject"
                        >
                          <X size={15} />
                        </button>
                      </>
                    )}
                    {(isManager || l.user_id === user?.id) && (
                      <button
                        onClick={() => setDeleting(l)}
                        className="p-1 text-slate-300 hover:text-red-500"
                        aria-label="Delete leave"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </span>
                </td>
              </tr>
            ))}
            {(leaves ?? []).length === 0 && !isLoading && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-slate-400">No leave records.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Modal open={creating} onClose={() => setCreating(false)} title="Request leave">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!form.user_id || !form.start_date || !form.end_date) {
              toast.error('Member and dates are required');
              return;
            }
            create.mutate(form);
          }}
          className="space-y-3"
        >
          {isManager && (
            <Field label="Member">
              <select className={inputClass} value={form.user_id ?? ''} onChange={(e) => setForm((f) => ({ ...f, user_id: Number(e.target.value) }))}>
                {(users ?? []).filter((u) => u.is_active).map((u) => (
                  <option key={u.id} value={u.id}>{u.name}</option>
                ))}
              </select>
            </Field>
          )}
          <div className="grid grid-cols-2 gap-3">
            <Field label="From">
              <input type="date" className={inputClass} value={form.start_date ?? ''} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} />
            </Field>
            <Field label="To">
              <input type="date" className={inputClass} value={form.end_date ?? ''} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))} />
            </Field>
          </div>
          <Field label="Type">
            <select className={inputClass} value={form.leave_type ?? 'planned'} onChange={(e) => setForm((f) => ({ ...f, leave_type: e.target.value as LeaveType }))}>
              {LEAVE_TYPES.map((t) => (
                <option key={t} value={t}>{t.replace('_', ' ')}</option>
              ))}
            </select>
          </Field>
          <Field label="Reason">
            <textarea className={inputClass} rows={2} value={form.reason ?? ''} onChange={(e) => setForm((f) => ({ ...f, reason: e.target.value || null }))} />
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setCreating(false)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">Cancel</button>
            <button type="submit" disabled={create.isPending} className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
              {create.isPending ? 'Submitting…' : 'Submit'}
            </button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        title="Delete leave"
        message={`Delete this leave (${deleting?.start_date} → ${deleting?.end_date})?`}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
