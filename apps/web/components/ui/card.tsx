import type { HTMLAttributes, ReactNode } from "react";

type CardTone = "default" | "muted";

type CardProps = HTMLAttributes<HTMLElement> & {
  as?: "article" | "section" | "div";
  eyebrow?: ReactNode;
  title?: ReactNode;
  actions?: ReactNode;
  footer?: ReactNode;
  tone?: CardTone;
};

export function Card({
  as: Component = "article",
  eyebrow,
  title,
  actions,
  footer,
  tone = "default",
  className,
  children,
  ...props
}: CardProps) {
  const classes = ["ui-card", tone === "muted" ? "ui-card-muted" : "", className]
    .filter(Boolean)
    .join(" ");

  return (
    <Component className={classes} {...props}>
      {eyebrow || title || actions ? (
        <div className="ui-card-head">
          <div>
            {eyebrow ? <div className="ui-card-eyebrow">{eyebrow}</div> : null}
            {title ? <h2 className="ui-card-title">{title}</h2> : null}
          </div>
          {actions ? <div className="ui-card-actions">{actions}</div> : null}
        </div>
      ) : null}
      <div className="ui-card-body">{children}</div>
      {footer ? <div className="ui-card-footer">{footer}</div> : null}
    </Component>
  );
}
