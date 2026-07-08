import { cn } from '../../utils/cn';

interface AvatarProps {
  name: string;
  color?: string;
  size?: 'sm' | 'md';
  className?: string;
}

export function Avatar({ name, color = '#6366f1', size = 'md', className }: AvatarProps) {
  const initials = name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase();
  return (
    <span
      title={name}
      className={cn(
        'inline-flex shrink-0 items-center justify-center rounded-full font-semibold text-white',
        size === 'sm' ? 'h-6 w-6 text-[10px]' : 'h-8 w-8 text-xs',
        className,
      )}
      style={{ backgroundColor: color }}
    >
      {initials}
    </span>
  );
}
