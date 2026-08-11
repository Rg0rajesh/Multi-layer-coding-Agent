// frontend/src/hooks/useAgentStream.ts
import { useMemo, useState } from "react";
import { useWebSocket } from "./useWebSocket";

// Mirrors backend/services/log_service.py::AGENT_COLORS — kept in sync
// manually since the frontend doesn't share that module.
export const AGENT_COLORS: Record<string, string> = {
  PLANNER: "#E8FF47",
  CODER: "#00C896",
  TESTER: "#FF6B35",
  REVIEWER: "#FF3C3C",
  SECURITY: "#FF3C3C",
  HUMAN: "#FFFFFF",
  SYSTEM: "#888888",
  GUARDRAIL: "#FF3C3C",
  IDENTITY_BROKER: "#E8FF47",
  GROUNDING: "#00C896",
  CONTEXT_CURATOR: "#888888",
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

  useMemo(() => {
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
      const next: AgentLogLine[] = [
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [lastMessage]);

  return { connectionStatus: status, lines, agentStatuses };
}
