'use client';

import { useState } from 'react';
import useSWR from 'swr';
import { api, ReviewQueueItem } from '@/lib/api';
import { formatRelativeDate, getInitials } from '@/lib/utils';
import { Check, X, SkipForward, RefreshCw, Users } from 'lucide-react';

export default function ReviewPage() {
  const { data, error, isLoading, mutate } = useSWR(
    'review-queue',
    () => api.getReviewQueue(),
    { revalidateOnFocus: false }
  );

  const { data: stats, mutate: mutateStats } = useSWR(
    'review-stats',
    () => api.getReviewStats()
  );

  const handleAction = async (itemId: string, action: 'accept' | 'reject' | 'ignore') => {
    await api.reviewAction(itemId, action);
    mutate();
    mutateStats();
  };

  const handleRefresh = async () => {
    await fetch('/api/review/refresh', { method: 'POST' });
    mutate();
    mutateStats();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="sticky top-0 bg-white border-b border-gray-200 px-4 py-3 z-10">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-xl font-bold text-gray-900">Review Queue</h1>
          <button
            onClick={handleRefresh}
            className="p-2 text-gray-500 hover:text-primary-600 transition-colors"
          >
            <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        {stats && (
          <p className="text-sm text-gray-500">
            {stats.total_pending} pending items
            {stats.high_signal_unlinked_count > 0 && (
              <span className="ml-2 text-primary-600">
                ({stats.high_signal_unlinked_count} high-signal unlinked)
              </span>
            )}
          </p>
        )}
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="p-4 text-center text-red-600">
            Failed to load review queue.
          </div>
        )}

        {isLoading && !data && (
          <div className="space-y-2 p-4">
            {[...Array(3)].map((_, i) => (
              <div key={i} className="card p-4">
                <div className="flex items-start gap-3">
                  <div className="skeleton w-10 h-10 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <div className="skeleton h-5 w-32" />
                    <div className="skeleton h-4 w-48" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {data && data.items.length === 0 && (
          <div className="empty-state">
            <Users className="w-12 h-12 text-gray-300 mb-4" />
            <p className="text-gray-500">No items to review</p>
            <p className="text-sm text-gray-400 mt-2">
              High-signal email contacts will appear here for promotion
            </p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <div className="divide-y divide-gray-100">
            {data.items.map((item) => (
              <ReviewCard
                key={item.id}
                item={item}
                onAction={(action) => handleAction(item.id, action)}
              />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function ReviewCard({
  item,
  onAction,
}: {
  item: ReviewQueueItem;
  onAction: (action: 'accept' | 'reject' | 'ignore') => void;
}) {
  const [loading, setLoading] = useState(false);

  const handleAction = async (action: 'accept' | 'reject' | 'ignore') => {
    setLoading(true);
    await onAction(action);
    setLoading(false);
  };

  return (
    <div className="p-4">
      <div className="flex items-start gap-3">
        <div className="flex-shrink-0 w-10 h-10 rounded-full bg-gray-100 flex items-center justify-center text-gray-600 font-medium">
          {getInitials(item.person.full_name)}
        </div>
        <div className="flex-1 min-w-0">
          <h3 className="text-base font-medium text-gray-900">
            {item.person.full_name}
          </h3>
          {item.person.company && (
            <p className="text-sm text-gray-500">{item.person.company}</p>
          )}
          <p className="text-xs text-gray-400 mt-1">
            {item.interaction_count} interactions
          </p>

          {/* Queue type specific info */}
          {item.queue_type === 'link_suggestion' && item.suggested_person && (
            <div className="mt-2 p-2 bg-primary-50 rounded-lg">
              <p className="text-xs text-primary-700">
                Possible match: <strong>{item.suggested_person.full_name}</strong>
                {item.confidence_score && ` (${Math.round(item.confidence_score * 100)}% confident)`}
              </p>
            </div>
          )}

          {item.queue_type === 'promote' && (
            <div className="mt-2 p-2 bg-green-50 rounded-lg">
              <p className="text-xs text-green-700">
                High activity contact - consider promoting to tracked
              </p>
            </div>
          )}
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-2 mt-3 ml-13">
        <button
          onClick={() => handleAction('accept')}
          disabled={loading}
          className="flex-1 btn btn-primary py-2 text-sm"
        >
          <Check className="w-4 h-4 mr-1" />
          {item.queue_type === 'promote' ? 'Promote' : 'Link'}
        </button>
        <button
          onClick={() => handleAction('reject')}
          disabled={loading}
          className="btn btn-secondary py-2 text-sm"
        >
          <X className="w-4 h-4" />
        </button>
        <button
          onClick={() => handleAction('ignore')}
          disabled={loading}
          className="btn btn-secondary py-2 text-sm"
        >
          <SkipForward className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
