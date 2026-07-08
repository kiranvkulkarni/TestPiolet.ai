/**
 * AI Project Planner (E4): brief → editable draft (requests, tasks, estimates,
 * assignments, dependencies, scheduled timeline) → explicit Commit.
 * Nothing is written until Commit; "Re-schedule" re-validates edits server-side.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { differenceInCalendarDays, parseISO } from 'date-fns';
import { AlertTriangle, CalendarClock, Check, RefreshCw, Sparkles } from 'lucide-react';
import { useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { Link, useNavigate } from 'react-router-dom';
import { apiErrorMessage } from '../api/client';
import { agentApi, deviceModelsApi, projectsApi, usersApi } from '../api/endpoints';
import { inputClass } from '../components/shared/Field';
import type { DraftTask, PlanDraft } from '../types';
import { cn } from '../utils/cn';
import {
  ALL_PRIORITIES,
  ALL_TASK_TYPES,
  PRIORITY_LABELS,
  TASK_TYPE_LABELS,
} from '../utils/labels';

const EXAMPLE =
  'Galaxy Camera v16 next week — HDR, Night Mode, Portrait Video, 50MP, Expert RAW; ' +
  '5 testers, 2 devices, 3 working days';

export function Planner() {
  const [brief, setBrief] = useState('');
  const [projectId, setProjectId] = useState<number | undefined>();
  const [draft, setDraft] = useState<PlanDraft | null>(null);
  const [dirty, setDirty] = useState(false);
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const { data: status } = useQuery({ queryKey: ['agent', 'status'], queryFn: agentApi.status });
  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list });
  const { data: users } = useQuery({ queryKey: ['users'], queryFn: usersApi.list });
  const { data: devices } = useQuery({
    queryKey: ['device-models'],
    queryFn: () => deviceModelsApi.list(true),
  });

  const generate = useMutation({
    mutationFn: () => agentApi.plan(brief, projectId),
    onSuccess: (data) => {
      setDraft(data);
      setDirty(false);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const refresh = useMutation({
    mutationFn: (d: PlanDraft) => agentApi.planRefresh({ ...d, project_id: projectId ?? d.project_id }),
    onSuccess: (data) => {
      setDraft(data);
      setDirty(false);
      toast.success('Schedule recomputed');
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const commit = useMutation({
    mutationFn: (d: PlanDraft) => agentApi.planCommit({ ...d, project_id: projectId ?? d.project_id }),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['test-requests'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      toast.success(result.rationale, { duration: 6000 });
      navigate('/gantt');
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const setTask = (reqIdx: number, taskIdx: number, patch: Partial<DraftTask>) => {
    setDraft((d) => {
      if (!d) return d;
      const requests = d.requests.map((r, i) =>
        i !== reqIdx
          ? r
          : { ...r, tasks: r.tasks.map((t, j) => (j !== taskIdx ? t : { ...t, ...patch })) },
      );
      return { ...d, requests };
    });
    setDirty(true);
  };

  const flat = useMemo(() => draft?.requests.flatMap((r) => r.tasks) ?? [], [draft]);
  const range = useMemo(() => {
    const dated = flat.filter((t) => t.start_date && t.due_date);
    if (dated.length === 0) return null;
    const min = dated.reduce((m, t) => (t.start_date! < m ? t.start_date! : m), dated[0].start_date!);
    const max = dated.reduce((m, t) => (t.due_date! > m ? t.due_date! : m), dated[0].due_date!);
    const total = differenceInCalendarDays(parseISO(max), parseISO(min)) + 1;
    return { min, total: Math.max(total, 1) };
  }, [flat]);

  const testers = (users ?? []).filter((u) => u.is_active && u.role === 'tester');

  return (
    <div className="space-y-4">
      <h1 className="flex items-center gap-2 text-xl font-semibold">
        <Sparkles size={18} className="text-indigo-500" /> AI Project Planner
      </h1>

      {/* brief input */}
      <div className="rounded-xl border border-slate-200 bg-white p-4">
        <textarea
          value={brief}
          onChange={(e) => setBrief(e.target.value)}
          rows={3}
          placeholder={`Describe the test effort in plain English, e.g.\n“${EXAMPLE}”`}
          className={cn(inputClass, 'resize-y')}
        />
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <select
            className={cn(inputClass, 'w-56')}
            value={projectId ?? ''}
            onChange={(e) => setProjectId(e.target.value ? Number(e.target.value) : undefined)}
          >
            <option value="">Target project…</option>
            {(projects ?? []).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
          <button
            onClick={() => generate.mutate()}
            disabled={!status?.enabled || brief.trim().length < 10 || generate.isPending}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            <Sparkles size={14} />
            {generate.isPending ? 'Planning…' : 'Generate plan'}
          </button>
          {!status?.enabled && (
            <span className="text-xs text-amber-600">
              Agent disabled — set AGENT_ENABLED=true and run a local LLM to generate plans.
            </span>
          )}
        </div>
      </div>

      {draft && (
        <>
          {/* rationale + warnings */}
          {draft.rationale && (
            <p className="rounded-xl border border-indigo-100 bg-indigo-50/60 p-3 text-sm text-slate-700">
              🧠 {draft.rationale}
            </p>
          )}
          {draft.warnings.length > 0 && (
            <div className="rounded-xl border border-amber-200 bg-amber-50 p-3 text-sm text-amber-800">
              {draft.warnings.map((w, i) => (
                <p key={i} className="flex items-start gap-1.5">
                  <AlertTriangle size={14} className="mt-0.5 shrink-0" /> {w}
                </p>
              ))}
            </div>
          )}

          {/* editable plan */}
          {draft.requests.map((req, ri) => (
            <section key={ri} className="rounded-xl border border-slate-200 bg-white">
              <div className="border-b border-slate-100 px-4 py-2.5 text-sm font-semibold">
                {req.title}
                <span className="ml-2 text-xs font-normal text-slate-400 capitalize">
                  {req.priority} · {req.tasks.length} tasks
                </span>
              </div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500 uppercase">
                    <th className="px-3 py-2">Task</th>
                    <th className="px-3 py-2">Type</th>
                    <th className="px-3 py-2">Est. h</th>
                    <th className="px-3 py-2">Assignee</th>
                    <th className="px-3 py-2">Device</th>
                    <th className="px-3 py-2">Priority</th>
                    <th className="px-3 py-2">Schedule</th>
                    <th className="px-3 py-2">After</th>
                  </tr>
                </thead>
                <tbody>
                  {req.tasks.map((t, ti) => (
                    <tr key={t.ref} className="border-t border-slate-100">
                      <td className="px-3 py-1.5">
                        <input
                          className={cn(inputClass, 'min-w-44')}
                          value={t.title}
                          onChange={(e) => setTask(ri, ti, { title: e.target.value })}
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <select
                          className={cn(inputClass, 'w-44')}
                          value={t.task_type}
                          onChange={(e) => setTask(ri, ti, { task_type: e.target.value as DraftTask['task_type'] })}
                        >
                          {ALL_TASK_TYPES.map((tt) => (
                            <option key={tt} value={tt}>{TASK_TYPE_LABELS[tt]}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-1.5">
                        <input
                          type="number"
                          min={1}
                          step={1}
                          className={cn(inputClass, 'w-16')}
                          value={t.estimated_hours}
                          onChange={(e) => setTask(ri, ti, { estimated_hours: Number(e.target.value) || 1 })}
                        />
                      </td>
                      <td className="px-3 py-1.5">
                        <select
                          className={cn(inputClass, 'w-32')}
                          value={t.assigned_to ?? ''}
                          onChange={(e) => {
                            const id = e.target.value ? Number(e.target.value) : null;
                            setTask(ri, ti, {
                              assigned_to: id,
                              assignee_name: testers.find((u) => u.id === id)?.name ?? null,
                            });
                          }}
                        >
                          <option value="">auto</option>
                          {testers.map((u) => (
                            <option key={u.id} value={u.id}>{u.name}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-1.5">
                        <select
                          className={cn(inputClass, 'w-40')}
                          value={t.device_model_id ?? ''}
                          onChange={(e) =>
                            setTask(ri, ti, {
                              device_model_id: e.target.value ? Number(e.target.value) : null,
                            })
                          }
                        >
                          <option value="">none</option>
                          {(devices ?? []).map((d) => (
                            <option key={d.id} value={d.id}>{d.model_name}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-1.5">
                        <select
                          className={cn(inputClass, 'w-24')}
                          value={t.priority}
                          onChange={(e) => setTask(ri, ti, { priority: e.target.value as DraftTask['priority'] })}
                        >
                          {ALL_PRIORITIES.map((p) => (
                            <option key={p} value={p}>{PRIORITY_LABELS[p]}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-1.5 text-xs whitespace-nowrap text-slate-500">
                        {t.start_date} → {t.due_date}
                      </td>
                      <td className="px-3 py-1.5 text-xs text-slate-400">
                        {t.depends_on_refs.join(', ') || '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}

          {/* mini timeline */}
          {range && (
            <section className="rounded-xl border border-slate-200 bg-white p-4">
              <h2 className="mb-2 flex items-center gap-1.5 text-sm font-semibold">
                <CalendarClock size={14} className="text-indigo-500" /> Draft timeline
                <span className="ml-auto text-xs font-normal text-slate-400">
                  {draft.start_date} → {draft.project_end}
                </span>
              </h2>
              <div className="space-y-1">
                {flat.map((t) => {
                  if (!t.start_date || !t.due_date) return null;
                  const left =
                    (differenceInCalendarDays(parseISO(t.start_date), parseISO(range.min)) /
                      range.total) * 100;
                  const width =
                    ((differenceInCalendarDays(parseISO(t.due_date), parseISO(t.start_date)) + 1) /
                      range.total) * 100;
                  return (
                    <div key={t.ref} className="flex items-center gap-2 text-xs">
                      <span className="w-56 truncate text-slate-600">{t.title}</span>
                      <div className="relative h-4 flex-1 rounded bg-slate-50">
                        <div
                          className="absolute h-4 rounded bg-indigo-400"
                          style={{ left: `${left}%`, width: `${Math.max(width, 1.5)}%` }}
                          title={`${t.start_date} → ${t.due_date} · ${t.assignee_name ?? 'unassigned'}`}
                        />
                      </div>
                      <span className="w-20 truncate text-right text-slate-400">
                        {t.assignee_name ?? '—'}
                      </span>
                    </div>
                  );
                })}
              </div>
            </section>
          )}

          {/* actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => draft && refresh.mutate(draft)}
              disabled={refresh.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50 disabled:opacity-50"
            >
              <RefreshCw size={14} className={refresh.isPending ? 'animate-spin' : ''} />
              Re-schedule edits
            </button>
            <button
              onClick={() => draft && commit.mutate(draft)}
              disabled={commit.isPending || !(projectId ?? draft.project_id) || flat.length === 0}
              className="flex items-center gap-1.5 rounded-lg bg-green-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-green-700 disabled:opacity-50"
              title={!(projectId ?? draft.project_id) ? 'Pick a target project first' : undefined}
            >
              <Check size={15} />
              {commit.isPending ? 'Committing…' : `Commit ${flat.length} tasks`}
            </button>
            {dirty && (
              <span className="text-xs text-amber-600">
                Edited since last scheduling — “Re-schedule edits” updates dates and warnings.
              </span>
            )}
            <span className="ml-auto text-xs text-slate-400">
              Nothing is created until you commit. Committed plans appear in the{' '}
              <Link to="/gantt" className="text-indigo-600 hover:underline">Gantt</Link>.
            </span>
          </div>
        </>
      )}
    </div>
  );
}
