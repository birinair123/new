'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import useSWR from 'swr';
import { api } from '@/lib/api';
import {
  LogOut,
  Upload,
  RefreshCw,
  Database,
  Calendar,
  Mail,
  CheckCircle,
  XCircle,
} from 'lucide-react';

export default function SettingsPage() {
  const router = useRouter();
  const [importing, setImporting] = useState<string | null>(null);

  const { data: status, mutate } = useSWR('ingestion-status', () =>
    api.getIngestionStatus()
  );

  const handleLogout = async () => {
    await api.logout();
    router.push('/login');
  };

  const handleIngestLinkedIn = async () => {
    setImporting('linkedin');
    try {
      await api.ingestLinkedIn();
      mutate();
    } catch (e) {
      console.error(e);
    }
    setImporting(null);
  };

  const handleIngestCalendar = async () => {
    setImporting('calendar');
    try {
      await api.ingestOstCalendar();
      mutate();
    } catch (e) {
      console.error(e);
    }
    setImporting(null);
  };

  const handleRecomputeScores = async () => {
    setImporting('scores');
    try {
      await api.recomputeScores();
    } catch (e) {
      console.error(e);
    }
    setImporting(null);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <header className="sticky top-0 bg-white border-b border-gray-200 px-4 py-3 z-10">
        <h1 className="text-xl font-bold text-gray-900">Settings</h1>
      </header>

      {/* Content */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {/* Data Sources */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">
            Data Sources
          </h2>

          <div className="space-y-4">
            {/* LinkedIn */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-blue-100 flex items-center justify-center text-blue-600">
                  <Upload className="w-5 h-5" />
                </div>
                <div>
                  <p className="font-medium text-gray-900">LinkedIn CSV</p>
                  <p className="text-xs text-gray-500">
                    {status?.linkedin_csv_available ? (
                      <span className="flex items-center gap-1 text-green-600">
                        <CheckCircle className="w-3 h-3" />
                        File available
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-gray-400">
                        <XCircle className="w-3 h-3" />
                        No file found
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <button
                onClick={handleIngestLinkedIn}
                disabled={importing === 'linkedin' || !status?.linkedin_csv_available}
                className="btn btn-secondary py-2 text-sm"
              >
                {importing === 'linkedin' ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  'Import'
                )}
              </button>
            </div>

            {/* Calendar */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-green-100 flex items-center justify-center text-green-600">
                  <Calendar className="w-5 h-5" />
                </div>
                <div>
                  <p className="font-medium text-gray-900">Calendar (OST)</p>
                  <p className="text-xs text-gray-500">
                    {status?.ost_jsonl_available ? (
                      <span className="flex items-center gap-1 text-green-600">
                        <CheckCircle className="w-3 h-3" />
                        JSONL files available
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-gray-400">
                        <XCircle className="w-3 h-3" />
                        No JSONL files
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <button
                onClick={handleIngestCalendar}
                disabled={importing === 'calendar' || !status?.ost_jsonl_available}
                className="btn btn-secondary py-2 text-sm"
              >
                {importing === 'calendar' ? (
                  <RefreshCw className="w-4 h-4 animate-spin" />
                ) : (
                  'Import'
                )}
              </button>
            </div>

            {/* IMAP */}
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-purple-100 flex items-center justify-center text-purple-600">
                  <Mail className="w-5 h-5" />
                </div>
                <div>
                  <p className="font-medium text-gray-900">IMAP Email</p>
                  <p className="text-xs text-gray-500">
                    {status?.imap_configured ? (
                      <span className="flex items-center gap-1 text-green-600">
                        <CheckCircle className="w-3 h-3" />
                        Configured
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-gray-400">
                        <XCircle className="w-3 h-3" />
                        Not configured
                      </span>
                    )}
                  </p>
                </div>
              </div>
              <button disabled className="btn btn-secondary py-2 text-sm opacity-50">
                Coming soon
              </button>
            </div>
          </div>
        </div>

        {/* Actions */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">
            Actions
          </h2>

          <div className="space-y-3">
            <button
              onClick={handleRecomputeScores}
              disabled={importing === 'scores'}
              className="btn btn-secondary w-full justify-start"
            >
              {importing === 'scores' ? (
                <RefreshCw className="w-5 h-5 mr-3 animate-spin" />
              ) : (
                <Database className="w-5 h-5 mr-3" />
              )}
              Recompute All Scores
            </button>
          </div>
        </div>

        {/* Import Status */}
        {status && (status.last_linkedin_import || status.last_ost_import) && (
          <div className="card p-4">
            <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-3">
              Last Imports
            </h2>
            <div className="text-sm text-gray-500 space-y-1">
              {status.last_linkedin_import && (
                <p>LinkedIn: {new Date(status.last_linkedin_import).toLocaleString()}</p>
              )}
              {status.last_ost_import && (
                <p>Calendar: {new Date(status.last_ost_import).toLocaleString()}</p>
              )}
              {status.last_imap_sync && (
                <p>IMAP: {new Date(status.last_imap_sync).toLocaleString()}</p>
              )}
            </div>
          </div>
        )}

        {/* Account */}
        <div className="card p-4">
          <h2 className="text-sm font-semibold text-gray-900 uppercase tracking-wide mb-4">
            Account
          </h2>
          <button
            onClick={handleLogout}
            className="btn btn-secondary w-full justify-start text-red-600 hover:text-red-700 hover:bg-red-50"
          >
            <LogOut className="w-5 h-5 mr-3" />
            Sign Out
          </button>
        </div>

        {/* Version */}
        <p className="text-center text-xs text-gray-400 py-4">
          LinkedIn CRM v1.0.0
        </p>
      </div>
    </div>
  );
}
