// Pure date/pixel math for the custom Gantt timeline.

import { addDays, differenceInCalendarDays, format, isWeekend, parseISO, startOfWeek } from 'date-fns';

export type Zoom = 'day' | 'week' | 'month';

export const PX_PER_DAY: Record<Zoom, number> = { day: 36, week: 14, month: 5 };
export const ROW_HEIGHT = 34;
export const BAR_HEIGHT = 22;
export const HEADER_HEIGHT = 44;

export interface TimeScale {
  start: Date; // first visible day
  days: number; // total day count
  pxPerDay: number;
  width: number;
}

export function buildScale(minIso: string, maxIso: string, zoom: Zoom): TimeScale {
  // pad the range and align to Monday so week/month headers look right
  const start = startOfWeek(addDays(parseISO(minIso), -7), { weekStartsOn: 1 });
  const end = addDays(parseISO(maxIso), 14);
  const days = Math.max(differenceInCalendarDays(end, start) + 1, 14);
  const pxPerDay = PX_PER_DAY[zoom];
  return { start, days, pxPerDay, width: days * pxPerDay };
}

export function dateToX(scale: TimeScale, iso: string): number {
  return differenceInCalendarDays(parseISO(iso), scale.start) * scale.pxPerDay;
}

export function xToDate(scale: TimeScale, x: number): string {
  const day = Math.round(x / scale.pxPerDay);
  return format(addDays(scale.start, day), 'yyyy-MM-dd');
}

/** Inclusive bar geometry for a task spanning [startIso, dueIso]. */
export function barRect(scale: TimeScale, startIso: string, dueIso: string) {
  const x = dateToX(scale, startIso);
  const w = dateToX(scale, dueIso) - x + scale.pxPerDay;
  return { x, width: Math.max(w, scale.pxPerDay / 2) };
}

export interface HeaderCell {
  x: number;
  width: number;
  label: string;
  isWeekend?: boolean;
}

/** Two header rows: coarse (month or week) and fine (day/week ticks). */
export function buildHeaders(scale: TimeScale, zoom: Zoom): { top: HeaderCell[]; bottom: HeaderCell[] } {
  const top: HeaderCell[] = [];
  const bottom: HeaderCell[] = [];
  let monthStart = 0;
  let currentMonth = '';
  for (let i = 0; i < scale.days; i++) {
    const day = addDays(scale.start, i);
    const monthLabel = format(day, 'MMM yyyy');
    if (monthLabel !== currentMonth) {
      if (currentMonth) top.push({ x: monthStart * scale.pxPerDay, width: (i - monthStart) * scale.pxPerDay, label: currentMonth });
      currentMonth = monthLabel;
      monthStart = i;
    }
    if (zoom === 'day') {
      bottom.push({
        x: i * scale.pxPerDay,
        width: scale.pxPerDay,
        label: format(day, 'd'),
        isWeekend: isWeekend(day),
      });
    } else if (day.getDay() === 1) {
      // Monday tick for week/month zoom
      bottom.push({ x: i * scale.pxPerDay, width: 7 * scale.pxPerDay, label: format(day, 'd MMM') });
    }
  }
  top.push({ x: monthStart * scale.pxPerDay, width: (scale.days - monthStart) * scale.pxPerDay, label: currentMonth });
  return { top, bottom };
}

export function shiftIso(iso: string, days: number): string {
  return format(addDays(parseISO(iso), days), 'yyyy-MM-dd');
}

export function spanDays(startIso: string, dueIso: string): number {
  return differenceInCalendarDays(parseISO(dueIso), parseISO(startIso)) + 1;
}
