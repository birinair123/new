'use client';

import { PersonScore } from '@/lib/api';

interface ScoreBreakdownProps {
  score: PersonScore;
}

export function ScoreBreakdown({ score }: ScoreBreakdownProps) {
  const { score_breakdown: breakdown } = score;

  const components = [
    {
      name: 'Recency',
      value: breakdown.recency,
      max: breakdown.recency_max,
      reason: breakdown.recency_reason,
      color: 'bg-blue-500',
    },
    {
      name: 'Frequency',
      value: breakdown.frequency,
      max: breakdown.frequency_max,
      reason: breakdown.frequency_reason,
      color: 'bg-green-500',
    },
    {
      name: 'Bidirectionality',
      value: breakdown.bidirectionality,
      max: breakdown.bidirectionality_max,
      reason: breakdown.bidirectionality_reason,
      color: 'bg-purple-500',
    },
    {
      name: 'Meetings',
      value: breakdown.meetings,
      max: breakdown.meetings_max,
      reason: breakdown.meetings_reason,
      color: 'bg-orange-500',
    },
    {
      name: 'Context',
      value: breakdown.context,
      max: breakdown.context_max,
      reason: breakdown.context_reason,
      color: 'bg-pink-500',
    },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-gray-900">Connection Strength</h3>
        <div className="text-3xl font-bold text-primary-600">{score.score_total}</div>
      </div>

      <div className="space-y-3">
        {components.map((component) => (
          <div key={component.name} className="space-y-1">
            <div className="flex items-center justify-between text-sm">
              <span className="text-gray-700">{component.name}</span>
              <span className="text-gray-500">
                {component.value}/{component.max}
              </span>
            </div>
            <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
              <div
                className={`h-full ${component.color} rounded-full transition-all`}
                style={{ width: `${(component.value / component.max) * 100}%` }}
              />
            </div>
            <p className="text-xs text-gray-500">{component.reason}</p>
          </div>
        ))}
      </div>

      <div className="pt-2 border-t border-gray-100">
        <p className="text-xs text-gray-400">
          {score.interaction_count} total interactions
        </p>
      </div>
    </div>
  );
}
