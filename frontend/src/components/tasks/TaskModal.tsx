import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../../api/client';
import {
  deviceModelsApi,
  tasksApi,
  testRequestsApi,
  usersApi,
} from '../../api/endpoints';
import type { Task } from '../../types';
import {
  ALL_PRIORITIES,
  ALL_STATUSES,
  ALL_TASK_TYPES,
  PRIORITY_LABELS,
  STATUS_LABELS,
  TASK_TYPE_LABELS,
} from '../../utils/labels';
import { Field, inputClass } from '../shared/Field';
import { Modal } from '../shared/Modal';

interface TaskModalProps {
  open: boolean;
  onClose: () => void;
  task?: Task | null; // null/undefined = create
  defaultTestRequestId?: number;
}

export function TaskModal({ open, onClose, task, defaultTestRequestId }: TaskModalProps) {
  const queryClient = useQueryClient();
  const [form, setForm] = useState<Partial<Task>>({});

  useEffect(() => {
    if (!open) return;
    setForm(
      task ?? {
        title: '',
        task_type: 'functional_sanity',
        status: 'pending',
        priority: 'medium',
        automation_type: 'manual',
        test_request_id: defaultTestRequestId,
      },
    );
  }, [open, task, defaultTestRequestId]);

  const { data: requests } = useQuery({
    queryKey: ['test-requests'],
    queryFn: () => testRequestsApi.list(),
    enabled: open,
  });
  const { data: users } = useQuery({ queryKey: ['users'], queryFn: usersApi.list, enabled: open });
  const { data: devices } = useQuery({
    queryKey: ['device-models'],
    queryFn: () => deviceModelsApi.list(true),
    enabled: open,
  });

  const save = useMutation({
    mutationFn: (data: Partial<Task>) =>
      task ? tasksApi.update(task.id, data) : tasksApi.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks'] });
      queryClient.invalidateQueries({ queryKey: ['dashboard'] });
      queryClient.invalidateQueries({ queryKey: ['test-requests'] });
      toast.success(task ? 'Task updated' : 'Task created');
      onClose();
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const set = (key: keyof Task, value: unknown) => setForm((f) => ({ ...f, [key]: value }));
  const numOrNull = (v: string) => (v === '' ? null : Number(v));

  return (
    <Modal open={open} onClose={onClose} title={task ? `Edit task #${task.id}` : 'New task'} wide>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          if (!form.title || !form.test_request_id) {
            toast.error('Title and test request are required');
            return;
          }
          save.mutate(form);
        }}
        className="grid grid-cols-2 gap-3"
      >
        <div className="col-span-2">
          <Field label="Title">
            <input
              className={inputClass}
              value={form.title ?? ''}
              onChange={(e) => set('title', e.target.value)}
              autoFocus
            />
          </Field>
        </div>
        <Field label="Test request">
          <select
            className={inputClass}
            value={form.test_request_id ?? ''}
            onChange={(e) => set('test_request_id', Number(e.target.value))}
          >
            <option value="">Select…</option>
            {(requests ?? []).map((r) => (
              <option key={r.id} value={r.id}>
                #{r.id} · {r.title}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Task type">
          <select
            className={inputClass}
            value={form.task_type ?? 'functional_sanity'}
            onChange={(e) => set('task_type', e.target.value)}
          >
            {ALL_TASK_TYPES.map((t) => (
              <option key={t} value={t}>
                {TASK_TYPE_LABELS[t]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Assignee">
          <select
            className={inputClass}
            value={form.assigned_to ?? ''}
            onChange={(e) => set('assigned_to', e.target.value ? Number(e.target.value) : null)}
          >
            <option value="">Unassigned</option>
            {(users ?? [])
              .filter((u) => u.is_active && u.role !== 'viewer')
              .map((u) => (
                <option key={u.id} value={u.id}>
                  {u.name}
                </option>
              ))}
          </select>
        </Field>
        <Field label="Device">
          <select
            className={inputClass}
            value={form.device_model_id ?? ''}
            onChange={(e) =>
              set('device_model_id', e.target.value ? Number(e.target.value) : null)
            }
          >
            <option value="">None</option>
            {(devices ?? []).map((d) => (
              <option key={d.id} value={d.id}>
                {d.model_name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Status">
          <select
            className={inputClass}
            value={form.status ?? 'pending'}
            onChange={(e) => set('status', e.target.value)}
          >
            {ALL_STATUSES.map((s) => (
              <option key={s} value={s}>
                {STATUS_LABELS[s]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Priority">
          <select
            className={inputClass}
            value={form.priority ?? 'medium'}
            onChange={(e) => set('priority', e.target.value)}
          >
            {ALL_PRIORITIES.map((p) => (
              <option key={p} value={p}>
                {PRIORITY_LABELS[p]}
              </option>
            ))}
          </select>
        </Field>
        <Field label="Start date">
          <input
            type="date"
            className={inputClass}
            value={form.start_date ?? ''}
            onChange={(e) => set('start_date', e.target.value || null)}
          />
        </Field>
        <Field label="Due date">
          <input
            type="date"
            className={inputClass}
            value={form.due_date ?? ''}
            onChange={(e) => set('due_date', e.target.value || null)}
          />
        </Field>
        <Field label="Estimated hours">
          <input
            type="number"
            step="0.5"
            min="0"
            className={inputClass}
            value={form.estimated_hours ?? ''}
            onChange={(e) => set('estimated_hours', numOrNull(e.target.value))}
          />
        </Field>
        <Field label="Build version">
          <input
            className={inputClass}
            value={form.build_version ?? ''}
            onChange={(e) => set('build_version', e.target.value || null)}
          />
        </Field>
        <div className="col-span-2">
          <Field label="Description">
            <textarea
              className={inputClass}
              rows={3}
              value={form.description ?? ''}
              onChange={(e) => set('description', e.target.value || null)}
            />
          </Field>
        </div>
        <div className="col-span-2 mt-1 flex justify-end gap-2">
          <button
            type="button"
            onClick={onClose}
            className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={save.isPending}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {save.isPending ? 'Saving…' : task ? 'Save changes' : 'Create task'}
          </button>
        </div>
      </form>
    </Modal>
  );
}
