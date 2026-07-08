import type {
  AgentAction,
  AgentExplanation,
  AgentStatus,
  Attachment,
  Comment,
  DashboardSummary,
  DependencyResult,
  DeviceModel,
  GanttTask,
  Leave,
  Notification,
  PlanCommitResult,
  PlanDraft,
  Project,
  RescheduleResult,
  Task,
  TestCycle,
  TestRequest,
  User,
  Workload,
} from '../types';
import { api } from './client';

// ---- auth -----------------------------------------------------------------
export const authApi = {
  login: (email: string, password: string) =>
    api
      .post<{ access_token: string; user: User }>('/auth/login', { email, password })
      .then((r) => r.data),
  me: () => api.get<User>('/auth/me').then((r) => r.data),
};

// ---- users ------------------------------------------------------------------
export const usersApi = {
  list: () => api.get<User[]>('/users').then((r) => r.data),
  create: (data: Partial<User> & { password: string }) =>
    api.post<User>('/users', data).then((r) => r.data),
  update: (id: number, data: Partial<User> & { password?: string }) =>
    api.put<User>(`/users/${id}`, data).then((r) => r.data),
  workload: (id: number) => api.get<Workload>(`/users/${id}/workload`).then((r) => r.data),
};

// ---- projects ---------------------------------------------------------------
export const projectsApi = {
  list: () => api.get<Project[]>('/projects').then((r) => r.data),
  create: (data: Partial<Project>) => api.post<Project>('/projects', data).then((r) => r.data),
  update: (id: number, data: Partial<Project>) =>
    api.put<Project>(`/projects/${id}`, data).then((r) => r.data),
  remove: (id: number) => api.delete(`/projects/${id}`),
  testRequests: (id: number) =>
    api.get<TestRequest[]>(`/projects/${id}/test-requests`).then((r) => r.data),
};

// ---- test cycles --------------------------------------------------------------
export const testCyclesApi = {
  list: (projectId?: number) =>
    api
      .get<TestCycle[]>('/test-cycles', { params: { project_id: projectId } })
      .then((r) => r.data),
  create: (data: Partial<TestCycle>) =>
    api.post<TestCycle>('/test-cycles', data).then((r) => r.data),
  update: (id: number, data: Partial<TestCycle>) =>
    api.put<TestCycle>(`/test-cycles/${id}`, data).then((r) => r.data),
  remove: (id: number) => api.delete(`/test-cycles/${id}`),
};

// ---- test requests -------------------------------------------------------------
export const testRequestsApi = {
  list: (params?: { project_id?: number; status?: string }) =>
    api.get<TestRequest[]>('/test-requests', { params }).then((r) => r.data),
  create: (data: Partial<TestRequest>) =>
    api.post<TestRequest>('/test-requests', data).then((r) => r.data),
  update: (id: number, data: Partial<TestRequest>) =>
    api.put<TestRequest>(`/test-requests/${id}`, data).then((r) => r.data),
  remove: (id: number) => api.delete(`/test-requests/${id}`),
  tasks: (id: number) => api.get<Task[]>(`/test-requests/${id}/tasks`).then((r) => r.data),
};

// ---- tasks ----------------------------------------------------------------------
export interface TaskFilters {
  status?: string;
  assigned_to?: number;
  project_id?: number;
  test_request_id?: number;
  priority?: string;
  task_type?: string;
  overdue?: boolean;
  search?: string;
}

export const tasksApi = {
  list: (filters?: TaskFilters) =>
    api.get<Task[]>('/tasks', { params: filters }).then((r) => r.data),
  gantt: (params?: { project_id?: number; test_cycle_id?: number; assigned_to?: number }) =>
    api.get<GanttTask[]>('/tasks/gantt', { params }).then((r) => r.data),
  get: (id: number) => api.get<Task>(`/tasks/${id}`).then((r) => r.data),
  create: (data: Partial<Task>) => api.post<Task>('/tasks', data).then((r) => r.data),
  update: (id: number, data: Partial<Task>) =>
    api.put<Task>(`/tasks/${id}`, data).then((r) => r.data),
  updateStatus: (id: number, status: string, actual_hours?: number) =>
    api.patch<Task>(`/tasks/${id}/status`, { status, actual_hours }).then((r) => r.data),
  remove: (id: number) => api.delete(`/tasks/${id}`),
  // E1 scheduling endpoints (consumed by the Gantt workspace)
  move: (id: number, start_date: string, keep_duration = true) =>
    api
      .patch<RescheduleResult>(`/tasks/${id}/move`, { start_date, keep_duration })
      .then((r) => r.data),
  resize: (id: number, args: { due_date?: string; duration_days?: number }) =>
    api.patch<RescheduleResult>(`/tasks/${id}/resize`, args).then((r) => r.data),
  addDependency: (id: number, depends_on_task_id: number) =>
    api
      .post<DependencyResult>(`/tasks/${id}/dependencies`, { depends_on_task_id })
      .then((r) => r.data),
  removeDependency: (id: number, depId: number) =>
    api.delete<DependencyResult>(`/tasks/${id}/dependencies/${depId}`).then((r) => r.data),
  comments: (taskId: number) =>
    api.get<Comment[]>(`/tasks/${taskId}/comments`).then((r) => r.data),
  addComment: (taskId: number, content: string) =>
    api.post<Comment>(`/tasks/${taskId}/comments`, { content }).then((r) => r.data),
  deleteComment: (taskId: number, commentId: number) =>
    api.delete(`/tasks/${taskId}/comments/${commentId}`),
  attachments: (taskId: number) =>
    api.get<Attachment[]>(`/tasks/${taskId}/attachments`).then((r) => r.data),
  uploadAttachment: (taskId: number, file: File) => {
    const form = new FormData();
    form.append('file', file);
    return api.post<Attachment>(`/tasks/${taskId}/attachments`, form).then((r) => r.data);
  },
  deleteAttachment: (taskId: number, attId: number) =>
    api.delete(`/tasks/${taskId}/attachments/${attId}`),
};

// ---- leaves -------------------------------------------------------------------
export const leavesApi = {
  list: (params?: { user_id?: number; status?: string }) =>
    api.get<Leave[]>('/leaves', { params }).then((r) => r.data),
  create: (data: Partial<Leave>) => api.post<Leave>('/leaves', data).then((r) => r.data),
  approve: (id: number, status: 'approved' | 'rejected') =>
    api.patch<Leave>(`/leaves/${id}/approve`, { status }).then((r) => r.data),
  remove: (id: number) => api.delete(`/leaves/${id}`),
};

// ---- device models -------------------------------------------------------------
export const deviceModelsApi = {
  list: (activeOnly = false) =>
    api
      .get<DeviceModel[]>('/device-models', { params: { active_only: activeOnly } })
      .then((r) => r.data),
  create: (data: Partial<DeviceModel>) =>
    api.post<DeviceModel>('/device-models', data).then((r) => r.data),
  update: (id: number, data: Partial<DeviceModel>) =>
    api.put<DeviceModel>(`/device-models/${id}`, data).then((r) => r.data),
  remove: (id: number) => api.delete(`/device-models/${id}`),
};

// ---- dashboard --------------------------------------------------------------------
export const dashboardApi = {
  summary: () => api.get<DashboardSummary>('/dashboard/summary').then((r) => r.data),
  teamWorkload: () => api.get<Workload[]>('/dashboard/team-workload').then((r) => r.data),
  taskTypes: () =>
    api
      .get<{ task_type: string; count: number }[]>('/dashboard/task-types')
      .then((r) => r.data),
  projectProgress: () =>
    api
      .get<
        {
          project_id: number;
          name: string;
          color_hex: string;
          total_tasks: number;
          completed_tasks: number;
          percent_complete: number;
          by_status: Record<string, number>;
        }[]
      >('/dashboard/project-progress')
      .then((r) => r.data),
  overdue: () =>
    api
      .get<
        {
          id: number;
          title: string;
          due_date: string;
          days_overdue: number;
          status: string;
          priority: string;
          assignee_name: string | null;
        }[]
      >('/dashboard/overdue')
      .then((r) => r.data),
  upcomingLeaves: () =>
    api
      .get<
        {
          id: number;
          user_id: number;
          user_name: string;
          start_date: string;
          end_date: string;
          leave_type: string;
        }[]
      >('/dashboard/upcoming-leaves')
      .then((r) => r.data),
  exportTasksUrl: '/api/dashboard/export/tasks',
};

// ---- notifications -----------------------------------------------------------------
export const notificationsApi = {
  list: (unreadOnly = false) =>
    api
      .get<Notification[]>('/notifications', { params: { unread_only: unreadOnly } })
      .then((r) => r.data),
  unreadCount: () =>
    api.get<{ count: number }>('/notifications/unread-count').then((r) => r.data),
  markRead: (id: number) => api.patch(`/notifications/${id}/read`),
  markAllRead: () => api.post('/notifications/read-all'),
};

// ---- AI agent ------------------------------------------------------------------------
export const agentApi = {
  status: () => api.get<AgentStatus>('/agent/status').then((r) => r.data),
  chat: (messages: { role: string; content: string }[]) =>
    api
      .post<{
        reply: string;
        actions: AgentAction[];
        explanation: AgentExplanation[];
        pending_confirmation: boolean;
      }>('/agent/chat', { messages })
      .then((r) => r.data),
  plan: (brief: string, project_id?: number, start_date?: string) =>
    api.post<PlanDraft>('/agent/plan', { brief, project_id, start_date }).then((r) => r.data),
  planRefresh: (draft: PlanDraft) =>
    api.post<PlanDraft>('/agent/plan/refresh', { draft }).then((r) => r.data),
  planCommit: (draft: PlanDraft) =>
    api.post<PlanCommitResult>('/agent/plan/commit', { draft }).then((r) => r.data),
};
