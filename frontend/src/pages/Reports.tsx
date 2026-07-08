import { useQuery } from '@tanstack/react-query';
import { Download } from 'lucide-react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { api } from '../api/client';
import { dashboardApi } from '../api/endpoints';
import type { TaskType } from '../types';
import { TASK_TYPE_LABELS } from '../utils/labels';

const PIE_COLORS = [
  '#3b82f6', '#22c55e', '#f97316', '#8b5cf6', '#ef4444', '#06b6d4', '#eab308',
  '#ec4899', '#14b8a6', '#6366f1', '#f43f5e', '#84cc16', '#a855f7', '#0ea5e9', '#f59e0b',
];

export function Reports() {
  const { data: workload } = useQuery({
    queryKey: ['dashboard', 'team-workload'],
    queryFn: dashboardApi.teamWorkload,
  });
  const { data: taskTypes } = useQuery({
    queryKey: ['dashboard', 'task-types'],
    queryFn: dashboardApi.taskTypes,
  });
  const { data: progress } = useQuery({
    queryKey: ['dashboard', 'project-progress'],
    queryFn: dashboardApi.projectProgress,
  });

  const typeData = (taskTypes ?? []).map((t) => ({
    name: TASK_TYPE_LABELS[t.task_type as TaskType] ?? t.task_type,
    value: t.count,
  }));

  const workloadData = (workload ?? []).map((w) => ({
    name: w.name.split(' ')[0],
    tasks: w.active_tasks,
    hours: w.estimated_hours,
  }));

  const exportCsv = async () => {
    const response = await api.get('/dashboard/export/tasks', { responseType: 'blob' });
    const url = URL.createObjectURL(response.data);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'tasks.csv';
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Reports</h1>
        <button
          onClick={exportCsv}
          className="flex items-center gap-1.5 rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
        >
          <Download size={15} /> Export tasks CSV
        </button>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">Active workload by tester</h2>
          <ResponsiveContainer width="100%" height={280}>
            <BarChart data={workloadData}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="name" tick={{ fontSize: 12 }} />
              <YAxis tick={{ fontSize: 12 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Bar dataKey="tasks" name="Active tasks" fill="#6366f1" radius={[4, 4, 0, 0]} />
              <Bar dataKey="hours" name="Est. hours" fill="#c7d2fe" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4">
          <h2 className="mb-3 text-sm font-semibold">Tasks by type</h2>
          <ResponsiveContainer width="100%" height={280}>
            <PieChart>
              <Pie data={typeData} dataKey="value" nameKey="name" outerRadius={100} label={({ name, value }) => `${name} (${value})`} labelLine={false} fontSize={10}>
                {typeData.map((_, i) => (
                  <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </section>

        <section className="rounded-xl border border-slate-200 bg-white p-4 lg:col-span-2">
          <h2 className="mb-3 text-sm font-semibold">Project completion</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={progress ?? []} layout="vertical">
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 12 }} unit="%" />
              <YAxis type="category" dataKey="name" width={180} tick={{ fontSize: 12 }} />
              <Tooltip formatter={(v) => `${v}%`} />
              <Bar dataKey="percent_complete" name="Complete" radius={[0, 4, 4, 0]}>
                {(progress ?? []).map((p) => (
                  <Cell key={p.project_id} fill={p.color_hex} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </section>
      </div>
    </div>
  );
}
