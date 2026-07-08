import * as DropdownMenu from '@radix-ui/react-dropdown-menu';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { formatDistanceToNow } from 'date-fns';
import { Bell, LogOut } from 'lucide-react';
import { notificationsApi } from '../../api/endpoints';
import { useAuthStore } from '../../store/authStore';
import { cn } from '../../utils/cn';
import { Avatar } from '../shared/Avatar';

export function Topbar() {
  const { user, logout } = useAuthStore();
  const queryClient = useQueryClient();

  const { data: unread } = useQuery({
    queryKey: ['notifications', 'unread-count'],
    queryFn: notificationsApi.unreadCount,
    refetchInterval: 30_000,
  });
  const { data: notifications } = useQuery({
    queryKey: ['notifications', 'list'],
    queryFn: () => notificationsApi.list(),
  });

  const markAllRead = useMutation({
    mutationFn: notificationsApi.markAllRead,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['notifications'] }),
  });

  return (
    <header className="flex h-14 shrink-0 items-center justify-end gap-3 border-b border-slate-200 bg-white px-5">
      <DropdownMenu.Root>
        <DropdownMenu.Trigger asChild>
          <button
            className="relative rounded-lg p-2 text-slate-500 hover:bg-slate-100"
            aria-label="Notifications"
          >
            <Bell size={18} />
            {(unread?.count ?? 0) > 0 && (
              <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-500 px-1 text-[10px] font-bold text-white">
                {unread!.count}
              </span>
            )}
          </button>
        </DropdownMenu.Trigger>
        <DropdownMenu.Portal>
          <DropdownMenu.Content
            align="end"
            className="z-50 max-h-96 w-80 overflow-y-auto rounded-xl border border-slate-200 bg-white p-1 shadow-lg"
          >
            <div className="flex items-center justify-between px-3 py-2">
              <span className="text-sm font-semibold">Notifications</span>
              {(unread?.count ?? 0) > 0 && (
                <button
                  onClick={() => markAllRead.mutate()}
                  className="text-xs text-indigo-600 hover:underline"
                >
                  Mark all read
                </button>
              )}
            </div>
            {(notifications ?? []).length === 0 && (
              <p className="px-3 py-4 text-sm text-slate-500">Nothing yet.</p>
            )}
            {(notifications ?? []).map((n) => (
              <div
                key={n.id}
                className={cn(
                  'rounded-lg px-3 py-2 text-sm',
                  !n.is_read && 'bg-indigo-50/60 font-medium',
                )}
              >
                <p className="text-slate-800">{n.message}</p>
                <p className="mt-0.5 text-xs text-slate-400">
                  {formatDistanceToNow(new Date(n.created_at), { addSuffix: true })}
                </p>
              </div>
            ))}
          </DropdownMenu.Content>
        </DropdownMenu.Portal>
      </DropdownMenu.Root>

      {user && (
        <div className="flex items-center gap-2">
          <Avatar name={user.name} color={user.avatar_color} />
          <div className="leading-tight">
            <p className="text-sm font-medium">{user.name}</p>
            <p className="text-xs text-slate-400 capitalize">{user.role}</p>
          </div>
        </div>
      )}
      <button
        onClick={logout}
        className="rounded-lg p-2 text-slate-500 hover:bg-slate-100"
        aria-label="Log out"
        title="Log out"
      >
        <LogOut size={18} />
      </button>
    </header>
  );
}
