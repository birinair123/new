import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';
import { formatDistanceToNow, format, isToday, isTomorrow, isYesterday } from 'date-fns';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// Note: These date functions use current time. Components using them should
// be marked 'use client' and use useEffect/useState to avoid hydration mismatch.
export function formatRelativeDate(dateString: string | null): string {
  if (!dateString) return 'Never';
  const date = new Date(dateString);
  return formatDistanceToNow(date, { addSuffix: true });
}

export function formatMeetingDate(dateString: string): string {
  const date = new Date(dateString);

  if (isToday(date)) {
    return `Today at ${format(date, 'h:mm a')}`;
  }
  if (isTomorrow(date)) {
    return `Tomorrow at ${format(date, 'h:mm a')}`;
  }
  if (isYesterday(date)) {
    return `Yesterday at ${format(date, 'h:mm a')}`;
  }

  return format(date, 'MMM d, yyyy h:mm a');
}

// Safe version that returns a stable format for SSR, then updates on client
export function formatRelativeDateSafe(dateString: string | null): string {
  if (!dateString) return 'Never';
  // Return a stable date format that won't cause hydration mismatch
  return format(new Date(dateString), 'MMM d, yyyy');
}

export function formatDate(dateString: string | null): string {
  if (!dateString) return '';
  return format(new Date(dateString), 'MMM d, yyyy');
}

export function getScoreColor(score: number): string {
  if (score >= 70) return 'score-high';
  if (score >= 40) return 'score-medium';
  return 'score-low';
}

export function getScoreLabel(score: number): string {
  if (score >= 70) return 'Strong';
  if (score >= 40) return 'Moderate';
  return 'Weak';
}

export function getInteractionIcon(kind: string): string {
  switch (kind) {
    case 'meeting':
      return '📅';
    case 'email_in':
      return '📨';
    case 'email_out':
      return '📤';
    case 'linkedin_connect':
      return '🔗';
    case 'note':
      return '📝';
    default:
      return '💬';
  }
}

export function getInteractionLabel(kind: string): string {
  switch (kind) {
    case 'meeting':
      return 'Meeting';
    case 'email_in':
      return 'Email received';
    case 'email_out':
      return 'Email sent';
    case 'linkedin_connect':
      return 'Connected on LinkedIn';
    case 'note':
      return 'Note';
    default:
      return 'Interaction';
  }
}

export function truncate(str: string, length: number): string {
  if (str.length <= length) return str;
  return str.slice(0, length) + '...';
}

export function getInitials(name: string): string {
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .toUpperCase()
    .slice(0, 2);
}
