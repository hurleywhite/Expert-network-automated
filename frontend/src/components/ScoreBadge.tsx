interface ScoreBadgeProps {
  score: number;
}

export default function ScoreBadge({ score }: ScoreBadgeProps) {
  let colorClass = 'bg-gray-100 text-gray-800';

  if (score >= 70) {
    colorClass = 'bg-green-100 text-green-800';
  } else if (score >= 50) {
    colorClass = 'bg-blue-100 text-blue-800';
  } else if (score >= 40) {
    colorClass = 'bg-yellow-100 text-yellow-800';
  }

  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${colorClass}`}
    >
      Score: {score}
    </span>
  );
}
