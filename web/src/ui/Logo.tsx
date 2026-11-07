export function LogoMark({ size = 40 }: { size?: number }) {
  return (
    <img src="/anylo-mark.png" width={size} height={size} alt="" className="rounded-[22%]" style={{ width: size, height: size }} />
  );
}

export function Logo({ size = 36, onDark = false }: { size?: number; onDark?: boolean }) {
  return (
    <span className="inline-flex items-center gap-2.5" aria-label="Anylo">
      <LogoMark size={size} />
      <span
        className={`font-extrabold tracking-tight ${onDark ? "text-white" : "text-text"}`}
        style={{ fontSize: size * 0.72, letterSpacing: "-0.03em" }}
      >
        anylo
      </span>
    </span>
  );
}
