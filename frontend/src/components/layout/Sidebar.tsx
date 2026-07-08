import {
  BarChart3,
  CalendarOff,
  ClipboardList,
  FolderKanban,
  GanttChartSquare,
  Inbox,
  LayoutDashboard,
  Smartphone,
  Sparkles,
  Users,
} from 'lucide-react';
import { NavLink } from 'react-router-dom';
import { cn } from '../../utils/cn';

const NAV = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/tasks', label: 'Tasks', icon: ClipboardList },
  { to: '/gantt', label: 'Gantt', icon: GanttChartSquare },
  { to: '/planner', label: 'AI Planner', icon: Sparkles },
  { to: '/test-requests', label: 'Test Requests', icon: Inbox },
  { to: '/projects', label: 'Projects', icon: FolderKanban },
  { to: '/team', label: 'Team', icon: Users },
  { to: '/leaves', label: 'Leaves', icon: CalendarOff },
  { to: '/reports', label: 'Reports', icon: BarChart3 },
  { to: '/devices', label: 'Devices', icon: Smartphone },
];

export function Sidebar() {
  return (
    <aside className="flex w-56 shrink-0 flex-col border-r border-slate-200 bg-white">
      <div className="flex h-14 items-center gap-2 border-b border-slate-200 px-4">
        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-sm font-bold text-white">
          QA
        </span>
        <span className="font-semibold">Task Assigner</span>
      </div>
      <nav className="flex-1 space-y-0.5 overflow-y-auto p-2">
        {NAV.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            end={to === '/'}
            className={({ isActive }) =>
              cn(
                'flex items-center gap-2.5 rounded-lg px-3 py-2 text-sm font-medium text-slate-600 hover:bg-slate-100',
                isActive && 'bg-indigo-50 text-indigo-700 hover:bg-indigo-50',
              )
            }
          >
            <Icon size={17} />
            {label}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
