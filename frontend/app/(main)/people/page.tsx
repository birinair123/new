'use client';

import { useState, useCallback } from 'react';
import useSWR from 'swr';
import { api, PeopleListResponse } from '@/lib/api';
import { PersonCard } from '@/components/PersonCard';
import { SearchInput } from '@/components/SearchInput';
import { RefreshCw } from 'lucide-react';

export default function PeoplePage() {
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);

  const { data, error, isLoading, mutate } = useSWR<PeopleListResponse>(
    ['people', search, page],
    () => api.listPeople({ page, search, tracked_only: true, sort_by: 'score' }),
    { revalidateOnFocus: false }
  );

  const handleSearch = useCallback((value: string) => {
    setSearch(value);
    setPage(1);
  }, []);

  const handleRefresh = () => {
    mutate();
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="sticky top-0 bg-white border-b border-gray-200 px-4 py-3 z-10">
        <div className="flex items-center justify-between mb-3">
          <h1 className="text-xl font-bold text-gray-900">People</h1>
          <button
            onClick={handleRefresh}
            className="p-2 text-gray-500 hover:text-primary-600 transition-colors"
          >
            <RefreshCw className={`w-5 h-5 ${isLoading ? 'animate-spin' : ''}`} />
          </button>
        </div>
        <SearchInput
          value={search}
          onChange={handleSearch}
          placeholder="Search by name, company..."
        />
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto">
        {error && (
          <div className="p-4 text-center text-red-600">
            Failed to load people. Please try again.
          </div>
        )}

        {isLoading && !data && (
          <div className="space-y-2 p-4">
            {[...Array(5)].map((_, i) => (
              <div key={i} className="card p-4">
                <div className="flex items-start gap-3">
                  <div className="skeleton w-12 h-12 rounded-full" />
                  <div className="flex-1 space-y-2">
                    <div className="skeleton h-4 w-32" />
                    <div className="skeleton h-3 w-48" />
                    <div className="skeleton h-3 w-24" />
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {data && data.items.length === 0 && (
          <div className="empty-state">
            <p className="text-gray-500">
              {search ? 'No people match your search' : 'No people yet'}
            </p>
            <p className="text-sm text-gray-400 mt-2">
              Import your LinkedIn connections to get started
            </p>
          </div>
        )}

        {data && data.items.length > 0 && (
          <>
            <div className="divide-y divide-gray-100">
              {data.items.map((person) => (
                <PersonCard key={person.id} person={person} />
              ))}
            </div>

            {/* Pagination */}
            {data.has_more && (
              <div className="p-4 text-center">
                <button
                  onClick={() => setPage((p) => p + 1)}
                  className="btn btn-secondary"
                >
                  Load more
                </button>
              </div>
            )}
          </>
        )}

        {/* Stats */}
        {data && (
          <div className="p-4 text-center text-xs text-gray-400">
            Showing {data.items.length} of {data.total} people
          </div>
        )}
      </div>
    </div>
  );
}
