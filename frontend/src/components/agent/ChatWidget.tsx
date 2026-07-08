import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Bot, Send, Sparkles, X } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { agentApi } from '../../api/endpoints';
import { apiErrorMessage } from '../../api/client';
import type { ChatMessage } from '../../types';
import { cn } from '../../utils/cn';

export function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState<ChatMessage[]>([]);
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
        { role: 'assistant', content: data.reply, actions: data.actions },
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

  const send = () => {
    const content = input.trim();
    if (!content || chat.isPending) return;
    const next: ChatMessage[] = [...messages, { role: 'user', content }];
    setMessages(next);
    setInput('');
    chat.mutate(next);
  };

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
        <div className="fixed right-5 bottom-20 z-40 flex h-[520px] w-96 flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl">
          <div className="flex items-center gap-2 border-b border-slate-200 bg-indigo-600 px-4 py-3 text-white">
            <Bot size={18} />
            <div className="flex-1">
              <p className="text-sm font-semibold">AI Assistant</p>
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
                  “Who has the lightest workload?” · “Create a sanity task for HDR on the S25 Ultra
                  due Friday” · “Mark task 12 completed”
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
                    'max-w-[85%] rounded-2xl px-3 py-2 text-sm whitespace-pre-wrap',
                    m.role === 'user'
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-100 text-slate-800',
                  )}
                >
                  {m.content}
                  {m.actions && m.actions.length > 0 && (
                    <p className="mt-1.5 border-t border-slate-200 pt-1.5 text-xs text-slate-500">
                      ⚙️ {m.actions.map((a) => a.tool).join(', ')}
                    </p>
                  )}
                </div>
              </div>
            ))}
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
              onKeyDown={(e) => e.key === 'Enter' && send()}
              placeholder={status?.enabled ? 'Ask the assistant…' : 'Agent disabled'}
              disabled={!status?.enabled || chat.isPending}
              className="flex-1 rounded-lg border border-slate-300 px-3 py-1.5 text-sm focus:border-indigo-500 focus:outline-none disabled:bg-slate-50"
            />
            <button
              onClick={send}
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
