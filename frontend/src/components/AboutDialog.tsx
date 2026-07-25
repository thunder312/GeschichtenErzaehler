export function AboutDialog({ onClose }: { onClose: () => void }) {
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className="relative mx-auto max-w-md rounded-2xl border border-border bg-surface p-6 shadow-2xl shadow-black/50"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={onClose}
          className="absolute right-3 top-3 text-text-muted hover:text-text"
          aria-label="Schließen"
        >
          ✕
        </button>
        <div className="mb-1 flex items-center gap-2 text-2xl">
          📖
          <span className="font-heading bg-gradient-to-r from-accent-light to-accent bg-clip-text text-2xl font-bold text-transparent">
            Geschichten Erzähler
          </span>
        </div>
        <p className="mb-4 text-sm text-text-muted">
          Eine geführte Fünf-Rollen-Pipeline für KI-geschriebene Geschichten mit lokalen
          Ollama-Modellen.
        </p>
        <div className="space-y-3 text-sm">
          <div>
            <div className="text-xs font-medium uppercase tracking-wider text-text-muted">Konzept &amp; Entwicklung</div>
            <a
              href="https://github.com/thunder312"
              target="_blank"
              rel="noreferrer"
              className="text-accent-light hover:underline"
            >
              Daniel Ertl
            </a>
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wider text-text-muted">Umgesetzt mit</div>
            <a
              href="https://www.anthropic.com/claude-code"
              target="_blank"
              rel="noreferrer"
              className="text-accent-light hover:underline"
            >
              Claude Sonnet 5
            </a>
            <span className="text-text-muted"> (Anthropic)</span>
          </div>
          <div>
            <div className="text-xs font-medium uppercase tracking-wider text-text-muted">Quellcode</div>
            <a
              href="https://github.com/thunder312/GeschichtenErzaehler"
              target="_blank"
              rel="noreferrer"
              className="text-accent-light hover:underline"
            >
              github.com/thunder312/GeschichtenErzaehler
            </a>
          </div>
        </div>
      </div>
    </div>
  );
}
