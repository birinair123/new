'use client';

import Link from 'next/link';
import { Person } from '@/lib/api';
import { ScoreBadge } from './ScoreBadge';
import { getInitials } from '@/lib/utils';
import { useRelativeDate } from '@/lib/useRelativeDate';
import { Calendar, Clock } from 'lucide-react';

interface PersonCardProps {
  person: Person;
}

export function PersonCard({ person }: PersonCardProps) {
  const score = person.score?.score_total ?? 0;
  const lastInteraction = useRelativeDate(person.score?.last_interaction_at ?? null);

  return (
    <Link href={`/people/${person.id}`} className="block">
      <div className="card p-4 hover:bg-gray-50 transition-colors active:bg-gray-100">
        <div className="flex items-start gap-3">
          {/* Avatar */}
          <div className="flex-shrink-0 w-12 h-12 rounded-full bg-primary-100 flex items-center justify-center text-primary-700 font-medium">
            {getInitials(person.full_name)}
          </div>

          {/* Info */}
          <div className="flex-1 min-w-0">
            <div className="flex items-center justify-between gap-2">
              <h3 className="text-base font-medium text-gray-900 truncate">
                {person.full_name}
              </h3>
              {person.is_tracked && <ScoreBadge score={score} size="sm" />}
            </div>

            {person.company && (
              <p className="text-sm text-gray-500 truncate mt-0.5">
                {person.title ? `${person.title} at ${person.company}` : person.company}
              </p>
            )}

            {/* Meta info */}
            <div className="flex items-center gap-4 mt-2 text-xs text-gray-400">
              {person.score?.last_interaction_at && lastInteraction && (
                <span className="flex items-center gap-1">
                  <Clock className="w-3 h-3" />
                  {lastInteraction}
                </span>
              )}
              {person.score?.next_meeting_at && (
                <span className="flex items-center gap-1 text-primary-600">
                  <Calendar className="w-3 h-3" />
                  Next meeting
                </span>
              )}
            </div>

            {/* Tags */}
            {person.tags && person.tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {person.tags.slice(0, 3).map((tag) => (
                  <span key={tag} className="tag bg-gray-100 text-gray-600">
                    {tag}
                  </span>
                ))}
                {person.tags.length > 3 && (
                  <span className="tag bg-gray-100 text-gray-400">
                    +{person.tags.length - 3}
                  </span>
                )}
              </div>
            )}
          </div>

          {/* Chevron */}
          <svg
            className="w-5 h-5 text-gray-400 flex-shrink-0"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
        </div>
      </div>
    </Link>
  );
}
