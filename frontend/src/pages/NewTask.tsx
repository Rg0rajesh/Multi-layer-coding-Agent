// frontend/src/pages/NewTask.tsx
// Task creation form. On submit, POST /tasks kicks the Celery job off
// server-side (routers/tasks.py already handles that) — this page's only
// job is collecting a well-formed payload and routing to Live Monitor
// once the task exists.
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { Sidebar } from "../components";
import { tasksApi } from "../api";
import { ApiError } from "../api/client";
import type { Priority } from "../types";
import "./NewTask.css";

const LANGUAGES = ["python", "typescript", "javascript", "go", "rust", "java"];
const PRIORITIES: Priority[] = ["low", "medium", "high"];

export default function NewTask() {
  const navigate = useNavigate();

  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [language, setLanguage] = useState("python");
  const [priority, setPriority] = useState<Priority>("medium");
  const [gitIntegration, setGitIntegration] = useState(false);
  const [maxMinutes, setMaxMinutes] = useState(10);

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!title.trim()) {
      setFormError("Give the task a title first.");
      return;
    }

    setIsSubmitting(true);
    setFormError(null);

    try {
      const task = await tasksApi.create({
        title: title.trim(),
        description: description.trim() || undefined,
        language,
        priority,
        git_integration: gitIntegration,
        max_exec_minutes: maxMinutes,
      });
      navigate(`/monitor?task=${task.id}`);
    } catch (err) {
      setFormError(err instanceof ApiError ? err.message : "Couldn't create the task — try again.");
      setIsSubmitting(false);
    }
  }

  return (
    <div className="app-shell">
      <Sidebar />
      <main className="app-main">
        <div className="page-header">
          <div>
            <h1>New Task</h1>
            <p className="page-header__meta">Guardrail screens it, Planner breaks it down, you approve the plan.</p>
          </div>
        </div>

        <form className="new-task-form card" onSubmit={handleSubmit}>
          <label className="new-task-field">
            <span>Title</span>
            <input
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Build a JWT refresh endpoint"
              autoFocus
            />
          </label>

          <label className="new-task-field">
            <span>Description</span>
            <textarea
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              placeholder="What should the Coder actually build? The more specific, the fewer re-plans."
              rows={5}
            />
          </label>

          <div className="new-task-row">
            <label className="new-task-field">
              <span>Language</span>
              <select value={language} onChange={(e) => setLanguage(e.target.value)}>
                {LANGUAGES.map((lang) => (
                  <option key={lang} value={lang}>
                    {lang}
                  </option>
                ))}
              </select>
            </label>

            <label className="new-task-field">
              <span>Priority</span>
              <select value={priority} onChange={(e) => setPriority(e.target.value as Priority)}>
                {PRIORITIES.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>

            <label className="new-task-field">
              <span>Time budget (min)</span>
              <input
                type="number"
                min={1}
                max={120}
                value={maxMinutes}
                onChange={(e) => setMaxMinutes(Number(e.target.value))}
              />
            </label>
          </div>

          <label className="new-task-checkbox">
            <input type="checkbox" checked={gitIntegration} onChange={(e) => setGitIntegration(e.target.checked)} />
            <span>Enable Git integration for this task</span>
          </label>

          {formError && <p className="new-task-form__error">{formError}</p>}

          <button type="submit" className="btn btn--fill" disabled={isSubmitting}>
            {isSubmitting ? "Starting…" : "Start Task"}
          </button>
        </form>
      </main>
    </div>
  );
}
