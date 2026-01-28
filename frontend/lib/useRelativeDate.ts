'use client';

import { useState, useEffect } from 'react';
import { formatRelativeDate, formatMeetingDate, formatDate } from './utils';

/**
 * Hook to format relative dates that updates on the client.
 * Returns a stable placeholder during SSR to avoid hydration mismatch.
 */
export function useRelativeDate(dateString: string | null): string {
  const [formatted, setFormatted] = useState<string>('');

  useEffect(() => {
    setFormatted(formatRelativeDate(dateString));
  }, [dateString]);

  // Return empty string during SSR, actual value after hydration
  return formatted;
}

/**
 * Hook to format meeting dates (with Today/Tomorrow/Yesterday).
 * Returns stable date format during SSR, updates with relative on client.
 */
export function useMeetingDate(dateString: string): string {
  // Use stable date format as initial value for SSR
  const [formatted, setFormatted] = useState<string>(() => formatDate(dateString));

  useEffect(() => {
    setFormatted(formatMeetingDate(dateString));
  }, [dateString]);

  return formatted;
}
