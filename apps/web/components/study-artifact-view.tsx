"use client";

type StudyArtifactViewProps = {
  artifactType: string;
  content: Record<string, unknown> | null | undefined;
};

function asArray(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function asString(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function StudyArtifactView({ artifactType, content }: StudyArtifactViewProps) {
  if (!content) {
    return <div style={{ color: "#666" }}>No content.</div>;
  }

  const type = (artifactType || "").replace(/-/g, "_");
  const title = asString(content.title);

  if (type === "summary") {
    const sections = asArray(content.sections);
    return (
      <div className="studyArtifactView">
        {title ? <h3 style={{ marginTop: 0 }}>{title}</h3> : null}
        {sections.length === 0 ? <div style={{ color: "#666" }}>No sections.</div> : null}
        {sections.map((raw, idx) => {
          const section = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
          const heading = asString(section.heading) || `Section ${idx + 1}`;
          const bullets = asArray(section.bullets).map(asString).filter(Boolean);
          return (
            <section key={`${heading}-${idx}`} style={{ marginBottom: 16 }}>
              <h4 style={{ margin: "0 0 8px" }}>{heading}</h4>
              <ul style={{ margin: 0, paddingLeft: 20 }}>
                {bullets.map((b, i) => (
                  <li key={i} style={{ marginBottom: 4 }}>
                    {b}
                  </li>
                ))}
              </ul>
            </section>
          );
        })}
      </div>
    );
  }

  if (type === "flashcards") {
    const cards = asArray(content.cards);
    return (
      <div className="studyArtifactView">
        {title ? <h3 style={{ marginTop: 0 }}>{title}</h3> : null}
        {cards.length === 0 ? <div style={{ color: "#666" }}>No cards.</div> : null}
        <div style={{ display: "grid", gap: 12 }}>
          {cards.map((raw, idx) => {
            const card = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
            return (
              <div
                key={idx}
                style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, background: "#fff" }}
              >
                <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Card {idx + 1}</div>
                <div style={{ fontWeight: 600, marginBottom: 6 }}>{asString(card.question) || "—"}</div>
                <div style={{ color: "#374151" }}>{asString(card.answer) || "—"}</div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  if (type === "quiz") {
    const items = asArray(content.items);
    return (
      <div className="studyArtifactView">
        {title ? <h3 style={{ marginTop: 0 }}>{title}</h3> : null}
        {items.length === 0 ? <div style={{ color: "#666" }}>No quiz items.</div> : null}
        <ol style={{ margin: 0, paddingLeft: 20, display: "grid", gap: 14 }}>
          {items.map((raw, idx) => {
            const item = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
            return (
              <li key={idx}>
                <div style={{ fontWeight: 600, marginBottom: 4 }}>{asString(item.question) || "—"}</div>
                <div>
                  <span style={{ color: "#6b7280" }}>Answer: </span>
                  {asString(item.answer) || "—"}
                </div>
                {asString(item.explanation) ? (
                  <div style={{ marginTop: 4, color: "#374151" }}>{asString(item.explanation)}</div>
                ) : null}
              </li>
            );
          })}
        </ol>
      </div>
    );
  }

  if (type === "sample_problems" || type === "sample-problems") {
    const problems = asArray(content.problems);
    return (
      <div className="studyArtifactView">
        {title ? <h3 style={{ marginTop: 0 }}>{title}</h3> : null}
        {problems.length === 0 ? <div style={{ color: "#666" }}>No problems.</div> : null}
        <div style={{ display: "grid", gap: 16 }}>
          {problems.map((raw, idx) => {
            const problem = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
            return (
              <div
                key={idx}
                style={{ border: "1px solid #e5e7eb", borderRadius: 8, padding: 12, background: "#fff" }}
              >
                <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4 }}>Problem {idx + 1}</div>
                <div style={{ fontWeight: 600, marginBottom: 8, whiteSpace: "pre-wrap" }}>
                  {asString(problem.problem) || "—"}
                </div>
                <div style={{ color: "#374151", whiteSpace: "pre-wrap" }}>
                  <span style={{ color: "#6b7280" }}>Solution: </span>
                  {asString(problem.solution) || "—"}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    );
  }

  return (
    <pre style={{ margin: 0, whiteSpace: "pre-wrap", fontSize: 12 }}>
      {JSON.stringify(content, null, 2)}
    </pre>
  );
}
