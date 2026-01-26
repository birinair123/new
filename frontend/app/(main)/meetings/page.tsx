'use client';

import useSWR from 'swr';
import { api, CalendarOccurrence } from '@/lib/api';
import { formatMeetingDate } from '@/lib/utils';
import { Calendar, MapPin, Users, RefreshCw } from 'lucide-react';

export default function MeetingsPage() {
  const { data, error, isLoading, mutate } = useSWR(
    'upcoming-meetings',
    () => api.getUpcomingMeetings(30),
    { revalidateOnFocus: false }
  );

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="sticky top-0 bg-white border-b border-gray-200 px-4 py-3 z-10">
        <div className="flex items-center justify-between">
          <h1 className="text-xl font-bold text-gray-900">Upcoming Meetings</h1>
          <button
            onClick={() => mutate()}
            className="p-2 text-gray-500 hover:text-primary-600 transition-colors"
          >
            <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="p-4 text-center text-red-600">
            Failed to load meetings.
          </div>
        )}

        {isLoading && !data && (
          <div className="space-y-2 p-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="card p-4">
                <div className="space-y-2">
                  <div className="skeleton h-5 w-48" />
                  <div className="skeleton h-4 w-32" />
                  <div className="skeleton h-3 w-24" />
                </div>
              </div>
            ))}
          </div>
        )}

        {data && data.items.length === 0 && (
          <div className="empty-state">
            <Calendar className="w-12 h-12 text-gray-300 mb-4" />
            <p className="text-gray-500">No upcoming meetings</p>
            <p className="text-sm text-gray-400 mt-2">
              Import calendar data to see your meetings
            </p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <div className="divide-y divide-gray-100">
            {data.items.map((meeting) => (
              <MeetingCard key={meeting.id} meeting={meeting} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MeetingCard({ meeting }: { meeting: CalendarOccurrence }) {
  const otherParticipants = meeting.participants.filter(
    (p) => p.email !== meeting.organizer_email
  );

  return (
    <div className="p-4 hover:bg-gray-50 transition-colors">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-10 h-10 rounded-lg bg-primary-100 flex items-center justify-center text-primary-600">
          <Calendar className="w-5 h-5" />
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-medium text-gray-900 truncate">
            {meeting.subject || 'Untitled Meeting'}
          </h3>
          <p className="text-sm text-primary-600 mt-0.5">
            {formatMeetingDate(meeting.start_at)}
          </p>

          {meeting.location && (
            <p className="text-sm text-gray-500 mt-1 flex items-center gap-1">
              <MapPin className="w-3.5 h-3.5" />
              {meeting.location}
            </p>
          )}

          {otherParticipants.length > 0 && (
            <div className="mt-2 flex items-center gap-1 text-xs text-gray-500">
              <Users className="w-3.5 h-3.5" />
              <span>
                {otherParticipants.length === 1
                  ? otherParticipants[0].name || otherParticipants[0].email
                  : `${otherParticipants.length} participants`}
              </span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
