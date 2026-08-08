// frontend/src/hooks/useTypewriter.ts
import { useEffect, useRef, useState } from "react";

interface UseTypewriterOptions {
  /** ms per character while a line is being typed out */
  typingSpeed?: number;
  /** ms to hold a finished line before starting the next one */
  holdTime?: number;
  /** loop back to the first line once the list is exhausted */
  loop?: boolean;
}

interface UseTypewriterResult {
  /** Lines that have already finished typing */
  completedLines: string[];
  /** The line currently being typed, character by character */
  currentText: string;
}

/**
 * Types out a list of strings one character at a time, like a terminal log
 * stream. Pulled into its own hook because the Login page and (eventually)
 * Live Monitor both want the same "typewriter log" effect, and the previous
 * version had this logic copy-pasted inline.
 *
 * `lines` should be a stable reference — module-level constant or memoized
 * array. Passing a new array literal on every render restarts the effect
 * before it ever finishes typing anything.
 */
export function useTypewriter(lines: string[], options: UseTypewriterOptions = {}): UseTypewriterResult {
  const { typingSpeed = 28, holdTime = 1400, loop = true } = options;

  const [completedLines, setCompletedLines] = useState<string[]>([]);
  const [currentText, setCurrentText] = useState("");

  const lineIndex = useRef(0);
  const charIndex = useRef(0);

  useEffect(() => {
    if (lines.length === 0) return;

    let timeoutId: ReturnType<typeof setTimeout>;

    const typeNextChar = () => {
      const line = lines[lineIndex.current];

      if (charIndex.current < line.length) {
        charIndex.current += 1;
        setCurrentText(line.slice(0, charIndex.current));
        timeoutId = setTimeout(typeNextChar, typingSpeed);
        return;
      }

      // Line's fully typed — hold it a beat, then either move to the next
      // line or wrap back to the start if looping.
      timeoutId = setTimeout(() => {
        const next = lineIndex.current + 1;

        if (next >= lines.length) {
          if (!loop) return;
          lineIndex.current = 0;
          setCompletedLines([]);
        } else {
          lineIndex.current = next;
          setCompletedLines((prev) => [...prev, line]);
        }

        charIndex.current = 0;
        setCurrentText("");
        timeoutId = setTimeout(typeNextChar, typingSpeed);
      }, holdTime);
    };

    timeoutId = setTimeout(typeNextChar, typingSpeed);
    return () => clearTimeout(timeoutId);
  }, [lines, typingSpeed, holdTime, loop]);

  return { completedLines, currentText };
}