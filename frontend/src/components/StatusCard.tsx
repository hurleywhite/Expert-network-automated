interface StatusCardProps {
  label: string;
  value: number;
  color?: 'blue' | 'green' | 'yellow' | 'red' | 'gray';
  subtext?: string;
}

export default function StatusCard({ label, value, color = 'blue', subtext }: StatusCardProps) {
  const colorClasses = {
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    green: 'bg-green-50 text-green-700 border-green-200',
    yellow: 'bg-yellow-50 text-yellow-700 border-yellow-200',
    red: 'bg-red-50 text-red-700 border-red-200',
    gray: 'bg-gray-50 text-gray-700 border-gray-200',
  };

  return (
    <div className={`rounded-lg border p-4 ${colorClasses[color]}`}>
      <p className="text-sm font-medium opacity-80">{label}</p>
      <p className="text-2xl font-bold mt-1">{value}</p>
      {subtext && <p className="text-xs opacity-70 mt-1">{subtext}</p>}
    </div>
  );
}
