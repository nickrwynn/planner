import "./globals.css";
import Link from "next/link";
import { AgentPane } from "../components/AgentPane";

export const metadata = {
  title: "Academic OS (Bootstrap)",
  description: "Sprint 1 bootstrap stack"
};

export default function RootLayout({
  children
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body>
        <div className="appShell">
          <aside className="sidebar">
            <div style={{ fontWeight: 700, marginBottom: 12 }}>Academic OS</div>
            <nav style={{ display: "grid", gap: 4 }}>
              <Link className="navLink" href="/">
                Dashboard
              </Link>
              <Link className="navLink" href="/courses">
                Courses
              </Link>
              <Link className="navLink" href="/tasks">
                Tasks
              </Link>
              <Link className="navLink" href="/resources">
                Resources
              </Link>
              <Link className="navLink" href="/search">
                Search
              </Link>
              <Link className="navLink" href="/study-lab">
                Study Lab
              </Link>
              <Link className="navLink" href="/notebooks">
                Notebooks
              </Link>
              <Link className="navLink" href="/notes">
                Notes
              </Link>
            </nav>
          </aside>
          <div className="mainPane">{children}</div>
          <aside className="agentPane">
            <AgentPane />
          </aside>
        </div>
      </body>
    </html>
  );
}

