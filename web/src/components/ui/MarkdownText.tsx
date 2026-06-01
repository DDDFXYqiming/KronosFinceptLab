"use client";

import type { ReactNode } from "react";

interface MarkdownTextProps {
  text: string;
  className?: string;
}

const LINK_PATTERN = /^\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)$/i;

function renderInlineMarkdown(text: string, keyPrefix: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const tokenPattern = /(\*\*[^*\n]+\*\*|__[^_\n]+__|==[^=\n]+==|`[^`\n]+`|\[[^\]\n]+\]\(https?:\/\/[^)\s\n]+\))/gi;
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  while ((match = tokenPattern.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index));
    }

    const raw = match[0];
    const key = `${keyPrefix}-${match.index}`;
    const linkMatch = raw.match(LINK_PATTERN);

    if (raw.startsWith("**") && raw.endsWith("**")) {
      nodes.push(
        <strong key={key} className="font-semibold text-foreground">
          {raw.slice(2, -2)}
        </strong>
      );
    } else if (raw.startsWith("__") && raw.endsWith("__")) {
      nodes.push(
        <span key={key} className="underline decoration-primary/50 underline-offset-4 text-foreground">
          {raw.slice(2, -2)}
        </span>
      );
    } else if (raw.startsWith("==") && raw.endsWith("==")) {
      nodes.push(
        <mark key={key} className="rounded bg-primary/10 px-1 text-foreground">
          {raw.slice(2, -2)}
        </mark>
      );
    } else if (raw.startsWith("`") && raw.endsWith("`")) {
      nodes.push(
        <code key={key} className="rounded bg-muted px-1 py-0.5 font-mono text-[0.92em] text-foreground">
          {raw.slice(1, -1)}
        </code>
      );
    } else if (linkMatch) {
      nodes.push(
        <a
          key={key}
          href={linkMatch[2]}
          target="_blank"
          rel="noreferrer"
          className="font-medium text-primary underline decoration-primary/40 underline-offset-4"
        >
          {linkMatch[1]}
        </a>
      );
    } else {
      nodes.push(raw);
    }

    lastIndex = match.index + raw.length;
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex));
  }

  return nodes;
}

export function MarkdownText({ text, className = "" }: MarkdownTextProps) {
  const lines = text.split(/\r?\n/);

  return (
    <div className={`space-y-2 text-sm leading-relaxed text-muted-foreground ${className}`}>
      {lines.map((line, index) => {
        const trimmed = line.trim();
        if (!trimmed) return <div key={`blank-${index}`} className="h-1" />;

        const unordered = trimmed.match(/^[-*]\s+(.+)$/);
        if (unordered) {
          return (
            <div key={`ul-${index}`} className="flex gap-2">
              <span className="mt-[0.65em] h-1.5 w-1.5 shrink-0 rounded-full bg-primary/70" />
              <p className="min-w-0 break-words">{renderInlineMarkdown(unordered[1], `ul-${index}`)}</p>
            </div>
          );
        }

        const ordered = trimmed.match(/^(\d+)[.)]\s+(.+)$/);
        if (ordered) {
          return (
            <div key={`ol-${index}`} className="flex gap-2">
              <span className="shrink-0 font-mono text-xs font-semibold text-primary">{ordered[1]}.</span>
              <p className="min-w-0 break-words">{renderInlineMarkdown(ordered[2], `ol-${index}`)}</p>
            </div>
          );
        }

        return (
          <p key={`p-${index}`} className="break-words">
            {renderInlineMarkdown(trimmed, `p-${index}`)}
          </p>
        );
      })}
    </div>
  );
}
