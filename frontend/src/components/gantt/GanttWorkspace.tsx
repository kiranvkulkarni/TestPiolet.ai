/**
 * The editable Gantt workspace (USP #1) — a custom timeline (ADR-0004).
 *
 * Interactions: drag to move (vertical drag reassigns), edge-drag to resize,
 * dependency drawing from the bar handle, double-click inline title edit,
 * right-click context menu, multi-select + bulk move, undo/redo, critical-path
 * highlight, workload heatmap, color-by, day/week/month zoom, virtualized rows.
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../../api/client';
import { tasksApi, usersApi } from '../../api/endpoints';
import type { GanttTask, TaskStatus } from '../../types';
import { cn } from '../../utils/cn';
import {
  BAR_HEIGHT,
  HEADER_HEIGHT,
  ROW_HEIGHT,
  buildHeaders,
  buildScale,
  barRect,
  dateToX,
  shiftIso,
  spanDays,
  type Zoom,
} from './timeline';
import { useUndoStack } from './useUndoStack';

export type ColorBy = 'status' | 'priority' | 'assignee';

const LABEL_WIDTH = 280;

const STATUS_FILL: Record<TaskStatus, string> = {
  pending: '#94a3b8',
  in_progress: '#3b82f6',
  blocked: '#ef4444',
  completed: '#22c55e',
  cancelled: '#d4d4d8',
};
const PRIORITY_FILL = {
  critical: '#dc2626',
  high: '#f97316',
  medium: '#eab308',
  low: '#94a3b8',
} as const;
const ASSIGNEE_FILL = ['#6366f1', '#0ea5e9', '#10b981', '#f59e0b', '#ec4899', '#8b5cf6', '#14b8a6', '#f43f5e'];
const HEAT_COLORS = ['transparent', '#bbf7d0', '#fde68a', '#fca5a5', '#f87171'];

type Row =
  | { kind: 'group'; key: string; assigneeId: number | null; name: string }
  | { kind: 'task'; key: string; task: GanttTask };

interface DragState {
  mode: 'move' | 'resize-end' | 'resize-start' | 'link';
  taskId: number;
  taskIds: number[]; // all tasks moving together (multi-select)
  startClientX: number;
  startClientY: number;
  dxDays: number;
  dyRows: number;
  moved: boolean;
  linkPos?: { x: number; y: number };
}

interface Props {
  projectId?: number;
  assigneeId?: number;
  zoom: Zoom;
  colorBy: ColorBy;
  showCritical: boolean;
  showHeatmap: boolean;
  undoStack: ReturnType<typeof useUndoStack>;
}

export function GanttWorkspace({
  projectId,
  assigneeId,
  zoom,
  colorBy,
  showCritical,
  showHeatmap,
  undoStack,
}: Props) {
  const queryClient = useQueryClient();
  const ganttKey = ['tasks', 'gantt', projectId, assigneeId];

  const { data: rowsData, isLoading } = useQuery({
    queryKey: ganttKey,
    queryFn: () => tasksApi.gantt({ project_id: projectId, assigned_to: assigneeId }),
  });
  const { data: users } = useQuery({ queryKey: ['users'], queryFn: usersApi.list });

  // ---- selection / edit state --------------------------------------------
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState('');
  const [menu, setMenu] = useState<{ x: number; y: number; task: GanttTask } | null>(null);
  const [linkSource, setLinkSource] = useState<number | null>(null); // context-menu "create dependency" mode
  const [drag, setDrag] = useState<DragState | null>(null);
  const [hoverTaskId, setHoverTaskId] = useState<number | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const [viewportH, setViewportH] = useState(600);
  const containerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<DragState | null>(null);

  const tasks = useMemo(() => rowsData ?? [], [rowsData]);
  const taskById = useMemo(() => new Map(tasks.map((t) => [t.id, t])), [tasks]);

  // ---- rows: tasks grouped by assignee ------------------------------------
  const rows: Row[] = useMemo(() => {
    const testers = (users ?? []).filter((u) => u.is_active && u.role !== 'viewer');
    const byAssignee = new Map<number | null, GanttTask[]>();
    for (const t of tasks) {
      const key = t.assigned_to ?? null;
      byAssignee.set(key, [...(byAssignee.get(key) ?? []), t]);
    }
    const out: Row[] = [];
    const seen = new Set<number | null>();
    const pushGroup = (id: number | null, name: string) => {
      out.push({ kind: 'group', key: `g${id ?? 'none'}`, assigneeId: id, name });
      const groupTasks = (byAssignee.get(id) ?? []).sort((a, b) =>
        a.start_date.localeCompare(b.start_date) || a.id - b.id,
      );
      for (const t of groupTasks) out.push({ kind: 'task', key: `t${t.id}`, task: t });
      seen.add(id);
    };
    for (const u of testers.sort((a, b) => a.name.localeCompare(b.name))) {
      if (assigneeId && u.id !== assigneeId) continue;
      pushGroup(u.id, u.name);
    }
    if (!assigneeId && (byAssignee.get(null)?.length ?? 0) > 0) pushGroup(null, 'Unassigned');
    // any assignees not in the testers list (e.g. managers with tasks)
    for (const [id, list] of byAssignee) {
      if (!seen.has(id) && list.length) pushGroup(id, list[0].assignee_name ?? `User ${id}`);
    }
    return out;
  }, [tasks, users, assigneeId]);

  const taskRowIndex = useMemo(() => {
    const map = new Map<number, number>();
    rows.forEach((r, i) => {
      if (r.kind === 'task') map.set(r.task.id, i);
    });
    return map;
  }, [rows]);

  // ---- time scale ----------------------------------------------------------
  const scale = useMemo(() => {
    if (tasks.length === 0) return null;
    let min = tasks[0].start_date;
    let max = tasks[0].due_date;
    for (const t of tasks) {
      if (t.start_date < min) min = t.start_date;
      if (t.due_date > max) max = t.due_date;
    }
    return buildScale(min, max, zoom);
  }, [tasks, zoom]);

  const headers = useMemo(() => (scale ? buildHeaders(scale, zoom) : null), [scale, zoom]);

  // ---- workload heatmap: per group, day-index -> overlapping active tasks --
  const heat = useMemo(() => {
    if (!showHeatmap || !scale) return null;
    const perGroup = new Map<number | null, Uint8Array>();
    for (const t of tasks) {
      if (t.status === 'completed' || t.status === 'cancelled') continue;
      const key = t.assigned_to ?? null;
      let arr = perGroup.get(key);
      if (!arr) perGroup.set(key, (arr = new Uint8Array(scale.days)));
      const from = Math.max(0, Math.round(dateToX(scale, t.start_date) / scale.pxPerDay));
      const to = Math.min(scale.days - 1, Math.round(dateToX(scale, t.due_date) / scale.pxPerDay));
      for (let d = from; d <= to; d++) arr[d] = Math.min(arr[d] + 1, 255);
    }
    return perGroup;
  }, [showHeatmap, scale, tasks]);

  // ---- mutations (optimistic; refetch reconciles; undo via snapshots) ------
  const invalidate = () => {
    queryClient.invalidateQueries({ queryKey: ['tasks'] });
    queryClient.invalidateQueries({ queryKey: ['dashboard'] });
  };

  const snapshotDates = useCallback(() => {
    const map = new Map<number, { start: string; due: string; assignee: number | null }>();
    for (const t of tasks) map.set(t.id, { start: t.start_date, due: t.due_date, assignee: t.assigned_to });
    return map;
  }, [tasks]);

  const restoreDates = useCallback(
    async (ids: number[], snapshot: Map<number, { start: string; due: string; assignee: number | null }>) => {
      for (const id of ids) {
        const prev = snapshot.get(id);
        if (prev) {
          await tasksApi.update(id, {
            start_date: prev.start,
            due_date: prev.due,
            assigned_to: prev.assignee,
          });
        }
      }
      invalidate();
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [],
  );

  const patchGanttCache = useCallback(
    (patch: Map<number, Partial<GanttTask>>) => {
      queryClient.setQueryData<GanttTask[]>(ganttKey, (old) =>
        old?.map((t) => (patch.has(t.id) ? { ...t, ...patch.get(t.id) } : t)),
      );
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, projectId, assigneeId],
  );

  /** Commit a move (+optional reassign) of one or more tasks; undo-able. */
  const commitMove = useCallback(
    async (ids: number[], dxDays: number, newAssignee: number | null | undefined) => {
      const snapshot = snapshotDates();
      // optimistic
      const patch = new Map<number, Partial<GanttTask>>();
      for (const id of ids) {
        const t = taskById.get(id);
        if (!t) continue;
        patch.set(id, {
          start_date: shiftIso(t.start_date, dxDays),
          due_date: shiftIso(t.due_date, dxDays),
          ...(newAssignee !== undefined && ids.length === 1
            ? { assigned_to: newAssignee, assignee_name: null }
            : {}),
        });
      }
      patchGanttCache(patch);
      try {
        const affectedIds = new Set<number>(ids);
        for (const id of ids) {
          const t = taskById.get(id);
          if (!t) continue;
          if (dxDays !== 0) {
            const result = await tasksApi.move(id, shiftIso(t.start_date, dxDays));
            result.affected.forEach((a) => affectedIds.add(a.id));
          }
          if (newAssignee !== undefined && ids.length === 1) {
            await tasksApi.update(id, { assigned_to: newAssignee });
          }
        }
        invalidate();
        const idList = [...affectedIds];
        undoStack.push({
          label: ids.length > 1 ? `Move ${ids.length} tasks` : 'Move task',
          undo: () => restoreDates(idList, snapshot),
          redo: async () => {
            await commitMove(ids, dxDays, newAssignee);
          },
        });
      } catch (error) {
        toast.error(apiErrorMessage(error));
        invalidate(); // rollback optimistic patch via refetch
      }
    },
    [snapshotDates, taskById, patchGanttCache, restoreDates, undoStack],
  );

  const commitResize = useCallback(
    async (taskId: number, edge: 'start' | 'end', dxDays: number) => {
      const t = taskById.get(taskId);
      if (!t || dxDays === 0) return;
      const snapshot = snapshotDates();
      const patch = new Map<number, Partial<GanttTask>>();
      let action: () => Promise<{ affected: { id: number }[] }>;
      if (edge === 'end') {
        const newDue = shiftIso(t.due_date, dxDays);
        if (newDue < t.start_date) return;
        patch.set(taskId, { due_date: newDue });
        action = () => tasksApi.resize(taskId, { due_date: newDue });
      } else {
        const newStart = shiftIso(t.start_date, dxDays);
        if (newStart > t.due_date) return;
        patch.set(taskId, { start_date: newStart });
        action = () => tasksApi.move(taskId, newStart, false);
      }
      patchGanttCache(patch);
      try {
        const result = await action();
        invalidate();
        const idList = [taskId, ...result.affected.map((a) => a.id)];
        undoStack.push({
          label: 'Resize task',
          undo: () => restoreDates(idList, snapshot),
          redo: async () => {
            await commitResize(taskId, edge, dxDays);
          },
        });
      } catch (error) {
        toast.error(apiErrorMessage(error));
        invalidate();
      }
    },
    [taskById, snapshotDates, patchGanttCache, restoreDates, undoStack],
  );

  const commitLink = useCallback(
    async (fromId: number, toId: number) => {
      if (fromId === toId) return;
      const snapshot = snapshotDates();
      try {
        const result = await tasksApi.addDependency(toId, fromId);
        invalidate();
        const depRef = { id: result.dependency!.id };
        const idList = result.affected.map((a) => a.id);
        undoStack.push({
          label: 'Link dependency',
          undo: async () => {
            await tasksApi.removeDependency(toId, depRef.id);
            await restoreDates(idList, snapshot);
          },
          redo: async () => {
            const again = await tasksApi.addDependency(toId, fromId);
            depRef.id = again.dependency!.id;
            invalidate();
          },
        });
        toast.success('Dependency created');
      } catch (error) {
        toast.error(apiErrorMessage(error)); // e.g. "would create a cycle"
      }
    },
    [snapshotDates, restoreDates, undoStack],
  );

  const commitUnlink = useCallback(
    async (task: GanttTask, edge: { id: number; from_task_id: number }) => {
      try {
        await tasksApi.removeDependency(task.id, edge.id);
        invalidate();
        undoStack.push({
          label: 'Unlink dependency',
          undo: async () => {
            await tasksApi.addDependency(task.id, edge.from_task_id);
            invalidate();
          },
          redo: async () => {
            const fresh = queryClient
              .getQueryData<GanttTask[]>(ganttKey)
              ?.find((t) => t.id === task.id)
              ?.dependency_edges.find((e) => e.from_task_id === edge.from_task_id);
            if (fresh) await tasksApi.removeDependency(task.id, fresh.id);
            invalidate();
          },
        });
      } catch (error) {
        toast.error(apiErrorMessage(error));
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [undoStack, queryClient],
  );

  const titleMutation = useMutation({
    mutationFn: ({ id, title }: { id: number; title: string }) => tasksApi.update(id, { title }),
    onSuccess: () => invalidate(),
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const commitTitle = useCallback(
    (task: GanttTask, title: string) => {
      const old = task.title;
      if (!title.trim() || title === old) return;
      patchGanttCache(new Map([[task.id, { title }]]));
      titleMutation.mutate({ id: task.id, title });
      undoStack.push({
        label: 'Rename task',
        undo: async () => {
          await tasksApi.update(task.id, { title: old });
          invalidate();
        },
        redo: async () => {
          await tasksApi.update(task.id, { title });
          invalidate();
        },
      });
    },
    [patchGanttCache, titleMutation, undoStack],
  );

  // ---- context-menu actions -------------------------------------------------
  const duplicateTask = useCallback(
    async (t: GanttTask) => {
      try {
        const full = await tasksApi.get(t.id);
        const created = await tasksApi.create({
          test_request_id: full.test_request_id,
          title: `${full.title} (copy)`,
          description: full.description,
          task_type: full.task_type,
          assigned_to: full.assigned_to,
          priority: full.priority,
          automation_type: full.automation_type,
          start_date: full.start_date,
          due_date: full.due_date,
          estimated_hours: full.estimated_hours,
          build_version: full.build_version,
          device_model_id: full.device_model_id,
        });
        invalidate();
        undoStack.push({
          label: 'Duplicate task',
          undo: async () => {
            await tasksApi.remove(created.id);
            invalidate();
          },
          redo: async () => {
            await duplicateTask(t);
          },
        });
        toast.success('Task duplicated');
      } catch (error) {
        toast.error(apiErrorMessage(error));
      }
    },
    [undoStack],
  );

  const splitTask = useCallback(
    async (t: GanttTask) => {
      const total = spanDays(t.start_date, t.due_date);
      if (total < 2) {
        toast.error('Task is too short to split');
        return;
      }
      const firstHalf = Math.ceil(total / 2);
      const oldDue = t.due_date;
      try {
        const full = await tasksApi.get(t.id);
        const resized = await tasksApi.resize(t.id, { duration_days: firstHalf });
        const created = await tasksApi.create({
          test_request_id: full.test_request_id,
          title: `${full.title} (part 2)`,
          task_type: full.task_type,
          assigned_to: full.assigned_to,
          priority: full.priority,
          start_date: shiftIso(resized.task.due_date!, 1),
          due_date: oldDue > resized.task.due_date! ? oldDue : shiftIso(resized.task.due_date!, 1),
          device_model_id: full.device_model_id,
        });
        await tasksApi.addDependency(created.id, t.id);
        invalidate();
        undoStack.push({
          label: 'Split task',
          undo: async () => {
            await tasksApi.remove(created.id);
            await tasksApi.update(t.id, { due_date: oldDue });
            invalidate();
          },
          redo: async () => {
            await splitTask(t);
          },
        });
        toast.success('Task split into two');
      } catch (error) {
        toast.error(apiErrorMessage(error));
      }
    },
    [undoStack],
  );

  const toMilestone = useCallback(
    async (t: GanttTask) => {
      const oldDue = t.due_date;
      try {
        await tasksApi.resize(t.id, { duration_days: 1 });
        invalidate();
        undoStack.push({
          label: 'Convert to milestone',
          undo: async () => {
            await tasksApi.update(t.id, { due_date: oldDue });
            invalidate();
          },
          redo: async () => {
            await tasksApi.resize(t.id, { duration_days: 1 });
            invalidate();
          },
        });
      } catch (error) {
        toast.error(apiErrorMessage(error));
      }
    },
    [undoStack],
  );

  // ---- drag handling ---------------------------------------------------------
  const beginDrag = useCallback(
    (e: React.PointerEvent, task: GanttTask, mode: DragState['mode']) => {
      e.preventDefault();
      e.stopPropagation();
      const ids = mode === 'move' && selected.has(task.id) ? [...selected] : [task.id];
      const state: DragState = {
        mode,
        taskId: task.id,
        taskIds: ids,
        startClientX: e.clientX,
        startClientY: e.clientY,
        dxDays: 0,
        dyRows: 0,
        moved: false,
      };
      dragRef.current = state;
      setDrag(state);
      (e.currentTarget as HTMLElement).setPointerCapture?.(e.pointerId);
    },
    [selected],
  );

  useEffect(() => {
    if (!drag) return;
    const onMove = (e: PointerEvent) => {
      const s = dragRef.current;
      if (!s || !scale) return;
      const dx = e.clientX - s.startClientX;
      const dy = e.clientY - s.startClientY;
      const next: DragState = {
        ...s,
        dxDays: Math.round(dx / scale.pxPerDay),
        dyRows: Math.round(dy / ROW_HEIGHT),
        moved: s.moved || Math.abs(dx) > 3 || Math.abs(dy) > 3,
        linkPos:
          s.mode === 'link' && containerRef.current
            ? {
                x:
                  e.clientX -
                  containerRef.current.getBoundingClientRect().left +
                  containerRef.current.scrollLeft -
                  LABEL_WIDTH,
                y:
                  e.clientY -
                  containerRef.current.getBoundingClientRect().top +
                  containerRef.current.scrollTop -
                  HEADER_HEIGHT,
              }
            : undefined,
      };
      dragRef.current = next;
      setDrag(next);
    };
    const onUp = (e: PointerEvent) => {
      const s = dragRef.current;
      dragRef.current = null;
      setDrag(null);
      if (!s || !s.moved) return;
      if (s.mode === 'move') {
        // vertical displacement onto another group = reassign (single task)
        let newAssignee: number | null | undefined;
        const rowIdx = taskRowIndex.get(s.taskId);
        if (rowIdx !== undefined && s.dyRows !== 0 && s.taskIds.length === 1) {
          const targetIdx = Math.min(Math.max(rowIdx + s.dyRows, 0), rows.length - 1);
          for (let i = targetIdx; i >= 0; i--) {
            const row = rows[i];
            if (row.kind === 'group') {
              const current = taskById.get(s.taskId)?.assigned_to ?? null;
              if (row.assigneeId !== current) newAssignee = row.assigneeId;
              break;
            }
          }
        }
        if (s.dxDays !== 0 || newAssignee !== undefined) {
          void commitMove(s.taskIds, s.dxDays, newAssignee);
        }
      } else if (s.mode === 'resize-end') {
        void commitResize(s.taskId, 'end', s.dxDays);
      } else if (s.mode === 'resize-start') {
        void commitResize(s.taskId, 'start', s.dxDays);
      } else if (s.mode === 'link') {
        // drop on a bar → create dependency source → target
        const el = document.elementFromPoint(e.clientX, e.clientY) as HTMLElement | null;
        const targetId = el?.closest('[data-task-id]')?.getAttribute('data-task-id');
        if (targetId) void commitLink(s.taskId, Number(targetId));
      }
    };
    window.addEventListener('pointermove', onMove);
    window.addEventListener('pointerup', onUp, { once: true });
    return () => {
      window.removeEventListener('pointermove', onMove);
      window.removeEventListener('pointerup', onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drag !== null, scale, rows, taskRowIndex]);

  // ---- keyboard ---------------------------------------------------------------
  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (editingId !== null) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        e.preventDefault();
        void undoStack.undo().then((label) => label && toast(`Undid: ${label}`, { icon: '↩️' }));
      } else if (
        ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'y') ||
        ((e.ctrlKey || e.metaKey) && e.shiftKey && e.key.toLowerCase() === 'z')
      ) {
        e.preventDefault();
        void undoStack.redo().then((label) => label && toast(`Redid: ${label}`, { icon: '↪️' }));
      } else if (e.key === 'Escape') {
        setSelected(new Set());
        setMenu(null);
        setLinkSource(null);
      } else if ((e.key === 'ArrowLeft' || e.key === 'ArrowRight') && selected.size > 0) {
        e.preventDefault();
        void commitMove([...selected], e.key === 'ArrowLeft' ? -1 : 1, undefined);
      }
    },
    [editingId, undoStack, selected, commitMove],
  );

  // ---- virtualization -----------------------------------------------------------
  const totalHeight = rows.length * ROW_HEIGHT;
  const overscan = 8;
  const firstRow = Math.max(0, Math.floor(scrollTop / ROW_HEIGHT) - overscan);
  const lastRow = Math.min(rows.length, Math.ceil((scrollTop + viewportH) / ROW_HEIGHT) + overscan);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setViewportH(el.clientHeight);
    measure();
    const obs = new ResizeObserver(measure);
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  const barFill = useCallback(
    (t: GanttTask): string => {
      if (colorBy === 'status') return STATUS_FILL[t.status];
      if (colorBy === 'priority') return PRIORITY_FILL[t.priority];
      return ASSIGNEE_FILL[(t.assigned_to ?? 0) % ASSIGNEE_FILL.length];
    },
    [colorBy],
  );

  if (isLoading) return <p className="p-6 text-sm text-slate-400">Loading plan…</p>;
  if (!scale || tasks.length === 0) {
    return (
      <div className="rounded-xl border border-slate-200 bg-white p-10 text-center text-sm text-slate-400">
        No scheduled tasks here yet — give tasks a start and due date, or clear the filters.
      </div>
    );
  }

  const visibleRows = rows.slice(firstRow, lastRow);

  // dependency arrows among (near-)visible tasks
  const arrows: { key: string; from: GanttTask; to: GanttTask; critical: boolean }[] = [];
  for (const row of visibleRows) {
    if (row.kind !== 'task') continue;
    for (const edge of row.task.dependency_edges) {
      const from = taskById.get(edge.from_task_id);
      if (from) {
        arrows.push({
          key: `${edge.id}`,
          from,
          to: row.task,
          critical: from.critical && row.task.critical,
        });
      }
    }
  }

  const dragFor = (id: number) =>
    drag && drag.mode !== 'link' && drag.taskIds.includes(id) ? drag : null;

  return (
    <div
      ref={containerRef}
      tabIndex={0}
      onKeyDown={onKeyDown}
      onScroll={(e) => setScrollTop((e.target as HTMLElement).scrollTop)}
      onClick={() => {
        setMenu(null);
      }}
      className="relative h-[calc(100vh-190px)] overflow-auto rounded-xl border border-slate-200 bg-white outline-none focus:ring-1 focus:ring-indigo-300"
    >
      <div style={{ width: LABEL_WIDTH + scale.width, height: HEADER_HEIGHT + totalHeight }}>
        {/* ---- time header (sticky top) ---- */}
        <div
          className="sticky top-0 z-30 border-b border-slate-200 bg-white"
          style={{ height: HEADER_HEIGHT, width: LABEL_WIDTH + scale.width }}
        >
          <div
            className="sticky left-0 z-40 float-left flex h-full items-center border-r border-slate-200 bg-white px-3 text-xs font-semibold text-slate-500"
            style={{ width: LABEL_WIDTH }}
          >
            Task
          </div>
          <div className="relative h-full" style={{ marginLeft: LABEL_WIDTH, width: scale.width }}>
            {headers!.top.map((c) => (
              <span
                key={`t${c.x}`}
                className="absolute top-1 truncate border-l border-slate-100 pl-1.5 text-[11px] font-semibold text-slate-600"
                style={{ left: c.x, width: c.width }}
              >
                {c.label}
              </span>
            ))}
            {headers!.bottom.map((c) => (
              <span
                key={`b${c.x}`}
                className={cn(
                  'absolute bottom-0 truncate border-l border-slate-100 pl-1 text-[10px] text-slate-400',
                  c.isWeekend && 'text-red-300',
                )}
                style={{ left: c.x, width: c.width }}
              >
                {c.label}
              </span>
            ))}
          </div>
        </div>

        {/* ---- body ---- */}
        <div className="relative" style={{ height: totalHeight }}>
          {/* weekend shading (day zoom) */}
          {zoom === 'day' && (
            <div
              className="pointer-events-none absolute top-0 h-full"
              style={{
                left: LABEL_WIDTH,
                width: scale.width,
                backgroundImage: `repeating-linear-gradient(to right, transparent, transparent ${
                  scale.pxPerDay * 5
                }px, rgba(148,163,184,0.08) ${scale.pxPerDay * 5}px, rgba(148,163,184,0.08) ${
                  scale.pxPerDay * 7
                }px)`,
                backgroundPositionX:
                  -(((scale.start.getDay() + 6) % 7) * scale.pxPerDay),
              }}
            />
          )}

          {/* dependency arrows */}
          <svg
            className="pointer-events-none absolute top-0 z-10"
            style={{ left: LABEL_WIDTH, width: scale.width, height: totalHeight }}
          >
            <defs>
              <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="6" markerHeight="6" orient="auto">
                <path d="M0,0 L8,4 L0,8 z" fill="currentColor" />
              </marker>
            </defs>
            {arrows.map(({ key, from, to, critical }) => {
              const fromIdx = taskRowIndex.get(from.id);
              const toIdx = taskRowIndex.get(to.id);
              if (fromIdx === undefined || toIdx === undefined) return null;
              const fd = dragFor(from.id);
              const td = dragFor(to.id);
              const fr = barRect(scale, from.start_date, from.due_date);
              const tr = barRect(scale, to.start_date, to.due_date);
              const x1 = fr.x + fr.width + (fd ? fd.dxDays * scale.pxPerDay : 0);
              const y1 = fromIdx * ROW_HEIGHT + ROW_HEIGHT / 2;
              const x2 = tr.x + (td ? td.dxDays * scale.pxPerDay : 0);
              const y2 = toIdx * ROW_HEIGHT + ROW_HEIGHT / 2;
              const mid = Math.max(x1 + 8, x2 - 8);
              const highlight = showCritical && critical;
              return (
                <path
                  key={key}
                  d={`M${x1},${y1} L${x1 + 6},${y1} L${x1 + 6},${(y1 + y2) / 2} L${mid - 6},${(y1 + y2) / 2} L${mid - 6},${y2} L${x2 - 2},${y2}`}
                  fill="none"
                  stroke={highlight ? '#dc2626' : '#94a3b8'}
                  strokeWidth={highlight ? 2 : 1.2}
                  markerEnd="url(#arrow)"
                  style={{ color: highlight ? '#dc2626' : '#94a3b8' }}
                />
              );
            })}
            {/* live dependency-drawing line */}
            {drag?.mode === 'link' && drag.linkPos && (() => {
              const from = taskById.get(drag.taskId);
              const fromIdx = from && taskRowIndex.get(from.id);
              if (!from || fromIdx === undefined) return null;
              const fr = barRect(scale, from.start_date, from.due_date);
              return (
                <line
                  x1={fr.x + fr.width}
                  y1={fromIdx * ROW_HEIGHT + ROW_HEIGHT / 2}
                  x2={drag.linkPos.x}
                  y2={drag.linkPos.y}
                  stroke="#6366f1"
                  strokeWidth={1.5}
                  strokeDasharray="4 3"
                />
              );
            })()}
          </svg>

          {/* virtualized rows */}
          {visibleRows.map((row, i) => {
            const idx = firstRow + i;
            const top = idx * ROW_HEIGHT;
            if (row.kind === 'group') {
              const heatArr = heat?.get(row.assigneeId);
              return (
                <div
                  key={row.key}
                  className="absolute flex border-b border-slate-100 bg-slate-50/90"
                  style={{ top, height: ROW_HEIGHT, width: LABEL_WIDTH + scale.width }}
                >
                  <div
                    className="sticky left-0 z-20 flex items-center gap-2 border-r border-slate-200 bg-slate-50 px-3 text-xs font-semibold text-slate-600"
                    style={{ width: LABEL_WIDTH, minWidth: LABEL_WIDTH }}
                  >
                    {row.name}
                  </div>
                  {heatArr && (
                    <div className="relative flex-1">
                      {heatSegments(heatArr).map((seg) => (
                        <div
                          key={seg.from}
                          className="absolute top-1 bottom-1 rounded-sm"
                          title={`${seg.count} overlapping active task(s)`}
                          style={{
                            left: seg.from * scale.pxPerDay,
                            width: (seg.to - seg.from + 1) * scale.pxPerDay,
                            background: HEAT_COLORS[Math.min(seg.count, HEAT_COLORS.length - 1)],
                            opacity: 0.75,
                          }}
                        />
                      ))}
                    </div>
                  )}
                </div>
              );
            }

            const t = row.task;
            const rect = barRect(scale, t.start_date, t.due_date);
            const d = dragFor(t.id);
            const dx = d ? d.dxDays * scale.pxPerDay : 0;
            const dy = d && d.taskIds.length === 1 ? d.dyRows * ROW_HEIGHT : 0;
            const isSelected = selected.has(t.id);
            const dimmed = showCritical && !t.critical;
            const isMilestone = t.start_date === t.due_date;
            const linkTarget =
              (drag?.mode === 'link' && drag.taskId !== t.id && hoverTaskId === t.id) ||
              (linkSource !== null && linkSource !== t.id && hoverTaskId === t.id);

            return (
              <div
                key={row.key}
                className="group absolute border-b border-slate-50"
                style={{ top, height: ROW_HEIGHT, width: LABEL_WIDTH + scale.width }}
                onPointerEnter={() => setHoverTaskId(t.id)}
                onPointerLeave={() => setHoverTaskId((h) => (h === t.id ? null : h))}
              >
                {/* label cell */}
                <div
                  className={cn(
                    'sticky left-0 z-20 flex h-full items-center gap-1 border-r border-slate-200 bg-white pr-2 pl-6 text-xs',
                    isSelected && 'bg-indigo-50',
                  )}
                  style={{ width: LABEL_WIDTH, minWidth: LABEL_WIDTH, float: 'left' }}
                  onDoubleClick={() => {
                    setEditingId(t.id);
                    setEditValue(t.title);
                  }}
                >
                  {editingId === t.id ? (
                    <input
                      autoFocus
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={() => setEditingId(null)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter') {
                          commitTitle(t, editValue);
                          setEditingId(null);
                        } else if (e.key === 'Escape') {
                          setEditingId(null);
                        }
                        e.stopPropagation();
                      }}
                      className="w-full rounded border border-indigo-400 px-1 py-0.5 text-xs focus:outline-none"
                    />
                  ) : (
                    <>
                      <span
                        className={cn(
                          'truncate',
                          t.status === 'completed' && 'text-slate-400 line-through',
                          showCritical && t.critical && 'font-semibold text-red-700',
                        )}
                        title={`#${t.id} · ${t.title} (double-click to rename)`}
                      >
                        {t.title}
                      </span>
                      {t.critical && showCritical && <span className="text-[9px] text-red-500">●</span>}
                    </>
                  )}
                </div>

                {/* bar */}
                <div className="relative h-full" style={{ marginLeft: LABEL_WIDTH }}>
                  <div
                    data-task-id={t.id}
                    onPointerDown={(e) => {
                      if (e.button !== 0) return;
                      if (linkSource !== null) return; // click-to-link handled onClick
                      beginDrag(e, t, 'move');
                    }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setMenu(null);
                      if (linkSource !== null && linkSource !== t.id) {
                        void commitLink(linkSource, t.id);
                        setLinkSource(null);
                        return;
                      }
                      setSelected((prev) => {
                        const next = new Set(e.ctrlKey || e.metaKey ? prev : []);
                        if (prev.has(t.id) && (e.ctrlKey || e.metaKey)) next.delete(t.id);
                        else next.add(t.id);
                        return next;
                      });
                    }}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      e.stopPropagation();
                      setMenu({ x: e.clientX, y: e.clientY, task: t });
                    }}
                    className={cn(
                      'absolute flex cursor-grab items-center rounded-md px-1.5 text-[10px] font-medium text-white select-none active:cursor-grabbing',
                      isSelected && 'ring-2 ring-indigo-500 ring-offset-1',
                      linkTarget && 'ring-2 ring-emerald-500',
                      showCritical && t.critical && 'shadow-[0_0_0_2px_#dc2626]',
                      isMilestone && 'rotate-45 rounded-sm',
                    )}
                    style={{
                      left: rect.x,
                      width: isMilestone ? BAR_HEIGHT : rect.width,
                      height: BAR_HEIGHT,
                      top: (ROW_HEIGHT - BAR_HEIGHT) / 2,
                      background: barFill(t),
                      opacity: dimmed ? 0.35 : 1,
                      transform: d ? `translate(${dx}px, ${dy}px)` : undefined,
                      zIndex: d ? 15 : undefined,
                    }}
                  >
                    {!isMilestone && (
                      <span className="pointer-events-none truncate">{t.title}</span>
                    )}
                    {/* resize handles */}
                    {!isMilestone && (
                      <>
                        <span
                          onPointerDown={(e) => beginDrag(e, t, 'resize-start')}
                          className="absolute top-0 left-0 h-full w-1.5 cursor-ew-resize rounded-l-md opacity-0 group-hover:opacity-100 hover:bg-black/25"
                        />
                        <span
                          onPointerDown={(e) => beginDrag(e, t, 'resize-end')}
                          className="absolute top-0 right-0 h-full w-1.5 cursor-ew-resize rounded-r-md opacity-0 group-hover:opacity-100 hover:bg-black/25"
                        />
                      </>
                    )}
                    {/* dependency handle */}
                    <span
                      onPointerDown={(e) => beginDrag(e, t, 'link')}
                      title="Drag to another task to create a dependency"
                      className="absolute top-1/2 -right-2.5 h-3 w-3 -translate-y-1/2 cursor-crosshair rounded-full border-2 border-indigo-500 bg-white opacity-0 group-hover:opacity-100"
                    />
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>

      {/* ---- context menu ---- */}
      {menu && (
        <div
          className="fixed z-50 w-56 rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-xl"
          style={{ left: menu.x, top: menu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <MenuItem
            label="Rename"
            onClick={() => {
              setEditingId(menu.task.id);
              setEditValue(menu.task.title);
              setMenu(null);
            }}
          />
          <MenuItem
            label="Duplicate"
            onClick={() => {
              void duplicateTask(menu.task);
              setMenu(null);
            }}
          />
          <MenuItem
            label="Split"
            onClick={() => {
              void splitTask(menu.task);
              setMenu(null);
            }}
          />
          <MenuItem
            label="Convert to milestone"
            onClick={() => {
              void toMilestone(menu.task);
              setMenu(null);
            }}
          />
          <MenuItem
            label="Create dependency → click a task"
            onClick={() => {
              setLinkSource(menu.task.id);
              setMenu(null);
              toast('Click the task that must wait for this one', { icon: '🔗' });
            }}
          />
          {menu.task.dependency_edges.length > 0 && (
            <>
              <div className="my-1 border-t border-slate-100" />
              {menu.task.dependency_edges.map((edge) => (
                <MenuItem
                  key={edge.id}
                  label={`Unlink from “${taskById.get(edge.from_task_id)?.title ?? edge.from_task_id}”`}
                  onClick={() => {
                    void commitUnlink(menu.task, edge);
                    setMenu(null);
                  }}
                />
              ))}
            </>
          )}
        </div>
      )}
    </div>
  );
}

function MenuItem({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className="block w-full truncate px-3 py-1.5 text-left hover:bg-indigo-50"
    >
      {label}
    </button>
  );
}

function heatSegments(arr: Uint8Array): { from: number; to: number; count: number }[] {
  const segments: { from: number; to: number; count: number }[] = [];
  let i = 0;
  while (i < arr.length) {
    if (arr[i] === 0) {
      i++;
      continue;
    }
    const count = arr[i];
    let j = i;
    while (j + 1 < arr.length && arr[j + 1] === count) j++;
    segments.push({ from: i, to: j, count });
    i = j + 1;
  }
  return segments;
}
