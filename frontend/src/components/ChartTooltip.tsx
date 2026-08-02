interface ChartTooltipPoint {
  name: string;
  value: number;
  color: string;
}

interface ChartTooltipProps {
  active?: boolean;
  payload?: ChartTooltipPoint[];
  label?: string;
  /** Decimal places to format each value to (e.g. 1 for 0-10 scores). Omit for raw integers like counts. */
  decimals?: number;
}

/** Shared recharts <Tooltip content={...}> renderer — used by Dashboard, Analytics, and Admin charts. */
export function ChartTooltip({ active, payload, label, decimals }: ChartTooltipProps) {
  if (!active || !payload?.length) return null;
  return (
    <div
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border-strong)',
        borderRadius: 8,
        padding: '0.6rem 0.9rem',
        fontSize: '0.82rem',
        boxShadow: 'var(--shadow)',
      }}
    >
      <p style={{ margin: '0 0 0.4rem', color: 'var(--muted)', fontWeight: 600 }}>{label}</p>
      {payload.map((p) => (
        <p key={p.name} style={{ margin: '0.15rem 0', color: p.color }}>
          {p.name}: <strong>{decimals != null ? p.value?.toFixed(decimals) : p.value}</strong>
        </p>
      ))}
    </div>
  );
}
