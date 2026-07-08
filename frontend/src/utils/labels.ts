import type { Priority, TaskStatus, TaskType } from '../types';

export const TASK_TYPE_LABELS: Record<TaskType, string> = {
  functional_sanity: 'Sanity',
  functional_full_sanity: 'Full Sanity',
  functional_feature_verification: 'Feature Verification',
  functional_menu_tree: 'Menu Tree',
  issue_reproduction: 'Issue Reproduction',
  fix_verification: 'Fix Verification',
  side_effect_verification: 'Side-effect Verification',
  nonfunc_kpi_launch_time: 'KPI · Launch Time',
  nonfunc_fps: 'KPI · FPS',
  nonfunc_memory_profiling: 'Memory Profiling',
  nonfunc_memory_leak: 'Memory Leak',
  nonfunc_power_consumption: 'Power Consumption',
  compliance_google_its: 'Google ITS',
  compliance_google_cts: 'Google CTS',
  compliance_sensor_fusion: 'Sensor Fusion',
};

export const STATUS_LABELS: Record<TaskStatus, string> = {
  pending: 'Pending',
  in_progress: 'In Progress',
  blocked: 'Blocked',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

export const STATUS_COLORS: Record<TaskStatus, string> = {
  pending: 'bg-slate-100 text-slate-700',
  in_progress: 'bg-blue-100 text-blue-700',
  blocked: 'bg-red-100 text-red-700',
  completed: 'bg-green-100 text-green-700',
  cancelled: 'bg-zinc-100 text-zinc-500 line-through',
};

export const PRIORITY_LABELS: Record<Priority, string> = {
  critical: 'Critical',
  high: 'High',
  medium: 'Medium',
  low: 'Low',
};

export const PRIORITY_COLORS: Record<Priority, string> = {
  critical: 'bg-red-100 text-red-700',
  high: 'bg-orange-100 text-orange-700',
  medium: 'bg-yellow-100 text-yellow-700',
  low: 'bg-slate-100 text-slate-600',
};

export const ALL_STATUSES: TaskStatus[] = [
  'pending',
  'in_progress',
  'blocked',
  'completed',
  'cancelled',
];

export const ALL_PRIORITIES: Priority[] = ['critical', 'high', 'medium', 'low'];

export const ALL_TASK_TYPES = Object.keys(TASK_TYPE_LABELS) as TaskType[];
