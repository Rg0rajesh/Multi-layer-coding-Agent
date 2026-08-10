// frontend/src/hooks/useWebSocket.ts
import { useEffect, useRef, useState, useCallback } from "react";

const WS_BASE_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";

// Backend closes idle sockets and Ollama cold-starts can stall a task for
// a while — reconnect instead of just giving up on the first drop.
const MAX_RECONNECT_ATTEMPTS = 5;
const BASE_RECONNECT_DELAY_MS = 1000;

export type WsStatus = "connecting" | "open" | "closed" | "error";

interface UseWebSocketResult<T> {
  status: WsStatus;
  lastMessage: T | null;
  send: (data: unknown) => void;
}

/**
 * Thin wrapper around a task's live WS channel. Doesn't try to interpret
 * what comes through — routers/websocket.py already tags every payload
 * with a `type` field, so parsing that belongs to whoever's consuming
 * this (see useAgentStream.ts), not here.
 */
export function useWebSocket<T = unknown>(taskId: string | null): UseWebSocketResult<T> {
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [lastMessage, setLastMessage] = useState<T | null>(null);

  const socketRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const closedByUs = useRef(false);

  const connect = useCallback(() => {
    if (!taskId) return;

    setStatus("connecting");
    const socket = new WebSocket(`${WS_BASE_URL}/ws/task/${taskId}`);
    socketRef.current = socket;

    socket.onopen = () => {
      attemptsRef.current = 0;
      setStatus("open");
    };

    socket.onmessage = (event) => {
      try {
        setLastMessage(JSON.parse(event.data));
      } catch {
        console.warn("Couldn't parse WS message:", event.data);
      }
    };

    socket.onerror = () => setStatus("error");

    socket.onclose = () => {
      setStatus("closed");
      if (closedByUs.current) return;

      if (attemptsRef.current < MAX_RECONNECT_ATTEMPTS) {
        const delay = BASE_RECONNECT_DELAY_MS * 2 ** attemptsRef.current;
        attemptsRef.current += 1;
        reconnectTimer.current = setTimeout(connect, delay);
      }
    };
  }, [taskId]);

  useEffect(() => {
    closedByUs.current = false;
    connect();

    return () => {
      closedByUs.current = true;
      clearTimeout(reconnectTimer.current);
      socketRef.current?.close();
    };
  }, [connect]);

  const send = useCallback((data: unknown) => {
    if (socketRef.current?.readyState === WebSocket.OPEN) {
      socketRef.current.send(JSON.stringify(data));
    }
  }, []);

  return { status, lastMessage, send };
}
