'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import useSWR from 'swr';
import { api, Person, InteractionsListResponse } from '@/lib/api';
import { ScoreBadge } from '@/components/ScoreBadge';
import { ScoreBreakdown } from '@/components/ScoreBreakdown';
import { Timeline } from '@/components/Timeline';
import { formatRelativeDate, formatDate, getInitials } from '@/lib/utils';
import {
  ArrowLeft,
  Calendar,
  Mail,
  Linkedin,
  Building,
  Tag,
  MoreVertical,
  ExternalLink,
} from 'lucide-react';

export default function PersonDetailPage() {
  const params = useParams();
  const router = useRouter();
  const personId = params.id as string;
  const [showScoreBreakdown, setShowScoreBreakdown] = useState(false);
  const [newTag, setNewTag] = useState('');

  const { data: person, error, mutate } = useSWR<Person>(
    personId ? ['person', personId] : null,
    () => api.getPerson(personId)
  );

  const { data: timeline } = useSWR<InteractionsListResponse>(
    personId ? ['timeline', personId] : null,
    () => api.getPersonTimeline(personId)
  );

  const handleAddTag = async () => {
    if (!newTag.trim()) return;
    await api.addTag(personId, newTag.trim());
    setNewTag('');
    mutate();
  };

  const handleRemoveTag = async (tag: string) => {
    await api.removeTag(personId, tag);
    mutate();
  };

  const handlePromote = async () => {
    await api.promotePerson(personId);
    mutate();
  };

  if (error) {
    return (
      <div className="p-4 text-center text-red-600">
        Failed to load person details.
      </div>
    );
  }

  if (!person) {
    return (
      <div className="animate-pulse p-4 space-y-4">
        <div className="flex items-center gap-4">
          <div className="skeleton w-16 h-16 rounded-full" />
          <div className="space-y-2 flex-1">
            <div className="skeleton h-6 w-48" />
            <div className="skeleton h-4 w-32" />
          </div>
        </div>
        <div className="skeleton h-24 w-full rounded-lg" />
        <div className="skeleton h-48 w-full rounded-lg" />
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <header className="sticky top-0 bg-white border-b border-gray-200 px-4 py-3 z-10">
        <div className="flex items-center gap-3">
          <button
            onClick={() => router.back()}
            className="p-2 -ml-2 text-gray-500 hover:text-gray-900"
          >
            <ArrowLeft className="w-5 h-5" />
          </button>
          <h1 className="text-lg font-semibold text-gray-900 truncate flex-1">
            {person.full_name}
          </h1>
          <button className="p-2 text-gray-500 hover:text-gray-900">
            <MoreVertical className="w-5 h-5" />
          </button>
        </div>
      </header>

      <div className="p-4 space-y-4">
        {/* Profile card */}
        <div className="card p-4">
          <div className="flex items-start gap-4">
            <div className="flex-shrink-0 w-16 h-16 rounded-full bg-primary-100 flex items-center justify-center text-primary-700 text-xl font-medium">
              {getInitials(person.full_name)}
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2 mb-1">
                <h2 className="text-xl font-bold text-gray-900 truncate">
                  {person.full_name}
                </h2>
                {person.is_tracked && person.score && (
                  <button onClick={() => setShowScoreBreakdown(!showScoreBreakdown)}>
                    <ScoreBadge score={person.score.score_total} />
                  </button>
                )}
              </div>
              {(person.title || person.company) && (
                <p className="text-sm text-gray-500 flex items-center gap-1">
                  <Building className="w-4 h-4" />
                  {person.title ? `${person.title} at ${person.company}` : person.company}
                </p>
              )}
            </div>
          </div>

          {/* Contact actions */}
          <div className="flex gap-2 mt-4">
            {person.primary_email && (
              <a
                href={`mailto:${person.primary_email}`}
                className="btn btn-secondary flex-1"
              >
                <Mail className="w-4 h-4 mr-2" />
                Email
              </a>
            )}
            {person.linkedin_url && (
              <a
                href={person.linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                className="btn btn-linkedin flex-1"
              >
                <Linkedin className="w-4 h-4 mr-2" />
                LinkedIn
                <ExternalLink className="w-3 h-3 ml-1" />
              </a>
            )}
          </div>

          {/* Promote button for non-tracked */}
          {!person.is_tracked && (
            <button
              onClick={handlePromote}
              className="btn btn-primary w-full mt-3"
            >
              Promote to Tracked
            </button>
          )}
        </div>

        {/* Score breakdown (expandable) */}
        {showScoreBreakdown && person.score && (
          <div className="card p-4">
            <ScoreBreakdown score={person.score} />
          </div>
        )}

        {/* Quick stats */}
        <div className="grid grid-cols-2 gap-3">
          <div className="card p-3">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Last Contact</p>
            <p className="text-sm font-medium text-gray-900 mt-1">
              {formatRelativeDate(person.score?.last_interaction_at)}
            </p>
          </div>
          <div className="card p-3">
            <p className="text-xs text-gray-500 uppercase tracking-wide">Connected</p>
            <p className="text-sm font-medium text-gray-900 mt-1">
              {person.linkedin_connected_at
                ? formatDate(person.linkedin_connected_at)
                : 'Unknown'}
            </p>
          </div>
          {person.score?.next_meeting_at && (
            <div className="card p-3 col-span-2 bg-primary-50 border-primary-100">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-primary-600" />
                <p className="text-sm font-medium text-primary-700">
                  Next meeting: {formatDate(person.score.next_meeting_at)}
                </p>
              </div>
            </div>
          )}
        </div>

        {/* Tags */}
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <Tag className="w-4 h-4 text-gray-500" />
            <h3 className="text-sm font-medium text-gray-900">Tags</h3>
          </div>
          <div className="flex flex-wrap gap-2 mb-3">
            {person.tags?.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full bg-gray-100 text-sm text-gray-700"
              >
                {tag}
                <button
                  onClick={() => handleRemoveTag(tag)}
                  className="text-gray-400 hover:text-gray-600"
                >
                  &times;
                </button>
              </span>
            ))}
            {(!person.tags || person.tags.length === 0) && (
              <span className="text-sm text-gray-400">No tags</span>
            )}
          </div>
          <div className="flex gap-2">
            <input
              type="text"
              value={newTag}
              onChange={(e) => setNewTag(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAddTag()}
              placeholder="Add tag..."
              className="input flex-1 py-2 text-sm"
            />
            <button onClick={handleAddTag} className="btn btn-secondary py-2">
              Add
            </button>
          </div>
        </div>

        {/* Timeline */}
        <div className="card p-4">
          <h3 className="text-sm font-medium text-gray-900 mb-4">Interaction Timeline</h3>
          {timeline ? (
            <Timeline interactions={timeline.items} />
          ) : (
            <div className="space-y-3">
              {[...Array(3)].map((_, i) => (
                <div key={i} className="flex gap-3">
                  <div className="skeleton w-4 h-4 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <div className="skeleton h-4 w-24" />
                    <div className="skeleton h-3 w-full" />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
