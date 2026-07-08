import { useCallback, useRef, useState } from 'react';

export interface Command {
  label: string;
  undo: () => Promise<void>;
  redo: () => Promise<void>;
}

/** A simple command stack: push on every edit, ctrl+Z / ctrl+Y to walk it. */
export function useUndoStack(limit = 50) {
  const undoStack = useRef<Command[]>([]);
  const redoStack = useRef<Command[]>([]);
  const [, bump] = useState(0);
  const refresh = () => bump((n) => n + 1);

  const push = useCallback((cmd: Command) => {
    undoStack.current.push(cmd);
    if (undoStack.current.length > limit) undoStack.current.shift();
    redoStack.current = [];
    refresh();
  }, [limit]);

  const undo = useCallback(async () => {
    const cmd = undoStack.current.pop();
    if (!cmd) return null;
    await cmd.undo();
    redoStack.current.push(cmd);
    refresh();
    return cmd.label;
  }, []);

  const redo = useCallback(async () => {
    const cmd = redoStack.current.pop();
    if (!cmd) return null;
    await cmd.redo();
    undoStack.current.push(cmd);
    refresh();
    return cmd.label;
  }, []);

  return {
    push,
    undo,
    redo,
    canUndo: undoStack.current.length > 0,
    canRedo: redoStack.current.length > 0,
  };
}
