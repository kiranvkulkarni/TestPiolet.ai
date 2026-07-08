import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, Check, ExternalLink, Send, Sparkles, Undo2, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { Link } from 'react-router-dom';
import { apiErrorMessage } from '../../api/client';
import { agentApi, tasksApi } from '../../api/endpoints';
import type { AgentAction, AgentUndo, ChatMessage } from '../../types';
import { cn } from '../../utils/cn';

/** Task ids an action touched (for the "view in Gantt" affordance). */
function affectedTaskIds(action: AgentAction): number[] {
  const ids = new Set<number>();
  const r = action.result as Record<string, unknown>;
  for (const key of ['created', 'updated']) {
    const v = r[key] as { id?: number } | undefined;
    if (v?.id) ids.add(v.id);
  }
  for (const key of ['created', 'rescheduled', 'pushed_dependents', 'assigned']) {
    const list = r[key];
    if (Array.isArray(list)) list.forEach((t: { id?: number }) => t?.id && ids.add(t.id));
  }
  return [...ids];
}

async function executeUndo(undo: AgentUndo): Promise<void> {
  switch (undo.kind) {
    case 'update_tasks':
      for (const t of undo.tasks) await tasksApi.update(t.id, t.fields);
      break;
    case 'delete_tasks':
      for (const id of undo.ids) await tasksApi.remove(id);
      break;
    case 'add_dependency':
      await tasksApi.addDependency(undo.to_task_id, undo.from_task_id);
      break;
    case 'remove_dependency':
      await tasksApi.removeDependency(undo.task_id, undo.dep_id);
      break;
  }
}

function ActionCard({
  action,
  undone,
  onUndone,
}: {
  action: AgentAction;
  undone: boolean;
  onUndone: () => void;
}) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState(false);
  const { rationale, confidence, undo } = action.result;
  const taskIds = affectedTaskIds(action);
  const pct = typeof confidence === 'number' ? Math.round(confidence * 100) : null;

  return (
    <div className="mt-1.5 rounded-lg border border-indigo-100 bg-indigo-50/60 p-2 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="font-semibold text-indigo-700">⚙️ {action.tool}</span>
        {pct !== null && (
          <span
            className={cn(
              'rounded-full px-1.5 py-0.5 font-medium',
              pct >= 85 ? 'bg-green-100 text-green-700'
                : pct >= 70 ? 'bg-amber-100 text-amber-700'
                : 'bg-red-100 text-red-700',
            )}
            title="The assistant's confidence in this action"
          >
            {pct}%
          </span>
        )}
      </div>
      {rationale && <p className="mt-1 text-slate-600">{rationale}</p>}
      <div className="mt-1.5 flex items-center gap-3">
        {taskIds.length > 0 && (
          <Link
            to="/gantt"
            className="flex items-center gap-1 text-indigo-600 hover:underline"
            title={`Tasks: ${taskIds.join(', ')}`}
          >
            <ExternalLink size={11} /> View in Gantt ({taskIds.length} task
            {taskIds.length > 1 ? 's' : ''})
          </Link>
        )}
        {undo && !undone && (
          <button
            disabled={busy}
            onClick={async () => {
              setBusy(true);
              try {
                await executeUndo(undo);
                queryClient.invalidateQueries({ queryKey: ['tasks'] });
                queryClient.invalidateQueries({ queryKey: ['dashboard'] });
                onUndone();
                toast.success('AI action undone');
              } catch (error) {
                toast.error(apiErrorMessage(error));
              } finally {
                setBusy(false);
              }
            }}
            className="flex items-center gap-1 text-slate-500 hover:text-red-600 disabled:opacity-50"
          >
            <Undo2 size={11} /> {busy ? 'Undoing…' : 'Undo'}
          </button>
        )}
        {undone && <span className="text-slate-400">↩︎ undone</span>}
      </div>
    </div>
  );
}

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [undoneActions, setUndoneActions] = useState<Set<string>>(new Set());
  const bottomRef = useRef<HTMLDivElement>(null);
  const queryClient = useQueryClient();

  const { data: status } = useQuery({
    queryKey: ['agent', 'status'],
    queryFn: agentApi.status,
    staleTime: 5 * 60_000,
  });

  const chat = useMutation({
    mutationFn: (msgs: ChatMessage[]) =>
      agentApi.chat(msgs.map(({ role, content }) => ({ role, content }))),
    onSuccess: (data) => {
      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: data.reply,
          actions: data.actions,
          explanation: data.explanation,
          pendingConfirmation: data.pending_confirmation,
        },
      ]);
      if (data.actions.length > 0) {
        // the agent mutated tasks — refresh everything task-shaped
        queryClient.invalidateQueries({ queryKey: ['tasks'] });
        queryClient.invalidateQueries({ queryKey: ['dashboard'] });
        queryClient.invalidateQueries({ queryKey: ['notifications'] });
      }
    },
    onError: (error) => {
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: `⚠️ ${apiErrorMessage(error)}` },
      ]);
    },
  });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, chat.isPending]);

  const sendText = (content: string) => {
    if (!content.trim() || chat.isPending) return;
    const next: ChatMessage[] = [...messages, { role: 'user', content: content.trim() }];
    setMessages(next);
    setInput('');
    chat.mutate(next);
  };

  const lastMessage = messages[messages.length - 1];
  const awaitingConfirmation =
    lastMessage?.role === 'assistant' && lastMessage.pendingConfirmation && !chat.isPending;

  return (
    <>
      <button
        onClick={() => setOpen((o) => !o)}
        className="fixed right-5 bottom-5 z-40 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-600 text-white shadow-lg hover:bg-indigo-700"
        aria-label="AI assistant"
      >
        {open ? <X size={20} /> : <Sparkles size={20} />}
      </button>

      {open && (
        <div className="fixed right-5 bottom-20 z-40 flex h-[560px] w-[26rem] flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
          <div className="flex items-center gap-2 border-b border-slate-200 bg-indigo-600 px-4 py-3 text-white">
            <Bot size={18} />
            <div className="flex-1">
              <p className="text-sm font-semibold">AI Operations Assistant</p>
              <p className="text-xs text-indigo-200">
                {status?.enabled
                  ? status.llm_reachable
                    ? `On-prem LLM · ${status.model}`
                    : 'LLM unreachable'
                  : 'Agent disabled'}
              </p>
            </div>
          </div>

          <div className="flex-1 space-y-3 overflow-y-auto p-3">
            {messages.length === 0 && (
              <div className="mt-6 px-2 text-center text-sm text-slate-500">
                <p className="font-medium text-slate-700">Ask me to operate the schedule.</p>
                <p className="mt-2">
                  “Rebalance next week's sanity tasks off Priya” · “What's the critical path of
                  Camera v16?” · “Who has capacity for 16 more hours?”
                </p>
                {!status?.enabled && (
                  <p className="mt-3 rounded-lg bg-amber-50 p-2 text-xs text-amber-700">
                    The agent is disabled. Set AGENT_ENABLED=true in backend/.env and run a local
                    LLM (e.g. Ollama).
                  </p>
                )}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={cn('flex', m.role === 'user' && 'justify-end')}>
                <div
                  className={cn(
                    'max-w-[90%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap',
                    m.role === 'user' ? 'bg-indigo-600 text-white' : 'bg-slate-100 text-slate-800',
                  )}
                >
                  {m.content}
                  {m.actions?.map((action, j) => (
                    <ActionCard
                      key={j}
                      action={action}
                      undone={undoneActions.has(`${i}:${j}`)}
                      onUndone={() =>
                        setUndoneActions((prev) => new Set(prev).add(`${i}:${j}`))
                      }
                    />
                  ))}
                </div>
              </div>
            ))}
            {awaitingConfirmation && (
              <div className="flex gap-2 pl-1">
                <button
                  onClick={() => sendText('Yes, go ahead — confirmed.')}
                  className="flex items-center gap-1 rounded-lg bg-green-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-green-700"
                >
                  <Check size={13} /> Yes, do it
                </button>
                <button
                  onClick={() => sendText('No, cancel that.')}
                  className="flex items-center gap-1 rounded-lg border border-slate-300 px-3 py-1.5 text-xs text-slate-600 hover:bg-slate-50"
                >
                  <X size={13} /> Cancel
                </button>
              </div>
            )}
            {chat.isPending && (
              <div className="flex">
                <div className="rounded-2xl bg-slate-100 px-3 py-2 text-sm text-slate-400">
                  Thinking…
                </div>
              </div>
            )}
            <div ref={bottomRef} />
          </div>

          <div className="flex items-center gap-2 border-t border-slate-200 p-3">
            <input
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && sendText(input)}
              placeholder={status?.enabled ? 'Ask the assistant…' : 'Agent disabled'}
              disabled={!status?.enabled || chat.isPending}
              className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
            />
            <button
              onClick={() => sendText(input)}
              disabled={!status?.enabled || chat.isPending || !input.trim()}
              className="rounded-lg bg-indigo-600 p-2 text-white hover:bg-indigo-700 disabled:opacity-40"
              aria-label="Send"
            >
              <Send size={16} />
            </button>
          </div>
        </div>
      )}
    </>
  );
}
