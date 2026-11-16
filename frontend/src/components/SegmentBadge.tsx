import type { Segment } from "../types";

export function SegmentBadge({ segment }: { segment: Segment | null }) {
  if (!segment) return <span className="badge badge-none">unscored</span>;
  return <span className={`badge badge-${segment}`}>{segment}</span>;
}
