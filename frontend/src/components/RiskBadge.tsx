interface RiskBadgeProps {
  flag: string;
}

export default function RiskBadge({ flag }: RiskBadgeProps) {
  // Determine severity based on flag content
  const isHighRisk = flag.toLowerCase().includes('hallucination') ||
    flag.toLowerCase().includes('fabricated') ||
    flag.toLowerCase().includes('unverified');

  const isMediumRisk = flag.toLowerCase().includes('missing') ||
    flag.toLowerCase().includes('generic');

  const colorClass = isHighRisk
    ? 'bg-red-100 text-red-800 border-red-200'
    : isMediumRisk
    ? 'bg-orange-100 text-orange-800 border-orange-200'
    : 'bg-yellow-100 text-yellow-800 border-yellow-200';

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${colorClass}`}
    >
      {flag}
    </span>
  );
}
