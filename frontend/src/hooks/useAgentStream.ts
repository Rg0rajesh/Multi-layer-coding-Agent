// frontend/src/hooks/useAgentStream.ts
import { useEffect, useState } from "react";
import { logsApi } from "../api";
import { useWebSocket } from "./useWebSocket";

export const AGENT_COLORS: Record<string, string> = {
  PLANNER: "#E8FF47", CODER: "#00C896", TESTER: "#FF6B35", REVIEWER: "#FF3C3C",
  SECURITY: "#FF3C3C", HUMAN: "#FFFFFF", SYSTEM: "#888888", GUARDRAIL: "#FF3C3C",
  IDENTITY_BROKER: "#E8FF47", GROUNDING: "#00C896", CONTEXT_CURATOR: "#888888",
};

interface RawLogMessage {
  type: "log";
  agent: string;
  level: string;
  icon: string;
  message: string;
  timestamp: string;
}

interface RawEventMessage {
  type: "event";
  agent: string;
  keys_updated: string[];
  timestamp: string;
}

type RawMessage = RawLogMessage | RawEventMessage;

export interface AgentLogLine {
  id: string;
  agent: string;
  level: string;
  icon: string;
  message: string;
  timestamp: string;
  color: string;
}

export interface AgentStatus {
  agent: string;
  lastSeenAt: string;
  lastLevel: string;
}

const MAX_LOG_LINES = 500;

export function useAgentStream(taskId: string | null) {
  const { status, lastMessage } = useWebSocket<RawMessage>(taskId);
  const [lines, setLines] = useState<AgentLogLine[]>([]);
  const [agentStatuses, setAgentStatuses] = useState<Record<string, AgentStatus>>({});

  useEffect(() => {
    if (!taskId) {
      setLines([]);
      return;
    }

    let cancelled = false;
    logsApi.list(taskId, { page: 1, page_size: MAX_LOG_LINES })
      .then((response) => {
        if (cancelled) return;
        const history = [...(response.items ?? [])].reverse().map((entry) => ({
          id: `history-${entry.id}`,
          agent: entry.agent_name,
          level: entry.log_level,
          icon: entry.prefix_icon ?? "",
          message: entry.message,
          timestamp: entry.created_at,
          color: AGENT_COLORS[entry.agent_name] ?? "#FFFFFF",
        }));
        setLines(history.slice(-MAX_LOG_LINES));
      })
      .catch(() => {
        if (!cancelled) setLines([]);
      });

    return () => { cancelled = true; };
  }, [taskId]);

  useEffect(() => {
    if (!lastMessage) return;

    setAgentStatuses((prev) => ({
      ...prev,
      [lastMessage.agent]: {
        agent: lastMessage.agent,
        lastSeenAt: lastMessage.timestamp,
        lastLevel: lastMessage.type === "log" ? lastMessage.level : prev[lastMessage.agent]?.lastLevel ?? "INFO",
      },
    }));

    if (lastMessage.type !== "log") return;

    setLines((prev) => {
      const next = [
        ...prev,
        {
          id: `${lastMessage.timestamp}-${prev.length}`,
          agent: lastMessage.agent,
          level: lastMessage.level,
          icon: lastMessage.icon,
          message: lastMessage.message,
          timestamp: lastMessage.timestamp,
          color: AGENT_COLORS[lastMessage.agent] ?? "#FFFFFF",
        },
      ];
      return next.length > MAX_LOG_LINES ? next.slice(next.length - MAX_LOG_LINES) : next;
    });
  }, [lastMessage]);

  return { connectionStatus: status, lines, agentStatuses };
}
