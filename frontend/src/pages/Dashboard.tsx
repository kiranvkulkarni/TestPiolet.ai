import { useQuery } from '@tanstack/react-query';
import { AlertTriangle, CalendarOff, CheckCircle2, ClipboardList, Loader2 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { dashboardApi } from '../api/endpoints';
import { Badge } from '../components/shared/Badge';
import { PRIORITY_COLORS } from '../utils/labels';
import type { Priority } from '../types';

function StatCard({
  label,
  value,
  accent,
  to,
}: {
  label: string;
  value: number | string;
  accent?: string;
  to?: string;
}) {
  const body = (
    <div className="rounded-xl border border-slate-200 bg-white p-4 hover:border-slate-300">
      <p className="text-xs font-medium text-slate-500 uppercase">{label}</p>
      <p className={`mt-1 text-2xl font-semibold ${accent ?? ''}`}>{value}</p>
    </div>
  );
  return to ? <Link to={to}>{body}</Link> : body;
}

export function Dashboard() {
  const { data: summary, isLoading } = useQuery({
    queryKey: ['dashboard', 'summary'],
    queryFn: dashboardApi.summary,
  });
  const { data: workload } = useQuery({
    queryKey: ['dashboard', 'team-workload'],
    queryFn: dashboardApi.teamWorkload,
  });
  const { data: overdue } = useQuery({
    queryKey: ['dashboard', 'overdue'],
    queryFn: dashboardApi.overdue,
  });
  const { data: progress } = useQuery({
    queryKey: ['dashboard', 'project-progress'],
    queryFn: dashboardApi.projectProgress,
  });
  const { data: leaves } = useQuery({
    queryKey: ['dashboard', 'upcoming-leaves'],
    queryFn: dashboardApi.upcomingLeaves,
  });

  if (isLoading) {
    return (
      <div className="flex h-64 items-center justify-center text-slate-400">
        <Loader2 className="animate-spin" />
      </div>
    );
  }

  const maxLoad = Math.max(1, ...(workload ?? []).map((w) => w.active_tasks));

  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold">Dashboard</h1>

      <div className="grid grid-cols-2 gap-3 md:grid-cols-3 lg:grid-cols-6">
        <StatCard label="Total tasks" value={summary?.total_tasks ?? 0} to="/tasks" />
        <StatCard label="In progress" value={summary?.in_progress ?? 0} accent="text-blue-600" />
        <StatCard label="Blocked" value={summary?.blocked ?? 0} accent="text-red-600" />
        <StatCard label="Completed" value={summary?.completed ?? 0} accent="text-green-600" />
        <StatCard label="Overdue" value={summary?.overdue ?? 0} accent="text-orange-600" />
        <StatCard label="Team" value={summary?.team_size ?? 0} to="/team" />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        {/* Team workload */}
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <ClipboardList size={15} className="text-indigo-500" /> Team workload (active tasks)
          </h2>
          <div className="space-y-2">
            {(workload ?? []).map((w) => (
              <div key={w.user_id} className="flex items-center gap-2 text-sm">
                <span className="w-32 truncate">{w.name}</span>
                <div className="h-2.5 flex-1 rounded-full bg-slate-100">
                  <div
                    className="h-2.5 rounded-full"
                    style={{
                      width: `${(w.active_tasks / maxLoad) * 100}%`,
                      backgroundColor: w.avatar_color ?? '#6366f1',
                    }}
                  />
                </div>
                <span className="w-16 text-right text-xs text-slate-500">
                  {w.active_tasks} · {w.estimated_hours}h
                </span>
              </div>
            ))}
          </div>
        </section>

        {/* Project progress */}
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <CheckCircle2 size={15} className="text-green-500" /> Project progress
          </h2>
          <div className="space-y-3">
            {(progress ?? []).map((p) => (
              <div key={p.project_id}>
                <div className="mb-1 flex justify-between text-sm">
                  <span>{p.name}</span>
                  <span className="text-xs text-slate-500">
                    {p.completed_tasks}/{p.total_tasks} · {p.percent_complete}%
                  </span>
                </div>
                <div className="h-2.5 rounded-full bg-slate-100">
                  <div
                    className="h-2.5 rounded-full"
                    style={{ width: `${p.percent_complete}%`, backgroundColor: p.color_hex }}
                  />
                </div>
              </div>
            ))}
            {(progress ?? []).length === 0 && (
              <p className="text-sm text-slate-400">No active projects.</p>
            )}
          </div>
        </section>

        {/* Overdue */}
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <AlertTriangle size={15} className="text-orange-500" /> Overdue tasks
          </h2>
          <div className="space-y-1.5">
            {(overdue ?? []).slice(0, 8).map((t) => (
              <div key={t.id} className="flex items-center justify-between gap-2 text-sm">
                <span className="truncate">{t.title}</span>
                <span className="flex shrink-0 items-center gap-2">
                  <Badge className={PRIORITY_COLORS[t.priority as Priority]}>{t.priority}</Badge>
                  <span className="text-xs text-red-600">{t.days_overdue}d late</span>
                </span>
              </div>
            ))}
            {(overdue ?? []).length === 0 && (
              <p className="text-sm text-slate-400">Nothing overdue. 🎉</p>
            )}
          </div>
        </section>

        {/* Upcoming leaves */}
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 flex items-center gap-2 text-sm font-semibold">
            <CalendarOff size={15} className="text-purple-500" /> Upcoming leaves (30 days)
          </h2>
          <div className="space-y-1.5">
            {(leaves ?? []).map((l) => (
              <div key={l.id} className="flex items-center justify-between text-sm">
                <span>{l.user_name}</span>
                <span className="text-xs text-slate-500">
                  {l.start_date} → {l.end_date} · {l.leave_type}
                </span>
              </div>
            ))}
            {(leaves ?? []).length === 0 && (
              <p className="text-sm text-slate-400">No approved leaves coming up.</p>
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
