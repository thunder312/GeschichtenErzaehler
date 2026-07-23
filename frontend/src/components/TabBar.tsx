export interface Tab {
  id: string;
  label: string;
}

interface TabBarProps {
  tabs: Tab[];
  active: string;
  onSelect: (id: string) => void;
}

export function TabBar({ tabs, active, onSelect }: TabBarProps) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-neutral-200 px-4 dark:border-neutral-800">
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onSelect(tab.id)}
          className={`-mb-px whitespace-nowrap border-b-2 px-4 py-2.5 text-sm font-medium transition-colors ${
            active === tab.id
              ? "border-purple-500 text-purple-700 dark:text-purple-400"
              : "border-transparent text-neutral-500 hover:text-neutral-800 dark:text-neutral-400 dark:hover:text-neutral-100"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}
