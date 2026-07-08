import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Kanban, List, Plus, Search, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../api/client';
import { projectsApi, tasksApi, usersApi, type TaskFilters } from '../api/endpoints';
import { Avatar } from '../components/shared/Avatar';
import { Badge } from '../components/shared/Badge';
import { ConfirmDialog } from '../components/shared/ConfirmDialog';
import { inputClass } from '../components/shared/Field';
import { TaskDetailModal } from '../components/tasks/TaskDetailModal';
import { TaskModal } from '../components/tasks/TaskModal';
import { useAuthStore } from '../store/authStore';
import type { Task, TaskStatus } from '../types';
import { cn } from '../utils/cn';
import {
  ALL_PRIORITIES,
  ALL_STATUSES,
  PRIORITY_COLORS,
  PRIORITY_LABELS,
  STATUS_COLORS,
  STATUS_LABELS,
  TASK_TYPE_LABELS,
} from '../utils/labels';

const KANBAN_COLUMNS: TaskStatus[] = ['pending', 'in_progress', 'blocked', 'completed'];

export function Tasks() {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const [view, setView] = useState<'list' | 'kanban'>('list');
  const [filters, setFilters] = useState<TaskFilters>({});
  const [search, setSearch] = useState('');
  const [editing, setEditing] = useState<Task | null>(null);
  const [creating, setCreating] = useState(false);
  const [detail, setDetail] = useState<Task | null>(null);
  const [deleting, setDeleting] = useState<Task | null>(null);

  const effectiveFilters = useMemo(
    () => ({ ...filters, search: search || undefined }),
    [filters, search],
  );

  const { data: tasks, isLoading } = useQuery({
    queryKey: ['tasks', 'list', effectiveFilters],
    queryFn: () => tasksApi.list(effectiveFilters),
  });
  const { data: users } = useQuery({ queryKey: ['users'], queryFn: usersApi.list });
  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list });

  const statusMutation = useMutation({
    mutationFn: ({ id, status }: { id: number; status: TaskStatus }) =>
      tasksApi.updateStatus(id, status),
    // optimistic update: flip the status in every cached task list immediately
    onMutate: async ({ id, status }) => {
      await queryClient.cancelQueries({ queryKey: ['tasks', 'list'] });
      const previous = queryClient.getQueriesData<Task[]>({ queryKey: ['tasks', 'list'] });
      queryClient.setQueriesData<Task[]>({ queryKey: ['tasks', 'list'] }, (old) =>
        old?.map((t) => (t.id === id ? { ...t, status } : t)),
      );
      return { previous };
    },
    onError: (e, _vars, ctx) => {
      ctx?.previous.forEach(([key, data]) => queryClient.setQueryData(key, data));
      toast.error(apiErrorMessage(e));
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => tasksApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      toast.success('Task deleted');
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const canEdit = user?.role !== 'viewer';

  const setFilter = (key: keyof TaskFilters, value: string) =>
    setFilters((f) => ({
      ...f,
      [key]: value === '' ? undefined : ['assigned_to', 'project_id'].includes(key) ? Number(value) : value,
    }));

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Tasks</h1>
        <div className="flex rounded-lg border border-slate-300 p-0.5">
          {(['list', 'kanban'] as const).map((v) => (
            <button
              key={v}
              onClick={() => setView(v)}
              className={cn(
                'flex items-center gap-1 rounded-md px-2.5 py-1 text-sm capitalize',
                view === v ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100',
              )}
            >
              {v === 'list' ? <List size={14} /> : <Kanban size={14} />} {v}
            </button>
          ))}
        </div>
        {canEdit && (
          <button
            onClick={() => setCreating(true)}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <Plus size={15} /> New task
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative">
          <Search size={14} className="absolute top-2.5 left-2.5 text-slate-400" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search title…"
            className={cn(inputClass, 'w-52 pl-8')}
          />
        </div>
        <select className={cn(inputClass, 'w-36')} value={filters.status ?? ''} onChange={(e) => setFilter('status', e.target.value)}>
          <option value="">All statuses</option>
          {ALL_STATUSES.map((s) => (
            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
          ))}
        </select>
        <select className={cn(inputClass, 'w-36')} value={filters.priority ?? ''} onChange={(e) => setFilter('priority', e.target.value)}>
          <option value="">All priorities</option>
          {ALL_PRIORITIES.map((p) => (
            <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>
          ))}
        </select>
        <select className={cn(inputClass, 'w-40')} value={filters.assigned_to ?? ''} onChange={(e) => setFilter('assigned_to', e.target.value)}>
          <option value="">All assignees</option>
          {(users ?? []).filter((u) => u.role !== 'viewer').map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
        <select className={cn(inputClass, 'w-44')} value={filters.project_id ?? ''} onChange={(e) => setFilter('project_id', e.target.value)}>
          <option value="">All projects</option>
          {(projects ?? []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={!!filters.overdue}
            onChange={(e) => setFilters((f) => ({ ...f, overdue: e.target.checked || undefined }))}
          />
          Overdue only
        </label>
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}

      {/* List view */}
      {view === 'list' && !isLoading && (
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-left text-xs text-slate-500 uppercase">
                <th className="px-3 py-2.5">Task</th>
                <th className="px-3 py-2.5">Type</th>
                <th className="px-3 py-2.5">Status</th>
                <th className="px-3 py-2.5">Priority</th>
                <th className="px-3 py-2.5">Assignee</th>
                <th className="px-3 py-2.5">Due</th>
                <th className="px-3 py-2.5">Est.</th>
                <th className="px-3 py-2.5"></th>
              </tr>
            </thead>
            <tbody>
              {(tasks ?? []).map((t) => (
                <tr key={t.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                  <td className="max-w-72 px-3 py-2">
                    <button onClick={() => setDetail(t)} className="truncate text-left font-medium hover:text-indigo-600">
                      {t.title}
                    </button>
                    <p className="text-xs text-slate-400">#{t.id}{t.device_model ? ` · ${t.device_model.model_name}` : ''}</p>
                  </td>
                  <td className="px-3 py-2 text-xs text-slate-600">{TASK_TYPE_LABELS[t.task_type]}</td>
                  <td className="px-3 py-2">
                    {canEdit ? (
                      <select
                        value={t.status}
                        onChange={(e) => statusMutation.mutate({ id: t.id, status: e.target.value as TaskStatus })}
                        className={cn('rounded-full border-0 px-2 py-0.5 text-xs font-medium', STATUS_COLORS[t.status])}
                      >
                        {ALL_STATUSES.map((s) => (
                          <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                        ))}
                      </select>
                    ) : (
                      <Badge className={STATUS_COLORS[t.status]}>{STATUS_LABELS[t.status]}</Badge>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    <Badge className={PRIORITY_COLORS[t.priority]}>{PRIORITY_LABELS[t.priority]}</Badge>
                  </td>
                  <td className="px-3 py-2">
                    {t.assignee ? (
                      <span className="flex items-center gap-1.5">
                        <Avatar name={t.assignee.name} color={t.assignee.avatar_color} size="sm" />
                        <span className="text-xs">{t.assignee.name}</span>
                      </span>
                    ) : (
                      <span className="text-xs text-slate-400">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs">{t.due_date ?? '—'}</td>
                  <td className="px-3 py-2 text-xs">{t.estimated_hours ? `${t.estimated_hours}h` : '—'}</td>
                  <td className="px-3 py-2 text-right">
                    {canEdit && (
                      <button
                        onClick={() => setDeleting(t)}
                        className="p-1 text-slate-300 hover:text-red-500"
                        aria-label="Delete task"
                      >
                        <Trash2 size={14} />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {(tasks ?? []).length === 0 && (
                <tr>
                  <td colSpan={8} className="px-3 py-8 text-center text-slate-400">
                    No tasks match the filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {/* Kanban view */}
      {view === 'kanban' && !isLoading && (
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
          {KANBAN_COLUMNS.map((col) => {
            const colTasks = (tasks ?? []).filter((t) => t.status === col);
            return (
              <div key={col} className="rounded-xl bg-slate-100 p-2">
                <div className="mb-2 flex items-center justify-between px-1">
                  <span className="text-xs font-semibold text-slate-600 uppercase">
                    {STATUS_LABELS[col]}
                  </span>
                  <span className="text-xs text-slate-400">{colTasks.length}</span>
                </div>
                <div
                  className="min-h-24 space-y-2"
                  onDragOver={(e) => e.preventDefault()}
                  onDrop={(e) => {
                    const id = Number(e.dataTransfer.getData('task-id'));
                    if (id && canEdit) statusMutation.mutate({ id, status: col });
                  }}
                >
                  {colTasks.map((t) => (
                    <div
                      key={t.id}
                      draggable={canEdit}
                      onDragStart={(e) => e.dataTransfer.setData('task-id', String(t.id))}
                      onClick={() => setDetail(t)}
                      className="cursor-pointer rounded-lg border border-slate-200 bg-white p-2.5 shadow-sm hover:border-indigo-300"
                    >
                      <p className="text-sm font-medium">{t.title}</p>
                      <div className="mt-1.5 flex items-center justify-between">
                        <Badge className={PRIORITY_COLORS[t.priority]}>{t.priority}</Badge>
                        {t.assignee && (
                          <Avatar name={t.assignee.name} color={t.assignee.avatar_color} size="sm" />
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      <TaskModal open={creating} onClose={() => setCreating(false)} />
      <TaskModal open={!!editing} onClose={() => setEditing(null)} task={editing} />
      <TaskDetailModal
        task={detail}
        onClose={() => setDetail(null)}
        onEdit={(t) => {
          setDetail(null);
          setEditing(t);
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        title="Delete task"
        message={`Delete "${deleting?.title}"? This also removes its comments and attachments.`}
        onConfirm={() => deleting && deleteMutation.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
