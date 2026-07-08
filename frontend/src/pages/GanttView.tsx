import { useQuery } from '@tanstack/react-query';
import { Gantt, Task as GanttLibTask, ViewMode } from 'gantt-task-react';
import { useMemo, useState } from 'react';
import { projectsApi, tasksApi, usersApi } from '../api/endpoints';
import { inputClass } from '../components/shared/Field';
import { cn } from '../utils/cn';

const STATUS_BAR_COLORS: Record<string, { color: string; selected: string }> = {
  pending: { color: '#94a3b8', selected: '#64748b' },
  in_progress: { color: '#3b82f6', selected: '#2563eb' },
  blocked: { color: '#ef4444', selected: '#dc2626' },
  completed: { color: '#22c55e', selected: '#16a34a' },
  cancelled: { color: '#d4d4d8', selected: '#a1a1aa' },
};

export function GanttView() {
  const [projectId, setProjectId] = useState<number | undefined>();
  const [assigneeId, setAssigneeId] = useState<number | undefined>();
  const [viewMode, setViewMode] = useState<ViewMode>(ViewMode.Day);

  const { data: rows, isLoading } = useQuery({
    queryKey: ['tasks', 'gantt', projectId, assigneeId],
    queryFn: () => tasksApi.gantt({ project_id: projectId, assigned_to: assigneeId }),
  });
  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list });
  const { data: users } = useQuery({ queryKey: ['users'], queryFn: usersApi.list });

  const ganttTasks: GanttLibTask[] = useMemo(
    () =>
      (rows ?? []).map((t) => {
        const palette = STATUS_BAR_COLORS[t.status] ?? STATUS_BAR_COLORS.pending;
        return {
          id: String(t.id),
          name: `${t.title}${t.assignee_name ? ` · ${t.assignee_name}` : ''}`,
          start: new Date(t.start_date),
          end: new Date(t.due_date),
          progress: t.progress,
          type: 'task' as const,
          dependencies: t.depends_on ? [String(t.depends_on)] : [],
          styles: {
            backgroundColor: palette.color,
            backgroundSelectedColor: palette.selected,
            progressColor: t.project_color ?? '#6366f1',
            progressSelectedColor: t.project_color ?? '#4f46e5',
          },
        };
      }),
    [rows],
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Gantt</h1>
        <select
          className={cn(inputClass, 'w-44')}
          value={projectId ?? ''}
          onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">All projects</option>
          {(projects ?? []).map((p) => (
            <option key={p.id} value={p.id}>{p.name}</option>
          ))}
        </select>
        <select
          className={cn(inputClass, 'w-40')}
          value={assigneeId ?? ''}
          onChange={(e) => setAssigneeId(e.target.value ? Number(e.target.value) : undefined)}
        >
          <option value="">All assignees</option>
          {(users ?? []).filter((u) => u.role !== 'viewer').map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
        <div className="flex rounded-lg border border-slate-300 p-0.5">
          {([ViewMode.Day, ViewMode.Week, ViewMode.Month] as const).map((m) => (
            <button
              key={m}
              onClick={() => setViewMode(m)}
              className={cn(
                'rounded-md px-2.5 py-1 text-sm',
                viewMode === m ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100',
              )}
            >
              {m}
            </button>
          ))}
        </div>
      </div>

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white p-2">
        {isLoading && <p className="p-4 text-sm text-slate-400">Loading…</p>}
        {!isLoading && ganttTasks.length === 0 && (
          <p className="p-8 text-center text-sm text-slate-400">
            No scheduled tasks (tasks need both a start and a due date).
          </p>
        )}
        {ganttTasks.length > 0 && (
          <Gantt tasks={ganttTasks} viewMode={viewMode} listCellWidth="220px" columnWidth={viewMode === ViewMode.Month ? 200 : 60} />
        )}
      </div>

      <div className="flex flex-wrap gap-4 text-xs text-slate-500">
        {Object.entries(STATUS_BAR_COLORS).map(([status, { color }]) => (
          <span key={status} className="flex items-center gap-1.5 capitalize">
            <span className="h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: color }} />
            {status.replace('_', ' ')}
          </span>
        ))}
      </div>
    </div>
  );
}
