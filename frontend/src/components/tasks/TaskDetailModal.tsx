import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { format, formatDistanceToNow } from 'date-fns';
import { Paperclip, Send, Trash2 } from 'lucide-react';
import { useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../../api/client';
import { tasksApi } from '../../api/endpoints';
import { useAuthStore } from '../../store/authStore';
import type { Task } from '../../types';
import {
  PRIORITY_COLORS,
  PRIORITY_LABELS,
  STATUS_COLORS,
  STATUS_LABELS,
  TASK_TYPE_LABELS,
} from '../../utils/labels';
import { Avatar } from '../shared/Avatar';
import { Badge } from '../shared/Badge';
import { Modal } from '../shared/Modal';

export function TaskDetailModal({
  task,
  onClose,
  onEdit,
}: {
  task: Task | null;
  onClose: () => void;
  onEdit: (task: Task) => void;
}) {
  const queryClient = useQueryClient();
  const user = useAuthStore((s) => s.user);
  const [comment, setComment] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);

  const { data: comments } = useQuery({
    queryKey: ['tasks', task?.id, 'comments'],
    queryFn: () => tasksApi.comments(task!.id),
    enabled: !!task,
  });
  const { data: attachments } = useQuery({
    queryKey: ['tasks', task?.id, 'attachments'],
    queryFn: () => tasksApi.attachments(task!.id),
    enabled: !!task,
  });

  const addComment = useMutation({
    mutationFn: (content: string) => tasksApi.addComment(task!.id, content),
    onSuccess: () => {
      setComment('');
      queryClient.invalidateQueries({ queryKey: ['tasks', task?.id, 'comments'] });
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const upload = useMutation({
    mutationFn: (file: File) => tasksApi.uploadAttachment(task!.id, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['tasks', task?.id, 'attachments'] });
      toast.success('Attachment uploaded');
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  if (!task) return null;

  const meta: [string, React.ReactNode][] = [
    ['Type', TASK_TYPE_LABELS[task.task_type]],
    [
      'Status',
      <Badge key="s" className={STATUS_COLORS[task.status]}>
        {STATUS_LABELS[task.status]}
      </Badge>,
    ],
    [
      'Priority',
      <Badge key="p" className={PRIORITY_COLORS[task.priority]}>
        {PRIORITY_LABELS[task.priority]}
      </Badge>,
    ],
    ['Assignee', task.assignee?.name ?? 'Unassigned'],
    ['Device', task.device_model?.model_name ?? '—'],
    ['Automation', task.automation_type],
    ['Start', task.start_date ?? '—'],
    ['Due', task.due_date ?? '—'],
    ['Estimate', task.estimated_hours ? `${task.estimated_hours}h` : '—'],
    ['Actual', task.actual_hours ? `${task.actual_hours}h` : '—'],
    ['Build', task.build_version ?? '—'],
    ['Created', format(new Date(task.created_at), 'yyyy-MM-dd')],
  ];

  return (
    <Modal open={!!task} onClose={onClose} title={`#${task.id} · ${task.title}`} wide>
      <div className="space-y-4">
        <div className="flex justify-end">
          <button
            onClick={() => onEdit(task)}
            className="rounded-lg border border-slate-300 px-3 py-1 text-sm hover:bg-slate-50"
          >
            Edit
          </button>
        </div>
        {task.description && (
          <p className="rounded-lg bg-slate-50 p-3 text-sm whitespace-pre-wrap">
            {task.description}
          </p>
        )}
        <dl className="grid grid-cols-3 gap-x-4 gap-y-2 text-sm md:grid-cols-4">
          {meta.map(([label, value]) => (
            <div key={label}>
              <dt className="text-xs text-slate-400">{label}</dt>
              <dd className="mt-0.5">{value}</dd>
            </div>
          ))}
        </dl>

        {/* Attachments */}
        <section>
          <div className="mb-2 flex items-center justify-between">
            <h3 className="text-sm font-semibold">Attachments</h3>
            <button
              onClick={() => fileInput.current?.click()}
              className="flex items-center gap-1 text-xs text-indigo-600 hover:underline"
            >
              <Paperclip size={13} /> Upload
            </button>
            <input
              ref={fileInput}
              type="file"
              hidden
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) upload.mutate(f);
                e.target.value = '';
              }}
            />
          </div>
          <ul className="space-y-1 text-sm">
            {(attachments ?? []).map((a) => (
              <li key={a.id} className="flex items-center justify-between gap-2">
                <a
                  href={`/api/tasks/${task.id}/attachments/${a.id}/download`}
                  target="_blank"
                  rel="noreferrer"
                  className="truncate text-indigo-600 hover:underline"
                >
                  {a.original_filename}
                </a>
                <span className="text-xs text-slate-400">
                  {(a.file_size / 1024).toFixed(1)} KB
                </span>
              </li>
            ))}
            {(attachments ?? []).length === 0 && (
              <li className="text-xs text-slate-400">No attachments.</li>
            )}
          </ul>
        </section>

        {/* Comments */}
        <section>
          <h3 className="mb-2 text-sm font-semibold">Comments</h3>
          <div className="max-h-56 space-y-2 overflow-y-auto">
            {(comments ?? []).map((c) => (
              <div key={c.id} className="flex gap-2">
                <Avatar name={c.user?.name ?? '?'} color={c.user?.avatar_color} size="sm" />
                <div className="flex-1 rounded-lg bg-slate-50 px-3 py-2">
                  <div className="flex items-center justify-between">
                    <span className="text-xs font-medium">{c.user?.name}</span>
                    <span className="flex items-center gap-2 text-xs text-slate-400">
                      {formatDistanceToNow(new Date(c.created_at), { addSuffix: true })}
                      {(c.user_id === user?.id || user?.role === 'manager') && (
                        <button
                          onClick={() =>
                            tasksApi.deleteComment(task.id, c.id).then(() =>
                              queryClient.invalidateQueries({
                                queryKey: ['tasks', task.id, 'comments'],
                              }),
                            )
                          }
                          className="text-slate-300 hover:text-red-500"
                          aria-label="Delete comment"
                        >
                          <Trash2 size={12} />
                        </button>
                      )}
                    </span>
                  </div>
                  <p className="mt-0.5 text-sm whitespace-pre-wrap">{c.content}</p>
                </div>
              </div>
            ))}
            {(comments ?? []).length === 0 && (
              <p className="text-xs text-slate-400">No comments yet.</p>
            )}
          </div>
          <div className="mt-2 flex gap-2">
            <input
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && comment.trim() && addComment.mutate(comment)}
              placeholder="Add a comment…"
              className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none"
            />
            <button
              onClick={() => comment.trim() && addComment.mutate(comment)}
              disabled={!comment.trim() || addComment.isPending}
              className="rounded-lg bg-indigo-600 p-2 text-white hover:bg-indigo-700 disabled:opacity-40"
              aria-label="Send comment"
            >
              <Send size={14} />
            </button>
          </div>
        </section>
      </div>
    </Modal>
  );
}
