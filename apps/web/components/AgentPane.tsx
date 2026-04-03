"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { apiDelete, apiGet, apiPatch, apiPost } from "../lib/api";
import type { Course, Resource } from "../lib/types";

type Citation = {
  resource_id: string;
  page_number: number | null;
  chunk_id: string;
  chunk_index: number;
  snippet: string;
};

type ChatItem = {
  id?: string;
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
};

const STORAGE_KEY = "agent_conversation_id";

type ApiMessage = {
  id: string;
  role: string;
  content: string;
  citations_json: Citation[] | null;
};

export function AgentPane() {
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [items, setItems] = useState<ChatItem[]>([]);
  const [input, setInput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [historyLoaded, setHistoryLoaded] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  const [courses, setCourses] = useState<Course[]>([]);
  const [resources, setResources] = useState<Resource[]>([]);
  const [scopeMode, setScopeMode] = useState<"course" | "global">("course");
  const [courseId, setCourseId] = useState<string>("");
  const [selected, setSelected] = useState<Record<string, boolean>>({});

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [items, isSending]);

  async function refreshScope(nextCourseId?: string, nextScopeMode?: "course" | "global") {
    try {
      const cs = await apiGet<Course[]>("/courses");
      setCourses(cs);
      const mode = nextScopeMode ?? scopeMode;
      const selectedCourse = nextCourseId ?? courseId ?? cs[0]?.id ?? "";
      setCourseId(selectedCourse);
      if (mode === "global") {
        setResources(await apiGet<Resource[]>("/resources?limit=100&offset=0"));
      } else if (selectedCourse) {
        setResources(
          await apiGet<Resource[]>(
            `/resources?course_id=${encodeURIComponent(selectedCourse)}&limit=100&offset=0`
          )
        );
      } else {
        setResources([]);
      }
    } catch (e) {
      setError(String(e));
    }
  }

  useEffect(() => {
    refreshScope();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    async function loadHistory() {
      try {
        const stored = typeof window !== "undefined" ? localStorage.getItem(STORAGE_KEY) : null;
        if (!stored) {
          setHistoryLoaded(true);
          return;
        }
        const msgs = await apiGet<ApiMessage[]>(`/ai/conversations/${stored}/messages`);
        setConversationId(stored);
        setItems(
          msgs.map((m) => ({
            id: m.id,
            role: m.role === "assistant" ? "assistant" : "user",
            content: m.content,
            citations: m.role === "assistant" && m.citations_json ? m.citations_json : undefined
          }))
        );
      } catch {
        localStorage.removeItem(STORAGE_KEY);
      } finally {
        setHistoryLoaded(true);
      }
    }
    loadHistory();
  }, []);

  async function send() {
    const msg = input.trim();
    if (!msg) return;
    setInput("");
    setError(null);
    setIsSending(true);
    setItems((prev) => [...prev, { role: "user", content: msg }]);

    try {
      const selectedIds = Object.keys(selected).filter((k) => selected[k]);
      const data = await apiPost<{
        conversation_id: string;
        answer: string;
        citations: Citation[];
      }>("/ai/ask", {
        message: msg,
        conversation_id: conversationId,
        course_id: scopeMode === "course" ? courseId || null : null,
        resource_ids: selectedIds.length > 0 ? selectedIds : null,
        top_k: 8
      });
      setConversationId(data.conversation_id);
      if (typeof window !== "undefined") {
        localStorage.setItem(STORAGE_KEY, data.conversation_id);
      }
      setItems((prev) => [
        ...prev,
        { role: "assistant", content: data.answer, citations: data.citations ?? [] }
      ]);
    } catch (e) {
      setError(String(e));
    } finally {
      setIsSending(false);
    }
  }

  function newChat() {
    setConversationId(null);
    setItems([]);
    setError(null);
    if (typeof window !== "undefined") {
      localStorage.removeItem(STORAGE_KEY);
    }
  }

  async function renameChat() {
    if (!conversationId) return;
    const next = window.prompt("Conversation title");
    if (!next || !next.trim()) return;
    setError(null);
    try {
      await apiPatch(`/ai/conversations/${conversationId}?title=${encodeURIComponent(next.trim())}`, {});
    } catch (e) {
      setError(String(e));
    }
  }

  async function deleteChat() {
    if (!conversationId) return;
    if (!window.confirm("Delete this conversation?")) return;
    setError(null);
    try {
      await apiDelete(`/ai/conversations/${conversationId}`);
      newChat();
    } catch (e) {
      setError(String(e));
    }
  }

  return (
    <div style={{ display: "grid", gridTemplateRows: "auto 1fr auto", height: "100%" }}>
      <div style={{ display: "flex", justifyContent: "space-between", gap: 8, alignItems: "center" }}>
        <div style={{ fontWeight: 700 }}>Agent</div>
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          <div style={{ fontSize: 12, color: "#555" }}>Ask</div>
          <button
            type="button"
            onClick={newChat}
            style={{ padding: "4px 8px", fontSize: 12 }}
            title="Start a new conversation"
          >
            New chat
          </button>
          <button type="button" onClick={renameChat} style={{ padding: "4px 8px", fontSize: 12 }} disabled={!conversationId}>
            Rename
          </button>
          <button type="button" onClick={deleteChat} style={{ padding: "4px 8px", fontSize: 12 }} disabled={!conversationId}>
            Delete
          </button>
        </div>
      </div>

      <div style={{ marginTop: 10 }} className="card">
        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <div style={{ fontWeight: 600, fontSize: 12 }}>Scope</div>
          <select
            aria-label="Agent scope mode"
            value={scopeMode}
            onChange={(e) => {
              const mode = e.target.value as "course" | "global";
              setSelected({});
              setScopeMode(mode);
              refreshScope(courseId, mode);
            }}
            style={{ padding: 6, fontSize: 12 }}
          >
            <option value="course">Course</option>
            <option value="global">All resources</option>
          </select>
          <select
            aria-label="Agent course filter"
            value={courseId}
            onChange={(e) => {
              setSelected({});
              setCourseId(e.target.value);
              refreshScope(e.target.value);
            }}
            disabled={scopeMode !== "course"}
            style={{ padding: 6, fontSize: 12 }}
          >
            {courses.map((c) => (
              <option key={c.id} value={c.id}>
                {c.code ? `${c.code} — ` : ""}{c.name}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => {
              setSelected({});
              refreshScope();
            }}
            style={{ padding: "6px 10px", fontSize: 12 }}
          >
            Refresh
          </button>
        </div>

        <div style={{ display: "grid", gap: 6, marginTop: 8, maxHeight: 120, overflow: "auto" }}>
          {resources.map((r) => (
            <label key={r.id} style={{ display: "flex", gap: 8, alignItems: "center", fontSize: 12 }}>
              <input
                type="checkbox"
                checked={!!selected[r.id]}
                onChange={(e) => setSelected((prev) => ({ ...prev, [r.id]: e.target.checked }))}
              />
              <span style={{ fontWeight: 600 }}>{r.title}</span>
              <span style={{ color: "#555" }}>index={r.index_status}</span>
            </label>
          ))}
          {resources.length === 0 && <div style={{ color: "#555", fontSize: 12 }}>No resources.</div>}
        </div>
      </div>

      <div style={{ overflow: "auto", marginTop: 12, paddingRight: 6 }}>
        {!historyLoaded && <div style={{ color: "#555", fontSize: 13 }}>Loading history…</div>}
        {historyLoaded && items.length === 0 && (
          <div style={{ color: "#555", fontSize: 14 }}>
            Ask a question about your uploaded resources. Answers will cite chunks when available.
          </div>
        )}
        <div style={{ display: "grid", gap: 10 }}>
          {items.map((it, idx) => (
            <div
              key={it.id ?? `${it.role}-${idx}`}
              style={{
                border: "1px solid #e5e7eb",
                borderRadius: 10,
                padding: 10,
                background: it.role === "user" ? "#f9fafb" : "#fff"
              }}
            >
              <div style={{ fontSize: 12, color: "#555", marginBottom: 6 }}>{it.role}</div>
              <div style={{ whiteSpace: "pre-wrap", fontSize: 14 }}>{it.content}</div>
              {it.citations && it.citations.length > 0 && (
                <div style={{ marginTop: 8, fontSize: 12 }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>Citations</div>
                  <div style={{ display: "grid", gap: 6 }}>
                    {it.citations.map((c) => (
                      <div key={c.chunk_id} style={{ color: "#374151" }}>
                        <Link href={`/resources/${c.resource_id}`} style={{ textDecoration: "none" }}>
                          resource {c.resource_id}
                        </Link>
                        {c.page_number ? ` • page ${c.page_number}` : ""} • chunk {c.chunk_index}
                        <div style={{ color: "#555", marginTop: 2, whiteSpace: "pre-wrap" }}>
                          {c.snippet}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
      </div>

      <div style={{ marginTop: 12 }}>
        {error && <div style={{ color: "crimson", fontSize: 12, marginBottom: 6 }}>{error}</div>}
        <form
          onSubmit={(e) => {
            e.preventDefault();
            if (!isSending) send();
          }}
          style={{ display: "flex", gap: 8 }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask…"
            style={{ padding: 8, flex: 1 }}
            disabled={isSending}
          />
          <button type="submit" style={{ padding: "8px 12px" }} disabled={isSending}>
            Send
          </button>
        </form>
      </div>
    </div>
  );
}
