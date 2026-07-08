import { Navigate, Route, Routes } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { Dashboard } from './pages/Dashboard';
import { DeviceModels } from './pages/DeviceModels';
import { GanttView } from './pages/GanttView';
import { Leaves } from './pages/Leaves';
import { Login } from './pages/Login';
import { Projects } from './pages/Projects';
import { Reports } from './pages/Reports';
import { Tasks } from './pages/Tasks';
import { Team } from './pages/Team';
import { TestRequests } from './pages/TestRequests';
import { useAuthStore } from './store/authStore';

export default function App() {
  const token = useAuthStore((s) => s.token);

  if (!token) {
    return (
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }

  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Dashboard />} />
        <Route path="/tasks" element={<Tasks />} />
        <Route path="/gantt" element={<GanttView />} />
        <Route path="/test-requests" element={<TestRequests />} />
        <Route path="/projects" element={<Projects />} />
        <Route path="/team" element={<Team />} />
        <Route path="/leaves" element={<Leaves />} />
        <Route path="/reports" element={<Reports />} />
        <Route path="/devices" element={<DeviceModels />} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
