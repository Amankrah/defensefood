import Image from "next/image";

interface LogoMarkProps {
  size?: number;
  className?: string;
  /** Set when the mark appears without adjacent "DefenseFood" text. */
  labeled?: boolean;
}

/** DefenseFood shield mark — use beside the wordmark or standalone. */
export default function LogoMark({
  size = 36,
  className = "",
  labeled = false,
}: LogoMarkProps) {
  return (
    <Image
      src="/logo.png"
      alt={labeled ? "DefenseFood" : ""}
      width={size}
      height={size}
      className={`shrink-0 rounded-xl object-cover shadow-lg shadow-blue-600/20 ${className}`}
      priority
    />
  );
}
