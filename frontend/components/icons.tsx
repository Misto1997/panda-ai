// Small inline SVG icons (stroke = currentColor). Decorative: callers put the aria-label on the button.
const base = { width: 18, height: 18, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round", strokeLinejoin: "round", "aria-hidden": true } as const;
export const PlusIcon = () => <svg {...base}><path d="M12 5v14M5 12h14" /></svg>;
export const SidebarIcon = () => <svg {...base}><rect x="3" y="4" width="18" height="16" rx="3" /><path d="M9 4v16" /></svg>;
export const CloseIcon = () => <svg {...base} width={14} height={14}><path d="M6 6l12 12M18 6L6 18" /></svg>;
export const MenuIcon = () => <svg {...base}><path d="M4 7h16M4 12h16M4 17h16" /></svg>;
export const SendIcon = () => <svg {...base}><path d="M12 19V5M5 12l7-7 7 7" /></svg>;
export const SlidersIcon = () => <svg {...base}><path d="M4 6h10M18 6h2M4 12h2M10 12h10M4 18h12M20 18h0" /><circle cx="16" cy="6" r="2" /><circle cx="8" cy="12" r="2" /><circle cx="18" cy="18" r="2" /></svg>;
export const ChevronIcon = () => <svg {...base} width={14} height={14}><path d="M6 9l6 6 6-6" /></svg>;
