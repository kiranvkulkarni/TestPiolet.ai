import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../api/client';
import { projectsApi } from '../api/endpoints';
import { Badge } from '../components/shared/Badge';
import { ConfirmDialog } from '../components/shared/ConfirmDialog';
import { Field, inputClass } from '../components/shared/Field';
import { Modal } from '../components/shared/Modal';
import { useAuthStore } from '../store/authStore';
import type { Project, ProjectStatus } from '../types';

const PROJECT_STATUSES: ProjectStatus[] = ['active', 'completed', 'on_hold', 'cancelled'];
const PROJECT_STATUS_COLORS: Record<ProjectStatus, string> = {
  active: 'bg-green-100 text-green-700',
  completed: 'bg-blue-100 text-blue-700',
  on_hold: 'bg-amber-100 text-amber-700',
  cancelled: 'bg-zinc-100 text-zinc-500',
};

export function Projects() {
  const queryClient = useQueryClient();
  const isManager = useAuthStore((s) => s.user?.role === 'manager');
  const [editing, setEditing] = useState<Project | null | 'new'>(null);
  const [deleting, setDeleting] = useState<Project | null>(null);
  const [form, setForm] = useState<Partial<Project>>({});

  const { data: projects, isLoading } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list });

  useEffect(() => {
    if (editing === 'new') setForm({ status: 'active', color_hex: '#3b82f6' });
    else if (editing) setForm(editing);
  }, [editing]);

  const save = useMutation({
    mutationFn: (data: Partial<Project>) =>
      editing === 'new' || !editing ? projectsApi.create(data) : projectsApi.update(editing.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      toast.success('Saved');
      setEditing(null);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const remove = useMutation({
    mutationFn: (id: number) => projectsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['projects'] });
      toast.success('Project deleted');
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Projects</h1>
        {isManager && (
          <button
            onClick={() => setEditing('new')}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <Plus size={15} /> New project
          </button>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}

      <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-3">
        {(projects ?? []).map((p) => (
          <div
            key={p.id}
            className="group rounded-xl border border-slate-200 bg-white p-4 hover:border-slate-300"
          >
            <div className="flex items-start justify-between gap-2">
              <button
                onClick={() => isManager && setEditing(p)}
                className="flex items-center gap-2 text-left font-medium hover:text-indigo-600"
              >
                <span className="h-3 w-3 shrink-0 rounded-full" style={{ backgroundColor: p.color_hex }} />
                {p.name}
              </button>
              {isManager && (
                <button
                  onClick={() => setDeleting(p)}
                  className="p-1 text-slate-200 group-hover:text-slate-400 hover:!text-red-500"
                  aria-label="Delete project"
                >
                  <Trash2 size={14} />
                </button>
              )}
            </div>
            {p.description && <p className="mt-1.5 line-clamp-2 text-sm text-slate-500">{p.description}</p>}
            <div className="mt-3 flex items-center justify-between">
              <Badge className={PROJECT_STATUS_COLORS[p.status]}>{p.status.replace('_', ' ')}</Badge>
              <span className="text-xs text-slate-400">
                {p.start_date ?? '…'} → {p.end_date ?? '…'}
              </span>
            </div>
          </div>
        ))}
        {(projects ?? []).length === 0 && !isLoading && (
          <p className="text-sm text-slate-400">No projects yet.</p>
        )}
      </div>

      <Modal
        open={!!editing}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'New project' : `Edit ${(editing as Project)?.name}`}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!form.name) {
              toast.error('Name is required');
              return;
            }
            save.mutate(form);
          }}
          className="space-y-3"
        >
          <Field label="Name">
            <input className={inputClass} value={form.name ?? ''} onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))} autoFocus />
          </Field>
          <Field label="Description">
            <textarea className={inputClass} rows={2} value={form.description ?? ''} onChange={(e) => setForm((f) => ({ ...f, description: e.target.value || null }))} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Status">
              <select className={inputClass} value={form.status ?? 'active'} onChange={(e) => setForm((f) => ({ ...f, status: e.target.value as ProjectStatus }))}>
                {PROJECT_STATUSES.map((s) => (
                  <option key={s} value={s}>{s.replace('_', ' ')}</option>
                ))}
              </select>
            </Field>
            <Field label="Color">
              <input type="color" className="h-9 w-full cursor-pointer rounded-lg border border-slate-300" value={form.color_hex ?? '#3b82f6'} onChange={(e) => setForm((f) => ({ ...f, color_hex: e.target.value }))} />
            </Field>
            <Field label="Start date">
              <input type="date" className={inputClass} value={form.start_date ?? ''} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value || null }))} />
            </Field>
            <Field label="End date">
              <input type="date" className={inputClass} value={form.end_date ?? ''} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value || null }))} />
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

      <ConfirmDialog
        open={!!deleting}
        title="Delete project"
        message={`Delete "${deleting?.name}" including all its test requests and tasks?`}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
