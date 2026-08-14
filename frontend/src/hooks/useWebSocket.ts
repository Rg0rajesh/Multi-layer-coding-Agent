import { useEffect, useRef, useState, useCallback } from "react";
import { getAccessToken, refreshAccessToken } from "../api/client";

const WS_BASE_URL = import.meta.env.VITE_WS_URL ?? "ws://localhost:8000";
const BASE_RECONNECT_DELAY_MS = 1000;
const MAX_RECONNECT_DELAY_MS = 10000;

export type WsStatus = "connecting" | "open" | "closed" | "error";
interface UseWebSocketResult<T> { status: WsStatus; lastMessage: T | null; send: (data: unknown) => void; }

export function useWebSocket<T = unknown>(taskId: string | null): UseWebSocketResult<T> {
  const [status, setStatus] = useState<WsStatus>("connecting");
  const [lastMessage, setLastMessage] = useState<T | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const attemptsRef = useRef(0);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>();
  const closedByUs = useRef(false);

  const connect = useCallback(() => {
    if (!taskId || closedByUs.current) return;
    setStatus("connecting");
    const socket = new WebSocket(`${WS_BASE_URL}/ws/task/${taskId}`);
    socketRef.current = socket;

    socket.onopen = async () => {
      const token = getAccessToken() ?? await refreshAccessToken();
      if (!token || socket.readyState !== WebSocket.OPEN) { socket.close(1008, "Authentication required"); return; }
      socket.send(JSON.stringify({ type: "auth", token }));
      attemptsRef.current = 0;
      setStatus("open");
    };
    socket.onmessage = (event) => { try { setLastMessage(JSON.parse(event.data)); } catch { console.warn("Couldn't parse WS message:", event.data); } };
    socket.onerror = () => setStatus("error");
    socket.onclose = () => {
      setStatus("closed");
      if (closedByUs.current) return;
      const delay = Math.min(BASE_RECONNECT_DELAY_MS * 2 ** attemptsRef.current, MAX_RECONNECT_DELAY_MS);
      attemptsRef.current += 1;
      reconnectTimer.current = setTimeout(connect, delay);
    };
  }, [taskId]);

  useEffect(() => {
    closedByUs.current = false;
    attemptsRef.current = 0;
    connect();
    return () => { closedByUs.current = true; clearTimeout(reconnectTimer.current); socketRef.current?.close(); };
  }, [connect]);

  const send = useCallback((data: unknown) => { if (socketRef.current?.readyState === WebSocket.OPEN) socketRef.current.send(JSON.stringify(data)); }, []);
  return { status, lastMessage, send };
}
