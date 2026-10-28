
export default function Logo({ size = 40 }: { size?: number }) {
  return <img src="/logo.png" alt="INNquietus" width={size} height={size} style={{ display: 'block', objectFit: 'contain' }} />
}
