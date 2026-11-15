// Tiny dependency-free sparkline (many per screen, so no Recharts here).
export default function Spark({ data, up, width = 72, height = 26 }) {
  if (!data || data.length < 2) return <div style={{ width, height }} />
  const min = Math.min(...data), max = Math.max(...data), r = max - min || 1
  const pts = data.map((v, i) => `${(i / (data.length - 1)) * width},${height - 2 - ((v - min) / r) * (height - 4)}`).join(' ')
  const color = up === undefined ? 'rgb(var(--muted))' : up ? 'rgb(var(--up))' : 'rgb(var(--down))'
  return <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} aria-hidden="true"><polyline points={pts} fill="none" stroke={color} strokeWidth="1.6" strokeLinejoin="round" strokeLinecap="round" /></svg>
}
