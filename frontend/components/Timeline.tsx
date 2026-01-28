'use client';

import { Interaction } from '@/lib/api';
import { cn, getInteractionIcon, getInteractionLabel } from '@/lib/utils';
import { useMeetingDate } from '@/lib/useRelativeDate';

interface TimelineProps {
  interactions: Interaction[];
}

export function Timeline({ interactions }: TimelineProps) {
  if (interactions.length === 0) {
    return (
      <div className="empty-state">
        <p className="text-gray-500">No interactions yet</p>
      </div>
    );
  }

  return (
    <div className="space-y-0">
      {interactions.map((interaction) => (
        <TimelineItem key={interaction.id} interaction={interaction} />
      ))}
    </div>
  );
}

function TimelineItem({ interaction }: { interaction: Interaction }) {
  const formattedDate = useMeetingDate(interaction.occurred_at);

  const dotClass = cn('timeline-dot', {
    'timeline-dot-meeting': interaction.kind === 'meeting',
    'timeline-dot-email-in': interaction.kind === 'email_in',
    'timeline-dot-email-out': interaction.kind === 'email_out',
  });

  return (
    <div className="timeline-item">
      <div className={dotClass} />
      <div className="pb-2">
        <div className="flex items-center gap-2 text-sm">
          <span>{getInteractionIcon(interaction.kind)}</span>
          <span className="font-medium text-gray-900">
            {getInteractionLabel(interaction.kind)}
          </span>
          {!interaction.is_meaningful && (
            <span className="text-xs text-gray-400">(auto)</span>
          )}
        </div>

        <p className="text-xs text-gray-500 mt-0.5">
          {formattedDate}
        </p>

        {interaction.subject && (
          <p className="text-sm text-gray-700 mt-1 line-clamp-2">
            {interaction.subject}
          </p>
        )}

        {interaction.snippet && (
          <p className="text-sm text-gray-500 mt-1 line-clamp-2 italic">
            "{interaction.snippet}"
          </p>
        )}
      </div>
    </div>
  );
}
