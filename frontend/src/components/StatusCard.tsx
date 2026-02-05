interface StatusCardProps {
  label: string;
  value: number;
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'gray';
  subtext?: string;
  onClick?: () => void;
}

export default function StatusCard({ label, value, color = 'blue', subtext, onClick }: StatusCardProps) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200 hover:bg-blue-100',
    green: 'bg-green-50 text-green-700 border-green-200 hover:bg-green-100',
    yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200 hover:bg-yellow-100',
    red: 'bg-red-50 text-red-700 border-red-200 hover:bg-red-100',
    gray: 'bg-gray-50 text-gray-700 border-gray-200 hover:bg-gray-100',
  };

  const baseClasses = `rounded-lg border p-4 ${colorClasses[color]}`;
  const clickableClasses = onClick ? 'cursor-pointer transition-colors' : '';

  return (
    <div
      className={`${baseClasses} ${clickableClasses}`}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => e.key === 'Enter' && onClick() : undefined}
    >
      <p className="text-sm font-medium opacity-80">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      {subtext && <p className="text-xs opacity-70 mt-1">{subtext}</p>}
    </div>
  );
}
