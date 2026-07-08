import { useQuery } from '@tanstack/react-query';
import { Flame, Redo2, Route, Undo2 } from 'lucide-react';
import { useState } from 'react';
import toast from 'react-hot-toast';
import { projectsApi, usersApi } from '../api/endpoints';
import { GanttWorkspace, type ColorBy } from '../components/gantt/GanttWorkspace';
import type { Zoom } from '../components/gantt/timeline';
import { useUndoStack } from '../components/gantt/useUndoStack';
import { inputClass } from '../components/shared/Field';
import { cn } from '../utils/cn';

export function GanttView() {
  const [projectId, setProjectId] = useState<number | undefined>();
  const [assigneeId, setAssigneeId] = useState<number | undefined>();
  const [zoom, setZoom] = useState<Zoom>('day');
  const [colorBy, setColorBy] = useState<ColorBy>('status');
  const [showCritical, setShowCritical] = useState(false);
  const [showHeatmap, setShowHeatmap] = useState(false);
  const undoStack = useUndoStack();

  const { data: projects } = useQuery({ queryKey: ['projects'], queryFn: projectsApi.list });
  const { data: users } = useQuery({ queryKey: ['users'], queryFn: usersApi.list });

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <h1 className="mr-auto text-xl font-semibold">Gantt workspace</h1>
        <button
          onClick={() => void undoStack.undo().then((l) => l && toast(`Undid: ${l}`, { icon: '↩️' }))}
          disabled={!undoStack.canUndo}
          title="Undo (Ctrl+Z)"
          aria-label="Undo"
          className="rounded-lg border border-slate-300 p-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-30"
        >
          <Undo2 size={15} />
        </button>
        <button
          onClick={() => void undoStack.redo().then((l) => l && toast(`Redid: ${l}`, { icon: '↪️' }))}
          disabled={!undoStack.canRedo}
          title="Redo (Ctrl+Y)"
          aria-label="Redo"
          className="rounded-lg border border-slate-300 p-1.5 text-slate-600 hover:bg-slate-50 disabled:opacity-30"
        >
          <Redo2 size={15} />
        </button>

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
          <option value="">Everyone</option>
          {(users ?? []).filter((u) => u.role !== 'viewer').map((u) => (
            <option key={u.id} value={u.id}>{u.name}</option>
          ))}
        </select>
        <select
          className={cn(inputClass, 'w-36')}
          value={colorBy}
          onChange={(e) => setColorBy(e.target.value as ColorBy)}
          title="Color bars by"
        >
          <option value="status">Color: status</option>
          <option value="priority">Color: priority</option>
          <option value="assignee">Color: assignee</option>
        </select>
        <div className="flex rounded-lg border border-slate-300 p-0.5">
          {(['day', 'week', 'month'] as const).map((z) => (
            <button
              key={z}
              onClick={() => setZoom(z)}
              className={cn(
                'rounded-md px-2.5 py-1 text-sm capitalize',
                zoom === z ? 'bg-indigo-600 text-white' : 'text-slate-600 hover:bg-slate-100',
              )}
            >
              {z}
            </button>
          ))}
        </div>
        <button
          onClick={() => setShowCritical((v) => !v)}
          className={cn(
            'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm',
            showCritical
              ? 'border-red-300 bg-red-50 text-red-700'
              : 'border-slate-300 text-slate-600 hover:bg-slate-50',
          )}
          title="Highlight the critical path"
        >
          <Route size={14} /> Critical path
        </button>
        <button
          onClick={() => setShowHeatmap((v) => !v)}
          className={cn(
            'flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-sm',
            showHeatmap
              ? 'border-amber-300 bg-amber-50 text-amber-700'
              : 'border-slate-300 text-slate-600 hover:bg-slate-50',
          )}
          title="Show workload heatmap per person"
        >
          <Flame size={14} /> Heatmap
        </button>
      </div>

      <GanttWorkspace
        projectId={projectId}
        assigneeId={assigneeId}
        zoom={zoom}
        colorBy={colorBy}
        showCritical={showCritical}
        showHeatmap={showHeatmap}
        undoStack={undoStack}
      />

      <p className="text-xs text-slate-400">
        Drag a bar to move (drop on another person to reassign) · drag edges to resize · drag the
        ○ handle onto a task to link · double-click a title to rename · right-click for more ·
        Ctrl+click multi-select, ←/→ nudges selection · Ctrl+Z / Ctrl+Y undo/redo.
      </p>
    </div>
  );
}
