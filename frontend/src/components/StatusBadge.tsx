const statusColors: Record<string, string> = {
  sourced: 'bg-gray-100 text-gray-700',
  screened: 'bg-blue-100 text-blue-700',
  shortlisted: 'bg-indigo-100 text-indigo-700',
  scheduled: 'bg-yellow-100 text-yellow-700',
  completed: 'bg-green-100 text-green-700',
  rejected: 'bg-red-100 text-red-700',
  available: 'bg-green-100 text-green-700',
  // LinkedIn statuses
  pending: 'bg-gray-100 text-gray-700',
  connection_sent: 'bg-blue-100 text-blue-700',
  connected: 'bg-green-100 text-green-700',
  message_sent: 'bg-indigo-100 text-indigo-700',
  replied: 'bg-emerald-100 text-emerald-700',
  failed: 'bg-red-100 text-red-700',
};

const statusLabels: Record<string, string> = {
  sourced: 'Sourced',
  screened: 'Screened',
  shortlisted: 'Shortlisted',
  scheduled: 'Scheduled',
  completed: 'Completed',
  rejected: 'Rejected',
  available: 'Available',
  pending: 'Pending',
  connection_sent: 'Connection Sent',
  connected: 'Connected',
  message_sent: 'Message Sent',
  replied: 'Replied',
  failed: 'Failed',
};

export default function StatusBadge({ status }: { status: string }) {
  const color = statusColors[status] || 'bg-gray-100 text-gray-700';
  const label = statusLabels[status] || status;

  return (
    <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${color}`}>
      {label}
    </span>
  );
}
