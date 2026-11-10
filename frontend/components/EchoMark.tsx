/** The three echo curves from the Echofy logo, bulging right. */
export default function EchoMark({
  color = "#fff",
  className,
}: {
  color?: string;
  className?: string;
}) {
  const arcs = [
    "M36 38 A16 16 0 0 1 36 62",
    "M48 28 A28 28 0 0 1 48 72",
    "M60 18 A42 42 0 0 1 60 82",
  ];
  return (
    <svg viewBox="0 0 100 100" className={className} aria-hidden="true" fill="none" stroke={color} strokeWidth="8" strokeLinecap="round">
      {arcs.map((d, i) => (
        <path key={i} d={d} />
      ))}
    </svg>
  );
}
