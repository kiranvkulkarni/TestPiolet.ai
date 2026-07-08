import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Plus, Trash2 } from 'lucide-react';
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { apiErrorMessage } from '../api/client';
import { deviceModelsApi } from '../api/endpoints';
import { Badge } from '../components/shared/Badge';
import { ConfirmDialog } from '../components/shared/ConfirmDialog';
import { Field, inputClass } from '../components/shared/Field';
import { Modal } from '../components/shared/Modal';
import { useAuthStore } from '../store/authStore';
import type { DeviceModel } from '../types';

export function DeviceModels() {
  const queryClient = useQueryClient();
  const isManager = useAuthStore((s) => s.user?.role === 'manager');
  const [editing, setEditing] = useState<DeviceModel | null | 'new'>(null);
  const [deleting, setDeleting] = useState<DeviceModel | null>(null);
  const [form, setForm] = useState<Partial<DeviceModel>>({});

  const { data: devices, isLoading } = useQuery({
    queryKey: ['device-models'],
    queryFn: () => deviceModelsApi.list(),
  });

  useEffect(() => {
    if (editing === 'new') setForm({ brand: 'Samsung', is_active: true });
    else if (editing) setForm(editing);
  }, [editing]);

  const save = useMutation({
    mutationFn: (data: Partial<DeviceModel>) =>
      editing === 'new' || !editing
        ? deviceModelsApi.create(data)
        : deviceModelsApi.update(editing.id, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['device-models'] });
      toast.success('Saved');
      setEditing(null);
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  const remove = useMutation({
    mutationFn: (id: number) => deviceModelsApi.remove(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['device-models'] });
      toast.success('Device removed (or deactivated if in use)');
    },
    onError: (e) => toast.error(apiErrorMessage(e)),
  });

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Device Models</h1>
        {isManager && (
          <button
            onClick={() => setEditing('new')}
            className="flex items-center gap-1.5 rounded-lg bg-indigo-600 px-3 py-1.5 text-sm font-medium text-white hover:bg-indigo-700"
          >
            <Plus size={15} /> Add device
          </button>
        )}
      </div>

      {isLoading && <p className="text-sm text-slate-400">Loading…</p>}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs text-slate-500 uppercase">
              <th className="px-3 py-2.5">Model</th>
              <th className="px-3 py-2.5">Series</th>
              <th className="px-3 py-2.5">OS</th>
              <th className="px-3 py-2.5">Status</th>
              <th className="px-3 py-2.5"></th>
            </tr>
          </thead>
          <tbody>
            {(devices ?? []).map((d) => (
              <tr key={d.id} className="border-b border-slate-100 last:border-0 hover:bg-slate-50">
                <td className="px-3 py-2">
                  <button
                    onClick={() => isManager && setEditing(d)}
                    className="font-medium hover:text-indigo-600"
                  >
                    {d.model_name}
                  </button>
                </td>
                <td className="px-3 py-2 text-xs">{d.series ?? '—'}</td>
                <td className="px-3 py-2 text-xs">{d.os_version ?? '—'}</td>
                <td className="px-3 py-2">
                  <Badge className={d.is_active ? 'bg-green-100 text-green-700' : 'bg-slate-100 text-slate-500'}>
                    {d.is_active ? 'active' : 'inactive'}
                  </Badge>
                </td>
                <td className="px-3 py-2 text-right">
                  {isManager && (
                    <button
                      onClick={() => setDeleting(d)}
                      className="p-1 text-slate-300 hover:text-red-500"
                      aria-label="Delete device"
                    >
                      <Trash2 size={14} />
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {(devices ?? []).length === 0 && !isLoading && (
              <tr>
                <td colSpan={5} className="px-3 py-8 text-center text-slate-400">No devices yet.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <Modal
        open={!!editing}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'Add device model' : `Edit ${(editing as DeviceModel)?.model_name}`}
      >
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!form.model_name) {
              toast.error('Model name is required');
              return;
            }
            save.mutate(form);
          }}
          className="space-y-3"
        >
          <Field label="Model name">
            <input className={inputClass} value={form.model_name ?? ''} onChange={(e) => setForm((f) => ({ ...f, model_name: e.target.value }))} autoFocus placeholder="SM-S938B (Galaxy S25 Ultra)" />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Brand">
              <input className={inputClass} value={form.brand ?? ''} onChange={(e) => setForm((f) => ({ ...f, brand: e.target.value }))} />
            </Field>
            <Field label="Series">
              <input className={inputClass} value={form.series ?? ''} onChange={(e) => setForm((f) => ({ ...f, series: e.target.value || null }))} placeholder="Galaxy S" />
            </Field>
            <Field label="OS version">
              <input className={inputClass} value={form.os_version ?? ''} onChange={(e) => setForm((f) => ({ ...f, os_version: e.target.value || null }))} placeholder="Android 15 / One UI 7" />
            </Field>
            <Field label="Active">
              <select className={inputClass} value={form.is_active ? 'yes' : 'no'} onChange={(e) => setForm((f) => ({ ...f, is_active: e.target.value === 'yes' }))}>
                <option value="yes">Yes</option>
                <option value="no">No</option>
              </select>
            </Field>
          </div>
          <div className="flex justify-end gap-2 pt-1">
            <button type="button" onClick={() => setEditing(null)} className="rounded-lg border border-slate-300 px-3 py-1.5 text-sm hover:bg-slate-50">Cancel</button>
            <button type="submit" disabled={save.isPending} className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50">
              {save.isPending ? 'Saving…' : 'Save'}
            </button>
          </div>
        </form>
      </Modal>

      <ConfirmDialog
        open={!!deleting}
        title="Delete device"
        message={`Delete "${deleting?.model_name}"? Devices referenced by tasks are deactivated instead.`}
        onConfirm={() => deleting && remove.mutate(deleting.id)}
        onClose={() => setDeleting(null)}
      />
    </div>
  );
}
