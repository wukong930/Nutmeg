import type { ReactNode } from "react";

type TooltipProps = {
  label: ReactNode;
  children: ReactNode;
};

export function Tooltip({ label, children }: TooltipProps) {
  return (
    <span className="ui-tooltip">
      <span className="ui-tooltip-trigger" tabIndex={0}>
        {children}
      </span>
      <span className="ui-tooltip-content" role="tooltip">
        {label}
      </span>
    </span>
  );
}
