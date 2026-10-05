export const mockNodes = [
  { id: "moodle", label: "Moodle", x: 18, y: 30, kind: "source" },
  { id: "github", label: "GitHub", x: 72, y: 24, kind: "source" },
  { id: "ufc", label: "UFC", x: 30, y: 68, kind: "source" },
  { id: "openalex", label: "OpenAlex", x: 64, y: 66, kind: "source" },
  { id: "voce", label: "Você", x: 45, y: 45, kind: "center" }
];

export const mockSidebar = {
  changes: [
    { id: 1, text: "Placeholder: nota de Cálculo II atualizada", time: "2h" },
    { id: 2, text: "Placeholder: novo commit em projeto-final", time: "5h" }
  ],
  connections: [
    { id: 1, text: "Moodle ⇄ GitHub (placeholder)" },
    { id: 2, text: "UFC ⇄ OpenAlex (placeholder)" }
  ],
  events: [
    { id: 1, text: "P1 — placeholder", time: "12 OUT" },
    { id: 2, text: "Entrega parcial — placeholder", time: "20 OUT" }
  ],
  sources: ["Moodle", "GitHub", "UFC", "OpenAlex"]
};
