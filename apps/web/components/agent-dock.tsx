"use client";

import { useEffect, useState } from "react";
import { AgentPane } from "./AgentPane";

const STORAGE_KEY = "agent_pane_collapsed";

export function AgentDock() {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setCollapsed(localStorage.getItem(STORAGE_KEY) === "1");
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("agentCollapsed", collapsed);
    localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
  }, [collapsed]);

  if (collapsed) {
    return (
      <button type="button" className="agentDockChip" onClick={() => setCollapsed(false)} title="Open agent">
        Agent
      </button>
    );
  }

  return (
    <aside className="agentPane">
      <AgentPane onCollapse={() => setCollapsed(true)} />
    </aside>
  );
}
