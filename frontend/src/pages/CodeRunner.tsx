import { useEffect, useState } from "react";
import { Sidebar } from "../components";
import { tasksApi } from "../api";
import type { CodeRunResult } from "../api";
import "./CodeRunner.css";

const FALLBACK_LANGUAGES = ["python", "java", "javascript", "typescript", "c", "c++", "go", "rust", "php", "ruby", "html", "css"];

const STARTERS: Record<string, string> = {
  python: 'print("Hello, AGENTX!")',
  java: 'public class Main {\n    public static void main(String[] args) {\n        System.out.println("Hello, AGENTX!");\n    }\n}',
  javascript: 'console.log("Hello, AGENTX!");',
  typescript: 'const message: string = "Hello, AGENTX!";\nconsole.log(message);',
  c: '#include <stdio.h>\nint main(void) { printf("Hello, AGENTX!\\n"); return 0; }',
  "c++": '#include <iostream>\nint main() { std::cout << "Hello, AGENTX!\\n"; }',
  go: 'package main\nimport "fmt"\nfunc main() { fmt.Println("Hello, AGENTX!") }',
  rust: 'fn main() { println!("Hello, AGENTX!"); }',
  php: '<?php echo "Hello, AGENTX!\\n";',
  ruby: 'puts "Hello, AGENTX!"',
  html: '<!doctype html>\n<html><body><h1>Hello, AGENTX!</h1></body></html>',
  css: 'body { margin: 0; font-family: sans-serif; }',
};

export default function CodeRunner() {
  const [language, setLanguage] = useState("python");
  const [code, setCode] = useState(STARTERS.python);
  const [stdin, setStdin] = useState("");
  const [result, setResult] = useState<CodeRunResult | null>(null);
  const [running, setRunning] = useState(false);
  const [languages, setLanguages] = useState(FALLBACK_LANGUAGES);

  useEffect(() => { tasksApi.runtimes().then(({ runtimes }) => setLanguages(runtimes.map((r) => r.language))).catch(() => {}); }, []);

  function changeLanguage(next: string) { setLanguage(next); setCode(STARTERS[next] ?? ""); setResult(null); }
  async function run() {
    setRunning(true); setResult(null);
    try { setResult(await tasksApi.runCode({ language, code, stdin })); }
    catch (error) { setResult({ language, version: "", compile: {}, run: {}, stdout: "", stderr: error instanceof Error ? error.message : "Execution failed", output: "", exit_code: 1, signal: null, success: false }); }
    finally { setRunning(false); }
  }

  return <div className="app-shell"><Sidebar /><main className="app-main code-runner">
    <div className="page-header"><div><h1>Code Runner</h1><p className="page-header__meta">Run code directly in an isolated execution environment.</p></div><button className="btn btn--primary" type="button" onClick={run} disabled={running}>{running ? "Running…" : "Run Code"}</button></div>
    <div className="code-runner__toolbar"><select value={language} onChange={(e) => changeLanguage(e.target.value)}>{languages.map((lang) => <option key={lang} value={lang}>{lang}</option>)}</select><span>Isolated runtime • network disabled • time and memory limited</span></div>
    <div className="code-runner__layout"><section className="card code-runner__editor"><textarea value={code} onChange={(e) => setCode(e.target.value)} spellCheck={false} aria-label="Source code" /></section><aside className="card code-runner__side"><label>Standard input<textarea value={stdin} onChange={(e) => setStdin(e.target.value)} placeholder="Input passed to the program" /></label><div className={`code-runner__result ${result?.success ? "is-success" : result ? "is-error" : ""}`}><strong>{result ? (result.success ? "Execution successful" : "Execution failed") : "Output"}</strong><pre>{result ? (result.output || result.stderr || "No output") : "Run your code to see stdout and errors here."}</pre></div></aside></div>
  </main></div>;
}
