import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../api/client';
import { projectsApi, testCyclesApi, testRequestsApi } from '../api/endpoints';
import { Badge } from '../components/shared/Badge';
import { ConfirmDialog } from '../components/shared/ConfirmDialog';
import { Field, inputClass } from '../components/shared/Field';
import { Modal } from '../components/shared/Modal';
import { useAuthStore } from '../store/authStore';
import type { RequestStatus, TestRequest } from '../types';
import { cn } from '../utils/cn';
import { ALL_PRIORITIES, PRIORITY_COLORS, PRIORITY_LABELS } from '../utils/labels';

const REQUEST_STATUSES: RequestStatus[] = ['open', 'in_progress', 'completed', 'cancelled'];
const REQUEST_STATUS_COLORS: Record<RequestStatus, string> = {
  open: 'bg-blue-100 text-blue-700',
  in_progress: 'bg-indigo-100 text-indigo-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-zinc-100 text-zinc-500',
};

export function TestRequests() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const canEdit = user?.role !== 'viewer';
  const [editing, setEditing] = useState<TestRequest | null | 'new'>(null);
  const [deleting, setDeleting] = useState<TestRequest | null>(null);
  const [projectFilter, setProjectFilter] = useState<number | undefined>();
  const [form, setForm] = useState<Partial<TestRequest>>({});

  const { data: requests, isLoading } = useQuery({
    queryKey: ['test-requests', projectFilter],
    queryFn: () => testRequestsApi.list(projectFilter ? { project_id: projectFilter } : undefined),
  });
  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list });
  const { data: cycles } = useQuery({
    queryKey: ['test-cycles', form.project_id],
    queryFn: () => testCyclesApi.list(form.project_id ?? undefined),
    enabled: !!editing,
  });

  useEffect(() => {
    if (editing === 'new') setForm({ priority: 'medium', status: 'open' });
    else if (editing) setForm(editing);
  }, [editing]);

  const save = useMutation({
    mutationFn: (data: Partial<TestRequest>) =>
      editing === 'new' || !editing
        ? testRequestsApi.create(data)
        : testRequestsApi.update(editing.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['test-requests'] });
      toast.success('Saved');
      setEditing(null);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const remove = useMutation({
    mutationFn: (id: number) => testRequestsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['test-requests'] });
      toast.success('Request deleted');
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const projectName = (id: number) => (projects ?? []).find((p) => p.id === id)?.name ?? `#${id}`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Test Requests</h1>
        <select
          className={cn(inputClass, 'w-44')}
          value={projectFilter ?? ''}
          onChange={(e) => setProjectFilter(e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">All projects</option>
          {(projects ?? []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        {canEdit && (
          <button
            onClick={() => setEditing('new')}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <Plus size={15} /> New request
          </button>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500 uppercase">
              <th className="px-3 py-2.5">Request</th>
              <th className="px-3 py-2.5">Project</th>
              <th className="px-3 py-2.5">Requested by</th>
              <th className="px-3 py-2.5">Priority</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5">Tasks</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {(requests ?? []).map((r) => (
              <tr key={r.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="max-w-80 px-3 py-2">
                  <button
                    onClick={() => canEdit && setEditing(r)}
                    className="truncate text-left font-medium hover:text-indigo-600"
                  >
                    {r.title}
                  </button>
                  <p className="text-xs text-slate-400">#{r.id}</p>
                </td>
                <td className="px-3 py-2 text-xs">{projectName(r.project_id)}</td>
                <td className="px-3 py-2 text-xs">{r.requested_by ?? '—'}</td>
                <td className="px-3 py-2">
                  <Badge className={PRIORITY_COLORS[r.priority]}>{PRIORITY_LABELS[r.priority]}</Badge>
                </td>
                <td className="px-3 py-2">
                  <Badge className={REQUEST_STATUS_COLORS[r.status]}>{r.status.replace('_', ' ')}</Badge>
                </td>
                <td className="px-3 py-2 text-xs">{r.task_count}</td>
                <td className="px-3 py-2 text-right">
                  {canEdit && (
                    <button
                      onClick={() => setDeleting(r)}
                      className="p-1 text-slate-300 hover:text-red-500"
                      aria-label="Delete request"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {(requests ?? []).length === 0 && !isLoading && (
              <tr>
                <td colSpan={7} className="px-3 py-8 text-center text-slate-400">No test requests.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Modal
        open={!!editing}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'New test request' : `Edit request #${(editing as TestRequest)?.id}`}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!form.title || !form.project_id) {
              toast.error('Title and project are required');
              return;
            }
            save.mutate(form);
          }}
          className="space-y-3"
        >
          <Field label="Title">
            <input className={inputClass} value={form.title ?? ''} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} autoFocus />
          </Field>
          <Field label="Project">
            <select
              className={inputClass}
              value={form.project_id ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, project_id: Number(e.target.value), test_cycle_id: null }))}
            >
              <option value="">Select…</option>
              {(projects ?? []).map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
          </Field>
          <Field label="Test cycle (optional)">
            <select
              className={inputClass}
              value={form.test_cycle_id ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, test_cycle_id: e.target.value ? Number(e.target.value) : null }))}
            >
              <option value="">None</option>
              {(cycles ?? []).filter((c) => c.project_id === form.project_id).map((c) => (
                <option key={c.id} value={c.id}>{c.name}</option>
              ))}
            </select>
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Priority">
              <select className={inputClass} value={form.priority ?? 'medium'} onChange={(e) => setForm((f) => ({ ...f, priority: e.target.value as TestRequest['priority'] }))}>
                {ALL_PRIORITIES.map((p) => (
                  <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>
                ))}
              </select>
            </Field>
            <Field label="Status">
              <select className={inputClass} value={form.status ?? 'open'} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as RequestStatus }))}>
                {REQUEST_STATUSES.map((s) => (
                  <option key={s} value={s}>{s.replace('_', ' ')}</option>
                ))}
              </select>
            </Field>
          </div>
          <Field label="Requested by">
            <input className={inputClass} value={form.requested_by ?? ''} onChange={(e) => setForm((f) => ({ ...f, requested_by: e.target.value || null }))} />
          </Field>
          <Field label="Description">
            <textarea className={inputClass} rows={3} value={form.description ?? ''} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value || null }))} />
          </Field>
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setEditing(null)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
              Cancel
            </button>
            <button type="submit" disabled={save.isPending} className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        title="Delete test request"
        message={`Delete "${deleting?.title}" and all ${deleting?.task_count ?? 0} tasks under it?`}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
