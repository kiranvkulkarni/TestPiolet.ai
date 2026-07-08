export type UserRole = 'manager' | 'tester' | 'viewer';

export type TaskType =
  | 'functional_sanity'
  | 'functional_full_sanity'
  | 'functional_feature_verification'
  | 'functional_menu_tree'
  | 'issue_reproduction'
  | 'fix_verification'
  | 'side_effect_verification'
  | 'nonfunc_kpi_launch_time'
  | 'nonfunc_fps'
  | 'nonfunc_memory_profiling'
  | 'nonfunc_memory_leak'
  | 'nonfunc_power_consumption'
  | 'compliance_google_its'
  | 'compliance_google_cts'
  | 'compliance_sensor_fusion';

export type TaskStatus = 'pending' | 'in_progress' | 'blocked' | 'completed' | 'cancelled';
export type Priority = 'critical' | 'high' | 'medium' | 'low';
export type AutomationType = 'manual' | 'automated' | 'both';
export type ProjectStatus = 'active' | 'completed' | 'on_hold' | 'cancelled';
export type TestCycleStatus = 'planning' | 'active' | 'completed';
export type RequestStatus = 'open' | 'in_progress' | 'completed' | 'cancelled';
export type LeaveType = 'planned' | 'sick' | 'emergency' | 'comp_off';
export type LeaveStatus = 'pending' | 'approved' | 'rejected';

export interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  is_active: boolean;
  avatar_color: string;
  created_at: string;
}

export interface UserBrief {
  id: number;
  name: string;
  email: string;
  avatar_color: string;
}

export interface Workload {
  user_id: number;
  name: string;
  active_tasks: number;
  estimated_hours: number;
  by_status: Record<string, number>;
  avatar_color?: string;
}

export interface Project {
  id: number;
  name: string;
  description: string | null;
  status: ProjectStatus;
  color_hex: string;
  start_date: string | null;
  end_date: string | null;
  created_at: string;
}

export interface TestCycle {
  id: number;
  project_id: number;
  name: string;
  start_date: string | null;
  end_date: string | null;
  status: TestCycleStatus;
  created_at: string;
}

export interface TestRequest {
  id: number;
  project_id: number;
  test_cycle_id: number | null;
  title: string;
  description: string | null;
  requested_by: string | null;
  priority: Priority;
  status: RequestStatus;
  task_count: number;
  created_at: string;
}

export interface DeviceModel {
  id: number;
  brand: string;
  series: string | null;
  model_name: string;
  os_version: string | null;
  is_active: boolean;
}

export interface Task {
  id: number;
  test_request_id: number;
  title: string;
  description: string | null;
  task_type: TaskType;
  assigned_to: number | null;
  created_by: number | null;
  status: TaskStatus;
  priority: Priority;
  automation_type: AutomationType;
  start_date: string | null;
  due_date: string | null;
  completed_date: string | null;
  estimated_hours: number | null;
  actual_hours: number | null;
  build_version: string | null;
  device_model_id: number | null;
  depends_on: number | null;
  created_at: string;
  updated_at: string;
  assignee: UserBrief | null;
  device_model: DeviceModel | null;
}

export interface GanttDependencyEdge {
  id: number; // task_dependencies row id (needed to unlink)
  from_task_id: number;
}

export interface GanttTask {
  id: number;
  title: string;
  start_date: string;
  due_date: string;
  status: TaskStatus;
  priority: Priority;
  progress: number;
  assigned_to: number | null;
  assignee_name: string | null;
  project_id: number | null;
  project_name: string | null;
  project_color: string | null;
  test_request_id: number;
  test_request_title: string;
  depends_on: number | null;
  dependencies: number[];
  dependency_edges: GanttDependencyEdge[];
  critical: boolean;
  slack_days: number;
}

export interface RescheduleResult {
  task: Task;
  affected: Task[];
  critical_path: number[];
}

export interface DependencyResult {
  dependency: { id: number; from_task_id: number; to_task_id: number; type: string } | null;
  affected: Task[];
  critical_path: number[];
}

export interface Leave {
  id: number;
  user_id: number;
  start_date: string;
  end_date: string;
  leave_type: LeaveType;
  status: LeaveStatus;
  reason: string | null;
  approved_by: number | null;
  user: UserBrief | null;
  created_at: string;
}

export interface Comment {
  id: number;
  task_id: number;
  user_id: number;
  content: string;
  created_at: string;
  user: UserBrief | null;
}

export interface Attachment {
  id: number;
  task_id: number;
  filename: string;
  original_filename: string;
  file_size: number;
  mime_type: string | null;
  uploaded_by: number | null;
  created_at: string;
}

export interface Notification {
  id: number;
  type: string;
  message: string;
  entity_type: string | null;
  entity_id: number | null;
  is_read: boolean;
  created_at: string;
}

export interface DashboardSummary {
  total_tasks: number;
  pending: number;
  in_progress: number;
  blocked: number;
  completed: number;
  overdue: number;
  active_projects: number;
  open_requests: number;
  team_size: number;
}

export interface AgentStatus {
  enabled: boolean;
  llm_reachable: boolean;
  model: string | null;
}

export type AgentUndo =
  | { kind: 'update_tasks'; tasks: { id: number; fields: Record<string, unknown> }[] }
  | { kind: 'delete_tasks'; ids: number[] }
  | { kind: 'add_dependency'; from_task_id: number; to_task_id: number }
  | { kind: 'remove_dependency'; task_id: number; dep_id: number };

export interface AgentAction {
  tool: string;
  args: Record<string, unknown>;
  result: Record<string, unknown> & {
    rationale?: string;
    confidence?: number;
    undo?: AgentUndo;
  };
}

export interface AgentExplanation {
  tool: string;
  rationale: string;
  confidence: number | null;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  actions?: AgentAction[];
  explanation?: AgentExplanation[];
  pendingConfirmation?: boolean;
}

// ---- AI Planner (E4) --------------------------------------------------------

export interface DraftTask {
  ref: string;
  title: string;
  task_type: TaskType;
  priority: Priority;
  estimated_hours: number;
  device_model_id: number | null;
  device_model_name: string | null;
  assigned_to: number | null;
  assignee_name: string | null;
  depends_on_refs: string[];
  start_date: string | null;
  due_date: string | null;
}

export interface DraftRequest {
  title: string;
  priority: Priority;
  description: string | null;
  tasks: DraftTask[];
}

export interface PlanDraft {
  project_id: number | null;
  project_name: string | null;
  start_date: string;
  requests: DraftRequest[];
  warnings: string[];
  rationale: string;
  project_end: string | null;
}

export interface PlanCommitResult {
  project_id: number;
  request_ids: number[];
  task_ids: number[];
  dependency_count: number;
  rationale: string;
}
