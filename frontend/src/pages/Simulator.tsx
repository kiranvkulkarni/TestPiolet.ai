/**
 * AI Timeline Simulator (E5): build a what-if scenario (leave / slip / scope),
 * run it non-destructively, compare baseline vs scenario, and apply ranked
 * mitigations through the normal audited endpoints.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { differenceInCalendarDays, parseISO } from 'date-fns';
import { AlertTriangle, FlaskConical, Play, Plus, Trash2, Wand2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../api/client';
import { projectsApi, simulationsApi, tasksApi, usersApi } from '../api/endpoints';
import { Badge } from '../components/shared/Badge';
import { inputClass } from '../components/shared/Field';
import type { Perturbation, SimMitigation, SimulationResult } from '../types';
import { cn } from '../utils/cn';

function describe(p: Perturbation, userName: (id: number) => string, taskTitle: (id: number) => string) {
  switch (p.type) {
    case 'leave':
      return `🏖 ${userName(p.user_id)} out ${p.start_date} → ${p.end_date}`;
    case 'slip':
      return `⏳ "${taskTitle(p.task_id)}" slips ${p.days} day(s)`;
    case 'remove_task':
      return `✂️ Remove "${taskTitle(p.task_id)}"`;
    case 'add_task':
      return `➕ Add "${p.title}" (${p.estimated_hours}h)`;
  }
}

export function Simulator() {
  const [projectId, setProjectId] = useState<number | undefined>();
  const [perturbations, setPerturbations] = useState<Perturbation[]>([]);
  const [result, setResult] = useState<SimulationResult | null>(null);
  const [appliedRanks, setAppliedRanks] = useState<Set<number>>(new Set());
  // builder state
  const [kind, setKind] = useState<Perturbation['type']>('leave');
  const [form, setForm] = useState<Record<string, string>>({});
  const queryClient = useQueryClient();

  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list });
  const { data: users } = useQuery({ queryKey: ['users'], queryFn: usersApi.list });
  const { data: ganttRows } = useQuery({
    queryKey: ['tasks', 'gantt', projectId, undefined],
    queryFn: () => tasksApi.gantt({ project_id: projectId }),
  });

  const testers = (users ?? []).filter((u) => u.is_active && u.role === 'tester');
  const scheduledTasks = ganttRows ?? [];
  const userName = (id: number) => (users ?? []).find((u) => u.id === id)?.name ?? `user ${id}`;
  const taskTitle = (id: number) =>
    scheduledTasks.find((t) => t.id === id)?.title ?? `task ${id}`;

  const run = useMutation({
    mutationFn: () => simulationsApi.run(perturbations, projectId),
    onSuccess: (data) => {
      setResult(data);
      setAppliedRanks(new Set());
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const applyMitigation = useMutation({
    mutationFn: async (m: SimMitigation) => {
      for (const t of m.apply.tasks) await tasksApi.update(t.id, t.fields);
      return m;
    },
    onSuccess: (m) => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      setAppliedRanks((prev) => new Set(prev).add(m.rank));
      toast.success(`Mitigation applied — ${m.apply.tasks.length} task(s) reassigned`);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const addPerturbation = () => {
    let p: Perturbation | null = null;
    if (kind === 'leave' && form.user_id && form.start_date && form.end_date) {
      p = { type: 'leave', user_id: Number(form.user_id), start_date: form.start_date, end_date: form.end_date };
    } else if (kind === 'slip' && form.task_id && form.days) {
      p = { type: 'slip', task_id: Number(form.task_id), days: Number(form.days) };
    } else if (kind === 'remove_task' && form.task_id) {
      p = { type: 'remove_task', task_id: Number(form.task_id) };
    } else if (kind === 'add_task' && form.title) {
      p = {
        type: 'add_task',
        title: form.title,
        estimated_hours: Number(form.estimated_hours) || 8,
        after_task_id: form.after_task_id ? Number(form.after_task_id) : null,
      };
    }
    if (!p) {
      toast.error('Fill in the scenario fields first');
      return;
    }
    setPerturbations((prev) => [...prev, p!]);
    setForm({});
    setResult(null);
  };

  // shared scale for the baseline-vs-scenario overlay
  const overlayRange = useMemo(() => {
    if (!result) return null;
    const dates: string[] = [];
    for (const t of result.affected_tasks) {
      if (t.baseline) dates.push(t.baseline.start, t.baseline.end);
      dates.push(t.scenario.start, t.scenario.end);
    }
    if (dates.length === 0) return null;
    const min = dates.reduce((m, d) => (d < m ? d : m));
    const max = dates.reduce((m, d) => (d > m ? d : m));
    return { min, total: Math.max(differenceInCalendarDays(parseISO(max), parseISO(min)) + 1, 1) };
  }, [result]);

  const bar = (span: { start: string; end: string }) => {
    if (!overlayRange) return { left: 0, width: 0 };
    const left =
      (differenceInCalendarDays(parseISO(span.start), parseISO(overlayRange.min)) /
        overlayRange.total) * 100;
    const width =
      ((differenceInCalendarDays(parseISO(span.end), parseISO(span.start)) + 1) /
        overlayRange.total) * 100;
    return { left, width: Math.max(width, 1) };
  };

  const taskField = (
    <select className={cn(inputClass, 'w-64')} value={form.task_id ?? ''} onChange={(e) => setForm((f) => ({ ...f, task_id: e.target.value }))}>
      <option value="">Pick a task…</option>
      {scheduledTasks.map((t) => (
        <option key={t.id} value={t.id}>#{t.id} · {t.title}</option>
      ))}
    </select>
  );

  return (
    <div className="space-y-4">
      <h1 className="flex items-center gap-2 text-xl font-semibold">
        <FlaskConical size={18} className="text-purple-500" /> Timeline Simulator
        <span className="text-xs font-normal text-slate-400">
          what-if only — the real plan is never touched until you apply a mitigation
        </span>
      </h1>

      {/* scenario builder */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <div className="flex flex-wrap items-center gap-2">
          <select className={cn(inputClass, 'w-52')} value={projectId ?? ''} onChange={(e) => { setProjectId(e.target.value ? Number(e.target.value) : undefined); setResult(null); }}>
            <option value="">All projects</option>
            {(projects ?? []).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <select className={cn(inputClass, 'w-40')} value={kind} onChange={(e) => { setKind(e.target.value as Perturbation['type']); setForm({}); }}>
            <option value="leave">Person on leave</option>
            <option value="slip">Task slips</option>
            <option value="remove_task">Remove task</option>
            <option value="add_task">Add scope</option>
          </select>

          {kind === 'leave' && (
            <>
              <select className={cn(inputClass, 'w-40')} value={form.user_id ?? ''} onChange={(e) => setForm((f) => ({ ...f, user_id: e.target.value }))}>
                <option value="">Who…</option>
                {testers.map((u) => (
                  <option key={u.id} value={u.id}>{u.name}</option>
                ))}
              </select>
              <input type="date" className={cn(inputClass, 'w-38')} value={form.start_date ?? ''} onChange={(e) => setForm((f) => ({ ...f, start_date: e.target.value }))} />
              <input type="date" className={cn(inputClass, 'w-38')} value={form.end_date ?? ''} onChange={(e) => setForm((f) => ({ ...f, end_date: e.target.value }))} />
            </>
          )}
          {kind === 'slip' && (
            <>
              {taskField}
              <input type="number" min={1} placeholder="days" className={cn(inputClass, 'w-20')} value={form.days ?? ''} onChange={(e) => setForm((f) => ({ ...f, days: e.target.value }))} />
            </>
          )}
          {kind === 'remove_task' && taskField}
          {kind === 'add_task' && (
            <>
              <input placeholder="New task title" className={cn(inputClass, 'w-52')} value={form.title ?? ''} onChange={(e) => setForm((f) => ({ ...f, title: e.target.value }))} />
              <input type="number" min={1} placeholder="est. h" className={cn(inputClass, 'w-20')} value={form.estimated_hours ?? ''} onChange={(e) => setForm((f) => ({ ...f, estimated_hours: e.target.value }))} />
              <select className={cn(inputClass, 'w-52')} value={form.after_task_id ?? ''} onChange={(e) => setForm((f) => ({ ...f, after_task_id: e.target.value }))}>
                <option value="">after nothing (parallel)</option>
                {scheduledTasks.map((t) => (
                  <option key={t.id} value={t.id}>after #{t.id} · {t.title}</option>
                ))}
              </select>
            </>
          )}
          <button onClick={addPerturbation} className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">
            <Plus size={14} /> Add to scenario
          </button>
        </div>

        {perturbations.length > 0 && (
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {perturbations.map((p, i) => (
              <span key={i} className="flex items-center gap-1.5 rounded-full bg-purple-50 px-3 py-1 text-xs text-purple-800">
                {describe(p, userName, taskTitle)}
                <button
                  onClick={() => { setPerturbations((prev) => prev.filter((_x, j) => j !== i)); setResult(null); }}
                  className="text-purple-300 hover:text-red-500"
                  aria-label="Remove perturbation"
                >
                  <Trash2 size={12} />
                </button>
              </span>
            ))}
            <button
              onClick={() => run.mutate()}
              disabled={run.isPending}
              className="ml-auto flex items-center gap-1.5 rounded-lg bg-purple-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-purple-700 disabled:opacity-50"
            >
              <Play size={14} /> {run.isPending ? 'Simulating…' : 'Run simulation'}
            </button>
          </div>
        )}
      </div>

      {result && (
        <>
          {/* impact summary */}
          <div
            className={cn(
              'rounded-xl border p-4 text-sm',
              result.predicted_delay_days > 0
                ? 'border-red-200 bg-red-50 text-red-800'
                : 'border-green-200 bg-green-50 text-green-800',
            )}
          >
            <p className="font-semibold">{result.summary}</p>
            <p className="mt-1 text-xs opacity-80">
              End date: {result.baseline.project_end} → {result.scenario.project_end}
              {result.predicted_delay_days > 0 && ` (+${result.predicted_delay_days} days)`}
              {' · '}critical path: {result.baseline.critical_path.length} → {result.scenario.critical_path.length} tasks
            </p>
            {result.warnings.map((w, i) => (
              <p key={i} className="mt-1 flex items-center gap-1 text-xs">
                <AlertTriangle size={12} /> {w}
              </p>
            ))}
          </div>

          {/* baseline vs scenario overlay */}
          {result.affected_tasks.length > 0 && overlayRange && (
            <section className="rounded-xl border border-slate-200 bg-white p-4">
              <h2 className="mb-2 text-sm font-semibold">
                Affected tasks — baseline (grey) vs scenario (colored)
              </h2>
              <div className="space-y-1.5">
                {result.affected_tasks.map((t) => (
                  <div key={t.id} className="flex items-center gap-2 text-xs">
                    <span className="w-64 truncate text-slate-600" title={t.title}>
                      {t.id < 0 && <Badge className="mr-1 bg-purple-100 text-purple-700">new</Badge>}
                      {t.title}
                      {t.became_critical && (
                        <Badge className="ml-1 bg-red-100 text-red-700">now critical</Badge>
                      )}
                    </span>
                    <div className="relative h-6 flex-1 rounded bg-slate-50">
                      {t.baseline && (
                        <div
                          className="absolute top-0.5 h-2 rounded bg-slate-300"
                          style={{ left: `${bar(t.baseline).left}%`, width: `${bar(t.baseline).width}%` }}
                          title={`baseline ${t.baseline.start} → ${t.baseline.end}`}
                        />
                      )}
                      <div
                        className={cn('absolute bottom-0.5 h-2 rounded', t.delay_days > 0 ? 'bg-red-400' : 'bg-purple-400')}
                        style={{ left: `${bar(t.scenario).left}%`, width: `${bar(t.scenario).width}%` }}
                        title={`scenario ${t.scenario.start} → ${t.scenario.end}`}
                      />
                    </div>
                    <span className={cn('w-16 text-right', t.delay_days > 0 ? 'text-red-600' : 'text-slate-400')}>
                      {t.delay_days > 0 ? `+${t.delay_days}d` : '±0d'}
                    </span>
                    <span className="w-24 truncate text-right text-slate-400">{t.assignee_name ?? '—'}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* mitigations */}
          {result.mitigations.length > 0 && (
            <section className="rounded-xl border border-slate-200 bg-white p-4">
              <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
                <Wand2 size={14} className="text-indigo-500" /> Ranked mitigations
              </h2>
              <div className="space-y-2">
                {result.mitigations.map((m) => (
                  <div key={m.rank} className="flex items-start gap-3 rounded-lg border border-slate-100 bg-slate-50/60 p-3">
                    <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-indigo-600 text-xs font-bold text-white">
                      {m.rank}
                    </span>
                    <div className="min-w-0 flex-1">
                      <p className="text-sm text-slate-700">{m.explanation}</p>
                      <p className="mt-0.5 text-xs text-slate-400">
                        recovers {m.recovers_days} day(s) · new end {m.new_project_end} · confidence{' '}
                        {Math.round(m.confidence * 100)}%
                      </p>
                    </div>
                    {appliedRanks.has(m.rank) ? (
                      <Badge className="bg-green-100 text-green-700">applied</Badge>
                    ) : (
                      <button
                        onClick={() => applyMitigation.mutate(m)}
                        disabled={applyMitigation.isPending}
                        className="shrink-0 rounded-lg bg-indigo-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                      >
                        Apply
                      </button>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          <p className="text-xs text-slate-400">{result.note}</p>
        </>
      )}
    </div>
  );
}
