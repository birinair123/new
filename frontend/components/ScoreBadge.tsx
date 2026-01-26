'use client';

import { cn, getScoreColor, getScoreLabel } from '@/lib/utils';

interface ScoreBadgeProps {
  score: number;
  showLabel?: boolean;
  size?: 'sm' | 'md' | 'lg';
}

export function ScoreBadge({ score, showLabel = false, size = 'md' }: ScoreBadgeProps) {
  const sizeClasses = {
    sm: 'text-xs px-1.5 py-0.5',
    md: 'text-sm px-2 py-1',
    lg: 'text-base px-3 py-1.5',
  };

  return (
    <span
      className={cn(
        'inline-flex items-center rounded-full font-medium',
        getScoreColor(score),
        sizeClasses[size]
      )}
    >
      {score}
      {showLabel && <span className="ml-1 opacity-75">{getScoreLabel(score)}</span>}
    </span>
  );
}
