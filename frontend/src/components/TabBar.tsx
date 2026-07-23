export interface Tab {
  id: string;
  label: string;
  icon: string;
  // "end" fuer Tabs, die nicht zum eigentlichen Schreibablauf gehoeren
  // (z.B. KI-Ziele, Einstellungen) - werden rechtsbuendig abgesetzt.
  align?: "end";
}

interface TabBarProps {
  tabs: Tab[];
  active: string;
  onSelect: (id: string) => void;
}

function TabButton({ tab, istAktiv, onSelect }: { tab: Tab; istAktiv: boolean; onSelect: (id: string) => void }) {
  return (
    <button
      onClick={() => onSelect(tab.id)}
      className={`flex items-center gap-1.5 whitespace-nowrap rounded-full px-3.5 py-1.5 text-sm font-medium transition-all duration-150 ${
        istAktiv
          ? "bg-accent-soft text-accent-light shadow-inner"
          : "text-text-muted hover:bg-surface-hover hover:text-text"
      }`}
    >
      <span aria-hidden="true">{tab.icon}</span>
      {tab.label}
    </button>
  );
}

export function TabBar({ tabs, active, onSelect }: TabBarProps) {
  const start = tabs.filter((t) => t.align !== "end");
  const end = tabs.filter((t) => t.align === "end");

  return (
    <div className="flex gap-1 overflow-x-auto border-b border-border bg-surface/60 px-4 py-2">
      {start.map((tab) => (
        <TabButton key={tab.id} tab={tab} istAktiv={active === tab.id} onSelect={onSelect} />
      ))}
      {end.length > 0 && (
        <div className="ml-auto flex shrink-0 gap-1">
          {end.map((tab) => (
            <TabButton key={tab.id} tab={tab} istAktiv={active === tab.id} onSelect={onSelect} />
          ))}
        </div>
      )}
    </div>
  );
}
