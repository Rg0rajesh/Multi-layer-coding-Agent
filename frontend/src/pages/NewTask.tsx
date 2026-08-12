// frontend/src/pages/NewTask.tsx
// Prompt-first task creation — describe what you want, Guardrail/Planner
// take it from there. Language is guessed from the prompt itself; there's
// a manual override chip if the guess is wrong, but nobody has to pick
// from a dropdown before they've even finished typing.
import { useMemo, useRef, useState, type FormEvent, type KeyboardEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Sidebar } from "../components";
import { tasksApi } from "../api";
import { ApiError } from "../api/client";
import type { Priority } from "../types";
import "./NewTask.css";

const STARTER_PROMPTS = [
  "Build a REST API with JWT auth in FastAPI",
  "Add a rate limiter middleware to my Express app",
  "Write a CLI tool that batch-renames files in Go",
  "Create a React dashboard with a sortable data table",
  "Set up a Postgres migration for a new orders table",
];

// Word-boundary matching so "django" doesn't trip the "go" hint and
// "javascript" doesn't trip the "java" hint.
const LANGUAGE_HINTS: [RegExp, string][] = [
  [/\b(typescript|react|next\.?js|vue|angular|nestjs)\b/i, "typescript"],
  [/\b(javascript|node(\.js)?|express)\b/i, "javascript"],
  [/\b(python|django|flask|fastapi)\b/i, "python"],
  [/\b(golang|go)\b/i, "go"],
  [/\b(rust|cargo)\b/i, "rust"],
  [/\b(java|spring(boot)?)\b/i, "java"],
];

function guessLanguage(prompt: string): string | undefined {
  const match = LANGUAGE_HINTS.find(([pattern]) => pattern.test(prompt));
  return match?.[1];
}

function deriveTitle(prompt: string): string {
  const firstLine = prompt.trim().split("\n")[0];
  return firstLine.length > 60 ? `${firstLine.slice(0, 57)}...` : firstLine;
}

export default function NewTask() {
  const navigate = useNavigate();
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const [prompt, setPrompt] = useState("");
  const [priority, setPriority] = useState<Priority>("medium");
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const detectedLanguage = useMemo(() => guessLanguage(prompt), [prompt]);

  function autoGrow() {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, 320)}px`;
  }

  function usePrompt(text: string) {
    setPrompt(text);
    setFormError(null);
    requestAnimationFrame(() => {
      textareaRef.current?.focus();
      autoGrow();
    });
  }

  async function submit() {
    const trimmed = prompt.trim();
    if (!trimmed) {
      setFormError("Tell Agent X what to build first.");
      return;
    }

    setIsSubmitting(true);
    setFormError(null);

    try {
      const task = await tasksApi.create({
        title: deriveTitle(trimmed),
        description: trimmed,
        language: detectedLanguage,
        priority,
        max_exec_minutes: 15,
      });
      navigate(`/monitor?task=${task.id}`);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Couldn't start the task — try again.");
      setIsSubmitting(false);
    }
  }

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    submit();
  }

  function handleKeyDown(event: KeyboardEvent<HTMLTextAreaElement>) {
    // Cmd/Ctrl+Enter submits — Enter alone stays a newline, same as most
    // prompt boxes people are already used to.
    if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
      event.preventDefault();
      submit();
    }
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main new-task">
        <div className="new-task__hero">
          <h1 className="new-task__heading">What do you want to build?</h1>
          <p className="new-task__subheading">
            Describe it in plain English — Guardrail screens it, Planner breaks it down, and Coder picks a
            stack based on what you write.
          </p>

          <form className="new-task__composer" onSubmit={handleSubmit}>
            <textarea
              ref={textareaRef}
              className="new-task__textarea"
              placeholder="Build a JWT refresh endpoint in FastAPI, or a React table with sorting and pagination..."
              value={prompt}
              onChange={(e) => {
                setPrompt(e.target.value);
                setFormError(null);
                autoGrow();
              }}
              onKeyDown={handleKeyDown}
              rows={1}
              autoFocus
            />

            <div className="new-task__composer-footer">
              <div className="new-task__composer-left">
                <PriorityToggle value={priority} onChange={setPriority} />
                {detectedLanguage && (
                  <span className="new-task__detected-lang" title="Detected from your prompt">
                    {detectedLanguage}
                  </span>
                )}
              </div>

              <button
                type="submit"
                className="new-task__submit"
                disabled={isSubmitting || !prompt.trim()}
                aria-label="Start task"
              >
                {isSubmitting ? <Spinner /> : <ArrowIcon />}
              </button>
            </div>
          </form>

          {formError && <p className="new-task__error">{formError}</p>}

          <div className="new-task__chips">
            {STARTER_PROMPTS.map((starter) => (
              <button
                key={starter}
                type="button"
                className="new-task__chip"
                onClick={() => usePrompt(starter)}
              >
                {starter}
              </button>
            ))}
          </div>
        </div>
      </main>
    </div>
  );
}

function PriorityToggle({ value, onChange }: { value: Priority; onChange: (p: Priority) => void }) {
  const options: Priority[] = ["low", "medium", "high"];
  return (
    <div className="priority-toggle" role="radiogroup" aria-label="Priority">
      {options.map((option) => (
        <button
          key={option}
          type="button"
          role="radio"
          aria-checked={value === option}
          className={`priority-toggle__option${value === option ? " is-active" : ""}`}
          onClick={() => onChange(option)}
        >
          {option}
        </button>
      ))}
    </div>
  );
}

function ArrowIcon() {
  return (
    <svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M8 13V3M3 7l5-5 5 5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function Spinner() {
  return (
    <svg className="spinner" viewBox="0 0 24 24" width="16" height="16" aria-hidden="true">
      <circle cx="12" cy="12" r="10" fill="none" strokeWidth="2.5" strokeDasharray="60" strokeLinecap="round" />
    </svg>
  );
}